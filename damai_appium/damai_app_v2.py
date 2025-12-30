"""Command line entry point for the modular Damai Appium runner."""

from __future__ import annotations

import argparse
import json
import time
import subprocess
from datetime import datetime, timezone
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError

from damai_appium import (
    AppTicketConfig,
    ConfigValidationError,
    DamaiAppTicketRunner,
    FailureReason,
    LogLevel,
)


def _console_logger(level: str, message: str, context: Optional[Dict[str, object]] = None) -> None:
    if context is None:
        context = {}
    ctx_repr = " ".join(f"{k}={v}" for k, v in context.items())
    if ctx_repr:
        print(f"[{level.upper()}] {message} | {ctx_repr}")
    else:
        print(f"[{level.upper()}] {message}")


def _make_session_logger(session_label: str):
    def _logger(level: str, message: str, context: Optional[Dict[str, object]] = None) -> None:
        merged: Dict[str, Any] = {"session": session_label}
        if context:
            merged.update(context)
        _console_logger(level, message, merged)

    return _logger


def _derive_session_label(config: AppTicketConfig, index: int) -> str:
    device_caps = config.device_caps or {}
    parts: List[str] = []
    device_name = device_caps.get("deviceName")
    udid = device_caps.get("udid")
    if device_name:
        parts.append(str(device_name))
    if udid and udid not in parts:
        parts.append(str(udid))
    if not parts:
        parts.append(config.server_url)
    descriptor = "/".join(parts)
    return f"device-{index}:{descriptor}"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Damai app ticket grabbing (Appium)")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="配置文件路径，默认使用 damai_appium/config.jsonc",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="失败重试次数（包含首次执行）",
    )
    parser.add_argument(
        "--export-report",
        type=Path,
        default=None,
        help="可选：将运行日志与统计导出为 JSON 文件",
    )
    parser.add_argument(
        "--start-at",
        type=str,
        default=None,
        help="定时开抢时间（例如 2025-10-01T20:00:00+08:00 或 '2025-10-01 20:00:00' 按本地时区解析）",
    )
    parser.add_argument(
        "--warmup-sec",
        type=int,
        default=0,
        help="开抢前预热检查的提前秒数（0 表示不启用预热）",
    )
    return parser.parse_args()


def _print_summary(result: bool, report, *, session_label: Optional[str] = None) -> None:
    if report is None:
        prefix = "[SUMMARY]" if session_label is None else f"[SUMMARY][{session_label}]"
        print(f"{prefix} No run report available.")
        return

    metrics = report.metrics
    duration = max(metrics.end_time - metrics.start_time, 0.0)
    retries = max(metrics.attempts - 1, 0)
    status = "SUCCESS" if result else "FAILED"
    prefix = "[SUMMARY]" if session_label is None else f"[SUMMARY][{session_label}]"
    print(
        f"{prefix} Status={status} Attempts={metrics.attempts} Retries={retries} "
        f"Duration={duration:.2f}s FinalPhase={metrics.final_phase.value}"
    )
    if not result:
        reason = metrics.failure_reason or "未能成功完成流程"
        extra = (
            f" (code={metrics.failure_code.value})" if metrics.failure_code else ""
        )
        print(f"{prefix} FailureReason={reason}{extra}")
        if metrics.failure_code == FailureReason.MAX_RETRIES:
            print(f"{prefix} 提示: 已达到最大重试次数，可尝试调整参数或检查网络。")


