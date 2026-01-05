# -*- coding: utf-8 -*-
"""
授权模块（简化版）：在 GUI 启动前与 GitHub 原始仓库通信，验证令牌并强制授权。
- 发布：原始仓库 releases/latest 的 body 文本中包含 "AUTHZ:<BASE64>"
- 令牌内容（BASE64 解码后 JSON）示例：
  {
    "exp": 1735660800,          # 过期时间（Unix epoch 秒）
    "repo_id": 123456789,       # 强绑定仓库的数值 ID
    "nonce": "random-string"    # 可选随机数
  }
客户端仅校验仓库 id 与令牌过期时间，不依赖第三方库或签名。
"""

from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import dataclass
from typing import Optional, Tuple
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError


class AuthorizationError(Exception):
    """授权失败异常：在入口捕获后应立即退出。"""


def _unfuse(parts: Tuple[str, ...]) -> str:
    """简单字符串分片拼接（轻混淆，提升逆向成本，不影响功能）。"""
    return "".join(parts)


# TODO: 收到你的真实 GitHub owner 后，将 OWNER 更新为真实值
OWNER = _unfuse(("10000", "ge", "10000"))
REPO = _unfuse(("damai", "-", "ticket", "-", "assistant"))

# 数值仓库 ID 锁定（强绑定），收到你的真实 repo_id 后将其填入整数；None 表示未锁定
REPO_ID_LOCK: Optional[int] = 1059334334

# GitHub API 常量
_UA = "DamaiTicketAssistant/3.0.0"
_GH_API = "https://api.github.com"


@dataclass
class AuthzPayload:
    exp: int
    repo_id: int
    nonce: Optional[str] = None


def _http_get(url: str, timeout: int = 5) -> str:
    """最小依赖的 GET 请求（使用标准库 urllib）。"""
    req = Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": _UA})
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310 - 外部只读 API
        data = resp.read()
        return data.decode("utf-8", errors="replace")


def _fetch_repo_id(owner: str, repo: str) -> int:
    """获取远端仓库的数值 ID（强绑定用）。"""
    url = f"{_GH_API}/repos/{owner}/{repo}"
    try:
        text = _http_get(url)
        obj = json.loads(text)
        rid = int(obj.get("id"))
        return rid
    except (URLError, HTTPError) as exc:
        raise AuthorizationError(f"无法访问仓库信息：{exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise AuthorizationError(f"无法解析仓库信息：{exc}") from exc


def _fetch_latest_release_body(owner: str, repo: str) -> str:
    """读取 releases/latest 的 body（令牌所在位置）。"""
    url = f"{_GH_API}/repos/{owner}/{repo}/releases/latest"
    try:
        text = _http_get(url)
        obj = json.loads(text)
        body = obj.get("body") or ""
        return str(body)
    except (URLError, HTTPError) as exc:
        raise AuthorizationError(f"无法访问授权令牌：{exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise AuthorizationError(f"无法解析授权令牌：{exc}") from exc


def _extract_authz_token(body: str) -> AuthzPayload:
    """从 Release body 中提取 AUTHZ:<BASE64> 并解码为结构（简化版）。"""
    marker = "AUTHZ:"
    start = body.find(marker)
    if start < 0:
        raise AuthorizationError("未找到授权标记（AUTHZ:）")
    start += len(marker)
    end = body.find("\n", start)
    b64 = body[start:end].strip() if end > start else body[start:].strip()
    if not b64:
        raise AuthorizationError("授权标记内容为空")

    try:
        raw = base64.b64decode(b64, validate=True)
        obj = json.loads(raw.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise AuthorizationError(f"令牌解析失败：{exc}") from exc

    for key in ("exp", "repo_id"):
        if key not in obj:
            raise AuthorizationError(f"令牌缺少字段：{key}")

    try:
        return AuthzPayload(
            exp=int(obj["exp"]),
            repo_id=int(obj["repo_id"]),
            nonce=str(obj.get("nonce") or "") or None,
        )
    except Exception as exc:  # noqa: BLE001
        raise AuthorizationError(f"令牌字段类型错误：{exc}") from exc


def _check_exp(payload: AuthzPayload) -> None:
    """过期校验。"""
    now = int(time.time())
    if payload.exp <= now:
        raise AuthorizationError("授权令牌已过期")


def ensure_authorized() -> bool:
    """
    与原始仓库通信并验证授权令牌（简化版）。失败抛出 AuthorizationError。
    返回 True 表示授权通过。
    """
    owner = OWNER
    repo = REPO

    repo_id_actual = _fetch_repo_id(owner, repo)

    # 数值 ID 强绑定（可选）：锁定到你的原始仓库
    if REPO_ID_LOCK is not None and int(REPO_ID_LOCK) != int(repo_id_actual):
        raise AuthorizationError("仓库绑定校验失败（非原始仓库）")

    body = _fetch_latest_release_body(owner, repo)
    payload = _extract_authz_token(body)

    # 令牌中的 repo_id 必须与远端实际仓库 ID 一致，防止伪造
    if int(payload.repo_id) != int(repo_id_actual):
        raise AuthorizationError("令牌与仓库不匹配（repo_id 校验失败）")

    _check_exp(payload)
    return True


def block_if_unauthorized_with_ui() -> None:
    """
    可在 GUI 启动前调用：未授权则弹窗并立即退出（闪退）。
    """
    try:
        ensure_authorized()
    except Exception as exc:  # noqa: BLE001
        try:
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "未获授权",
                f"该工具未被原始仓库授权使用。\n\n详情：{exc}",
            )
        except Exception:
            # UI 弹窗失败也直接退出
            pass
        os._exit(1)