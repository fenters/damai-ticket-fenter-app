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
    TicketRunnerError,
    TicketRunnerStopped,
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


def _wait_until_utc(target_utc: datetime, warmup_sec: int = 0, server_url: Optional[str] = None, config: Optional[AppTicketConfig] = None) -> Optional[DamaiAppTicketRunner]:
    """
    预热：等到达预热时间点后，执行完整预热流程。

    预热内容（由 runner.preheat() 完成）：
        连接Appium → 选城市 → 搜索演出 → 进入详情页 →
        点击"立即购买" → 进入选票页 → 预选日期/场次/票价/数量 →
        记录按钮坐标 → 停留在选票页

    预热完成后返回 runner，后续由 sprint() 负责等到开抢时间并极速点击。
    时间等待由 sprint() 内部处理，此函数不再做开抢等待。

    Returns:
        Optional[DamaiAppTicketRunner]: 预热好的 runner（已在选票页就位），失败返回 None。
    """
    now_utc = datetime.now(timezone.utc)
    remain = (target_utc - now_utc).total_seconds()

    if remain <= 0:
        print(f"[INFO] 开抢时间已过 {abs(remain):.2f}s，立即执行（跳过预热）。")
        return None

    warmup = max(0, int(warmup_sec or 0))
    if warmup > 0 and remain > warmup:
        sleep_sec = remain - warmup
        print(f"[INFO] 距离开抢还有 {remain:.2f}s，先等待 {sleep_sec:.2f}s 后进入预热。")
        time.sleep(sleep_sec)
    elif warmup <= 0:
        print(f"[INFO] 未启用预热(warmup_sec=0)，立即开始预热。")

    preheated_runner: Optional[DamaiAppTicketRunner] = None

    if config:
        # 健康检查（非必须，失败不阻塞）
        if server_url:
            ok = _check_appium_status(server_url)
            print(f"[INFO] Appium /status: {'OK' if ok else 'FAIL'} ({server_url})")
        adb_ok = _adb_ready()
        print(f"[INFO] adb 设备: {'OK' if adb_ok else 'FAIL'}")

        print(f"[INFO] 开始完整预热：连接Appium → 搜索演出 → 进入选票页 → 预选 → 记录坐标")
        try:
            runner = DamaiAppTicketRunner(config=config)
            runner.preheat()  # 新 preheat：一路走到选票页并预选
            preheated_runner = runner
            print(f"[INFO] 预热成功！已在选票页就位，等待 sprint() 冲刺")
        except Exception as exc:
            print(f"[ERROR] 预热失败: {exc}")
            # 预热失败也继续 — 让 run() 做完整流程兜底
            preheated_runner = None
    else:
        print(f"[INFO] 未提供配置，跳过预热")

    return preheated_runner


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

    preheated_runner: Optional[DamaiAppTicketRunner] = None
    target_epoch: Optional[float] = None

    # If scheduled start is specified, do preheat before the sale
    if getattr(args, "start_at", None):
        try:
            target_utc = _parse_start_at_text(args.start_at)
            target_epoch = target_utc.timestamp()
            first_server = configs[0].server_url if configs else None
            first_config = configs[0] if configs else None
            preheated_runner = _wait_until_utc(
                target_utc, getattr(args, "warmup_sec", 0), first_server, first_config
            )
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

        # Use preheated runner if available and config matches
        if preheated_runner and preheated_runner.config == config:
            print("[INFO] 使用预热好的runner（已在选票页就位）")
            runner = preheated_runner
            runner._logger = logger
        else:
            runner = DamaiAppTicketRunner(config=config, logger=logger)

        # 有预热且有开抢时间 → 使用极速冲刺模式
        if preheated_runner is not None and target_epoch is not None:
            print("[INFO] 启动极速冲刺模式（坐标盲点 + CPU自旋等待）")
            try:
                success = runner.sprint(target_epoch)
            except TicketRunnerStopped:
                success = False
                print("[WARN] 用户停止了流程")
            except TicketRunnerError as exc:
                success = False
                print(f"[ERROR] 冲刺失败: {exc}")
            except Exception as exc:  # noqa: BLE001
                success = False
                print(f"[ERROR] 冲刺异常: {exc}")
        else:
            # 没有开抢时间 → 使用传统 run() 模式（元素查找兜底）
            print("[INFO] 使用传统抢票模式")
            success = runner.run(max(args.retries, 1))

        report = runner.get_last_report()
        _print_summary(success, report, session_label=session_label)
        if not success:
            overall_success = False
        runs.append({"session": session_label, "success": success, "config": config, "report": report})

        # Cleanup preheated runner after first use
        if preheated_runner and preheated_runner.config == config:
            preheated_runner = None
            target_epoch = None

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