def _export_reports(target: Path, runs: List[Dict[str, Any]]) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    now_utc = datetime.now(timezone.utc)
    export_payload = {
        "generated_at": now_utc.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "overall_success": all(item["success"] for item in runs),
        "runs": [
            {
                "session": item["session"],
                "success": item["success"],
                "config": {
                    "server_url": item["config"].server_url,
                    "users": item["config"].users,
                    "keyword": item["config"].keyword,
                    "city": item["config"].city,
                    "date": item["config"].date,
                    "price": item["config"].price,
                    "price_index": item["config"].price_index,
                    "device_caps": item["config"].device_caps,
                },
                "report": item["report"].to_dict() if item["report"] else None,
            }
            for item in runs
        ],
    }
    target.write_text(json.dumps(export_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def _local_tz():
    """Return the current local timezone object."""
    return datetime.now().astimezone().tzinfo


def _parse_start_at_text(text: str) -> datetime:
    """Parse --start-at into an aware UTC datetime.

    Accepts:
      - ISO8601 like '2025-10-01T20:00:00+08:00' or '2025-10-01T12:00:00Z'
      - 'YYYY-MM-DD HH:MM:SS' (treated as local timezone)
    """
    raw = text.strip()
    # Normalize 'Z' suffix to +00:00 for fromisoformat
    norm = raw.replace("Z", "+00:00")
    dt: Optional[datetime] = None
    try:
        dt = datetime.fromisoformat(norm)
    except Exception:
        # Try replace space with 'T'
        try:
            dt = datetime.fromisoformat(norm.replace(" ", "T"))
        except Exception:
            dt = None
    if dt is None:
        raise ValueError(f"无法解析开抢时间: {text}")

    if dt.tzinfo is None:
        # Assume local timezone when tzinfo missing
        dt = dt.replace(tzinfo=_local_tz())
    return dt.astimezone(timezone.utc)


def _check_appium_status(server_url: str, timeout: float = 3.0) -> bool:
    """Check Appium /status endpoint quickly."""
    base = server_url.rstrip("/")
    status_url = f"{base}/status"
    try:
        req = Request(status_url)
        with urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except URLError:
        return False
    except Exception:
        return False


def _adb_ready(timeout: float = 5.0) -> bool:
    """Check if any adb device is in 'device' state (best-effort)."""
    try:
        proc = subprocess.run(
            ["adb", "devices", "-l"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if proc.returncode != 0:
            return False
        lines = (proc.stdout or "").strip().splitlines()
        # Skip header line, look for any 'device' (but not 'unauthorized', 'offline')
        for line in lines[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[1].lower() == "device":
                return True
        return False
    except Exception:
        return False


def _wait_until_utc(target_utc: datetime, warmup_sec: int = 0, server_url: Optional[str] = None, config: Optional[AppTicketConfig] = None) -> None:
    """Wait until target UTC time with optional warmup checks."""
    now_utc = datetime.now(timezone.utc)
    remain = (target_utc - now_utc).total_seconds()

    if remain <= 0:
        print(f"[INFO] 开抢时间已过 {abs(remain):.2f}s，立即执行。")
        return

    warmup = max(0, int(warmup_sec or 0))
    if warmup > 0 and remain > warmup:
        sleep_sec = remain - warmup
        print(f"[INFO] 距离开抢还有 {remain:.2f}s，先等待 {sleep_sec:.2f}s 后进入预热检查。")
        time.sleep(sleep_sec)

    # Warmup window (best-effort health checks and navigate to detail page)
    if warmup > 0:
        if server_url:
            ok = _check_appium_status(server_url)
            status = "OK" if ok else "FAIL"
            print(f"[INFO] Appium /status 预热检查: {status} ({server_url})")
        adb_ok = _adb_ready()
        print(f"[INFO] adb 设备状态: {'OK' if adb_ok else 'FAIL'}")
        
        # Enter detail page during warmup if config is provided
        if config:
            print(f"[INFO] 进入预热阶段，导航到演出详情页面...")
            try:
                # Create a runner instance
                runner = DamaiAppTicketRunner(config=config)
                # Connect to Appium server
                driver = runner._create_driver()
                runner._driver = driver
                runner._wait = WebDriverWait(driver, config.wait_timeout)
                
                # Apply driver settings
                runner._apply_driver_settings()
                
                # Search for the event
                if config.keyword:
                    print(f"[INFO] 搜索演出: {config.keyword}")
                    if not runner._search_event(config.keyword):
                        print(f"[WARNING] 未能完成演出搜索")
                    else:
                        # Tap purchase button to enter detail page
                        print(f"[INFO] 尝试点击预约/购买按钮进入详情页面")
                        if runner._tap_purchase_button():
                            print(f"[INFO] 已成功进入详情页面，等待开抢时间...")
                        else:
                            print(f"[WARNING] 未能找到预约/购买入口")
                
                # Keep the driver alive until the target time
                while True:
                    now_utc = datetime.now(timezone.utc)
                    remain = (target_utc - now_utc).total_seconds()
                    if remain <= 0:
                        break
                    if remain > 1.0:
                        # Sleep most of the remaining time, keep 1s for fine-grained loop
                        time.sleep(remain - 1.0)
                    else:
                        # Sub-second busy wait
                        time.sleep(0.001)
                        
                # Cleanup driver
                driver.quit()
            except Exception as exc:
                print(f"[ERROR] 预热期间进入详情页面失败: {exc}")
                # Continue waiting even if there's an error
                while True:
                    now_utc = datetime.now(timezone.utc)
                    remain = (target_utc - now_utc).total_seconds()
                    if remain <= 0:
                        break
                    if remain > 1.0:
                        time.sleep(remain - 1.0)
                    else:
                        time.sleep(0.001)
                return
    else:
        # Final precise wait to the target moment
        while True:
            now_utc = datetime.now(timezone.utc)
            remain = (target_utc - now_utc).total_seconds()
            if remain <= 0:
                break
            if remain > 1.0:
                # Sleep most of the remaining time, keep 1s for fine-grained loop
                time.sleep(remain - 1.0)
            else:
                # Sub-second busy wait
                time.sleep(0.001)

    print("[INFO] 到点，开始执行抢票流程。")


def main() -> int:
    args = _parse_args()
    try:
        configs = AppTicketConfig.load_all(args.config)
    except FileNotFoundError as exc:
        print(f"[ERROR] {exc}")
        return 2
    except ConfigValidationError as exc:
        print(f"[ERROR] {exc.message}")
        for item in exc.errors:
            print(f"        - {item}")
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] 配置加载失败: {exc}")
        return 2

    # If scheduled start is specified, wait until the target time before executing.
    if getattr(args, "start_at", None):
        try:
            target_utc = _parse_start_at_text(args.start_at)
            first_server = configs[0].server_url if configs else None
            # Use the first config for warmup detail page navigation
            first_config = configs[0] if configs else None
            _wait_until_utc(target_utc, getattr(args, "warmup_sec", 0), first_server, first_config)
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] 定时等待发生异常: {exc}，将立即执行。")

    runs: List[Dict[str, Any]] = []
    total = len(configs)
    print(f"[INFO] 发现 {total} 个待执行会话。")

    overall_success = True
    for index, config in enumerate(configs, start=1):
        session_label = _derive_session_label(config, index)
        logger = _make_session_logger(session_label)
        print(f"[INFO] 开始执行 {session_label}")
        runner = DamaiAppTicketRunner(config=config, logger=logger)
        success = runner.run(max(args.retries, 1))
        report = runner.get_last_report()
        _print_summary(success, report, session_label=session_label)
        if not success:
            overall_success = False
        runs.append({"session": session_label, "success": success, "config": config, "report": report})

    print(
        f"[SUMMARY] 所有会话执行完成，共 {total} 个，其中 {sum(1 for item in runs if item['success'])} 个成功。"
    )

    if args.export_report:
        if not runs:
            print("[SUMMARY] No report to export.")
        else:
            export_target = _export_reports(Path(args.export_report), runs)
            print(f"[SUMMARY] 汇总报告已导出: {export_target}")

    return 0 if overall_success else 1


if __name__ == "__main__":
    sys.exit(main())
