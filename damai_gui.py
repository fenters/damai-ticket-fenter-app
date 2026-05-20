from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from comment import DatePickerCtk

os.environ["DISABLE_CTK_TRACEBACK"] = "1"

import customtkinter as ctk

ctk.set_default_color_theme(str(Path(__file__).resolve().parent / "assets" / "themes" / "damai.json"))

CTK_THEME_PATH = Path(__file__).resolve().parent / "assets" / "themes" / "damai.json"

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

try:
    from damai_appium import (
        AppTicketConfig, ConfigValidationError,
        DamaiAppTicketRunner, FailureReason, LogLevel,
        TicketRunReport,
    )
    from config import parse_adb_devices
    APPIUM_AVAILABLE = True
except Exception:
    AppTicketConfig = None
    DamaiAppTicketRunner = None
    LogLevel = None
    FailureReason = None
    TicketRunReport = None
    parse_adb_devices = None
    APPIUM_AVAILABLE = False

C = {
    "success": "#22C55E",
    "success_bg": "#F0FDF4",
    "warning": "#F59E0B",
    "warning_bg": "#FFFBEB",
    "error": "#EF4444",
    "error_bg": "#FEF2F2",
    "primary": "#3B82F6",
    "primary_bg": "#EFF6FF",
    "info": "#6366F1",
    "info_bg": "#EEF2FF",
    "gray": "#94A3B8",
    "text_secondary": "#64748B",
}


class damaiTheme:
    primary = "#3B82F6"
    primary_dark = "#2563EB"
    success = "#22C55E"
    warning = "#F59E0B"
    error = "#EF4444"
    bg_light = "#F8FAFC"
    bg_dark = "#0F172A"
    card_light = "#FFFFFF"
    card_dark = "#1E293B"
    text_light = "#1E293B"
    text_dark = "#F1F5F9"


class LogManager:
    MAX_ENTRIES = 500
    BATCH_INTERVAL_MS = 200

    def __init__(self, textbox: ctk.CTkTextbox):
        self._textbox = textbox
        self._entries: List[Tuple[str, str, str]] = []
        self._batch_buffer: List[str] = []
        self._batch_timer_id: Optional[str] = None
        self._lock = threading.Lock()
        self._filter_keyword = ""

    def set_filter(self, keyword: str) -> None:
        self._filter_keyword = keyword
        self._rebuild()

    def add(self, message: str, level: str = "info") -> None:
        icon = {"success": "  ", "warning": "  ", "error": "  ", "info": "  "}.get(level, "  ")
        tag = {"success": "success", "warning": "warning", "error": "error", "info": "info"}.get(level, "info")
        ts = datetime.now().strftime("%H:%M:%S")
        formatted = f"[{ts}] {icon} {message}"
        with self._lock:
            self._entries.append((ts, message, level))
            if len(self._entries) > self.MAX_ENTRIES:
                self._entries.pop(0)
            self._batch_buffer.append(formatted)
        self._schedule_flush()

    def _schedule_flush(self) -> None:
        if self._batch_timer_id is not None:
            try:
                self._textbox.master.after_cancel(self._batch_timer_id)
            except Exception:
                pass
        try:
            self._batch_timer_id = self._textbox.master.after(self.BATCH_INTERVAL_MS, self._flush)
        except Exception:
            pass

    def _flush(self) -> None:
        self._batch_timer_id = None
        with self._lock:
            to_add = list(self._batch_buffer)
            self._batch_buffer.clear()
        if not to_add:
            return
        try:
            self._textbox.configure(state="normal")
            for line in to_add:
                matched = True
                if self._filter_keyword:
                    kw = self._filter_keyword.lower()
                    matched = kw in line.lower()
                if matched:
                    self._textbox.insert("end", line + "\n")
            self._textbox.see("end")
            self._textbox.configure(state="disabled")
        except Exception:
            pass

    def _rebuild(self) -> None:
        try:
            self._textbox.configure(state="normal")
            self._textbox.delete("1.0", "end")
            kw = self._filter_keyword.lower()
            for ts, msg, level in self._entries:
                icon = {"success": "  ", "warning": "  ", "error": "  ", "info": "  "}.get(level, "  ")
                line = f"[{ts}] {icon} {msg}"
                if kw and kw not in line.lower():
                    continue
                self._textbox.insert("end", line + "\n")
            self._textbox.see("end")
            self._textbox.configure(state="disabled")
        except Exception:
            pass

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._batch_buffer.clear()
        try:
            self._textbox.configure(state="normal")
            self._textbox.delete("1.0", "end")
            self._textbox.configure(state="disabled")
        except Exception:
            pass

    @property
    def entries(self) -> List[Tuple[str, str, str]]:
        with self._lock:
            return list(self._entries)


class DamaiGUI:
    def __init__(self) -> None:
        self.root = ctk.CTk()
        self.root.title("")
        self.root.geometry("1280x860")
        self.root.minsize(1024, 700)
        self.root.update_idletasks()
        self._center_window()

        self._current_mode = "app"
        self._is_grabbing = False
        self._should_stop = False
        self._cookie_file = "damai_cookies.pkl"
        self._last_cookie_save = time.time()
        self._driver: Optional[Any] = None
        self._app_runner: Optional[Any] = None
        self._app_runner_thread: Optional[threading.Thread] = None
        self._sprint_target_epoch: Optional[float] = None
        self._preheat_executed = False
        self._schedule_running = False
        self._schedule_timer_id: Optional[str] = None
        self._config_payload: Dict[str, Any] = {}
        self._last_app_report: Optional[Any] = None
        self._detected_devices: List[str] = []
        self._web_config: Dict[str, Any] = {}
        self._config_path = Path(__file__).resolve().parent / "config" / "config.json"

        self._app_retries = 3
        self._warmup_sec = 120
        self._wait_timeout = 2.0
        self._retry_delay = 2.0
        self._if_commit_order = True

        self._build_ui()
        self._bind_events()
        self._check_initial_state()
        self._load_config_from_file()

    def _center_window(self) -> None:
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w, h = 1280, 860
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _check_initial_state(self) -> None:
        if not SELENIUM_AVAILABLE:
            self.log("Selenium 不可用，网页模式受限", "warning")
        if not APPIUM_AVAILABLE:
            self.log("Appium 环境未就绪，App 模式受限", "warning")
        self.log("v4.0 已启动 — 选择模式并配置参数", "info")

    # ============================
    # UI BUILDING
    # ============================
    def _build_ui(self) -> None:
        self.root.grid_rowconfigure(0, weight=0)
        self.root.grid_rowconfigure(1, weight=0)
        self.root.grid_rowconfigure(2, weight=1)
        self.root.grid_rowconfigure(3, weight=0)
        self.root.grid_columnconfigure(0, weight=1)

        self._header()
        self._status_row()
        self._content_area()
        self._footer()

    def _header(self) -> None:
        h = ctk.CTkFrame(self.root, fg_color="transparent", height=60)
        h.grid(row=0, column=0, sticky="ew", padx=24, pady=(16, 0))
        h.grid_columnconfigure(1, weight=1)

        container = ctk.CTkFrame(h, fg_color="transparent")
        container.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(container, text="  ", font=("Microsoft YaHei", 22, "bold"), anchor="w").pack(side="left")
        ctk.CTkLabel(container, text="大麦抢票", font=("Microsoft YaHei", 20, "bold"), anchor="w").pack(side="left")
        ctk.CTkLabel(container, text="v4.0", font=("Microsoft YaHei", 12), text_color="#94A3B8", anchor="w").pack(side="left", padx=(6, 0))

        right = ctk.CTkFrame(h, fg_color="transparent")
        right.grid(row=0, column=2, sticky="e")

        self._theme_btn = ctk.CTkButton(
            right, text="\u263E 主题", width=70, height=32,
            fg_color="transparent", border_width=1, border_color="#CBD5E1",
            text_color=("#1E293B", "#F1F5F9"), hover_color="#F1F5F9",
            command=self._toggle_theme,
        )
        self._theme_btn.pack(side="left", padx=(0, 8))

    def _status_row(self) -> None:
        s = ctk.CTkFrame(self.root, fg_color="transparent", height=80)
        s.grid(row=1, column=0, sticky="ew", padx=24, pady=(16, 0))
        s.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="status")

        cards_data = [
            ("mode", " 模式", "App", "#6366F1"),
            ("env", " 环境", "待检测", "#94A3B8"),
            ("device", " 设备", "未连接", "#94A3B8"),
            ("status", " 状态", "就绪", "#22C55E"),
        ]
        self._status_labels: Dict[str, Tuple[ctk.CTkFrame, ctk.CTkLabel, ctk.CTkLabel]] = {}
        for i, (key, title, val, color) in enumerate(cards_data):
            card = ctk.CTkFrame(s, corner_radius=12, border_width=0)
            card.grid(row=0, column=i, sticky="ew", padx=4)
            row_f = ctk.CTkFrame(card, fg_color="transparent")
            row_f.pack(fill="both", expand=True, padx=14, pady=10)
            ctk.CTkLabel(row_f, text=title, font=("Microsoft YaHei", 11), text_color="#94A3B8", anchor="w").pack(anchor="w")
            val_lbl = ctk.CTkLabel(row_f, text=val, font=("Microsoft YaHei", 16, "bold"), text_color=color, anchor="w")
            val_lbl.pack(anchor="w", pady=(2, 0))
            self._status_labels[key] = (card, row_f, val_lbl)

        mode_frame = self._status_labels["mode"][0]
        for w in mode_frame.winfo_children():
            w.destroy()
        ctk.CTkLabel(mode_frame, text=" 模式", font=("Microsoft YaHei", 11), text_color="#94A3B8").pack(anchor="w", padx=14, pady=(10, 0))
        sw_frame = ctk.CTkFrame(mode_frame, fg_color="transparent")
        sw_frame.pack(anchor="w", padx=14, pady=(4, 10))
        self._mode_switch = ctk.CTkSegmentedButton(sw_frame, values=["App", "Web"], selected_color="#6366F1", selected_hover_color="#4F46E5", command=self._on_mode_change)
        self._mode_switch.pack()
        self._mode_switch.set("App")

    def _content_area(self) -> None:
        main = ctk.CTkFrame(self.root, corner_radius=12, border_width=0)
        main.grid(row=2, column=0, sticky="nsew", padx=24, pady=(16, 0))
        main.grid_columnconfigure(0, weight=3, uniform="content")
        main.grid_columnconfigure(1, weight=2, uniform="content")
        main.grid_rowconfigure(0, weight=1)

        self._left_panel = ctk.CTkScrollableFrame(main, corner_radius=12, border_width=0, fg_color="transparent")
        self._left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self._left_panel.grid_columnconfigure(0, weight=1)
        self._left_panel.after(50, self._fix_left_panel_scroll)

        right = ctk.CTkFrame(main, corner_radius=12, border_width=0)
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        log_header = ctk.CTkFrame(right, fg_color="transparent", height=36)
        log_header.grid(row=0, column=0, sticky="ew", pady=(12, 0), padx=12)
        log_header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(log_header, text="\u2192 运行日志", font=("Microsoft YaHei", 13, "bold"), anchor="w").grid(row=0, column=0, sticky="w")
        filter_entry = ctk.CTkEntry(log_header, placeholder_text="  过滤...", width=140, height=28, corner_radius=8)
        filter_entry.grid(row=0, column=2, sticky="e", padx=(8, 0))
        filter_entry.bind("<KeyRelease>", lambda e: self._on_filter(e, filter_entry))

        self._log_box = ctk.CTkTextbox(right, corner_radius=10, border_width=0, wrap="word", font=("Consolas", 12))
        self._log_box.grid(row=1, column=0, sticky="nsew", padx=12, pady=(8, 12))
        self._log_box.configure(state="disabled")
        self._log_mgr = LogManager(self._log_box)

        self._rebuild_config_panel()

    def _on_filter(self, event, entry: ctk.CTkEntry) -> None:
        self._log_mgr.set_filter(entry.get().strip())

    def _rebuild_config_panel(self) -> None:
        if self._schedule_running:
            self._cancel_schedule()
        for w in self._left_panel.winfo_children():
            w.destroy()
        if self._current_mode == "app":
            self._build_app_config()
        else:
            self._build_web_config()

    def _fix_left_panel_scroll(self) -> None:
        try:
            canvas = self._left_panel._parent_canvas
            canvas.configure(yscrollincrement=4)
            canvas.bind("<MouseWheel>",
                        lambda e: canvas.yview_scroll(int(-e.delta / 3), "units"), add="+")
        except Exception:
            pass

    def _build_app_config(self) -> None:
        self._build_env_card()

        card = ctk.CTkFrame(self._left_panel, corner_radius=12)
        card.pack(fill="x", pady=(0, 6))
        hdr = ctk.CTkFrame(card, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(14, 4))
        ctk.CTkLabel(hdr, text="\uD83D\uDCF1 Appium 服务", font=("Microsoft YaHei", 14, "bold")).pack(side="left")
        appium_collapsed = [False]
        toggle_btn = ctk.CTkButton(hdr, text="\u25B2", width=24, height=22,
                                   fg_color="transparent", text_color=("#1E293B", "#F1F5F9"),
                                   hover_color="#E2E8F0", corner_radius=4)
        toggle_btn.pack(side="left", padx=(4, 0))

        sf = ctk.CTkFrame(card, fg_color="transparent")
        sf.pack(fill="x", padx=16, pady=(0, 14))
        sf.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(sf, text="服务地址", font=("Microsoft YaHei", 12)).grid(row=0, column=0, sticky="w", pady=3)
        self._server_url = ctk.CTkEntry(sf, height=32, placeholder_text="http://127.0.0.1:4723")
        self._server_url.grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=3)

        ctk.CTkLabel(sf, text="设备 UDID", font=("Microsoft YaHei", 12)).grid(row=1, column=0, sticky="w", pady=3)
        self._udid_entry = ctk.CTkEntry(sf, height=32, placeholder_text="adb devices 获取")
        self._udid_entry.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=3)

        device_btn_frame = ctk.CTkFrame(sf, fg_color="transparent")
        device_btn_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self._refresh_device_btn = ctk.CTkButton(device_btn_frame, text="\uD83D\uDD04 刷新设备", height=30, command=self._refresh_devices, fg_color="#0EA5E9", hover_color="#0284C7")
        self._refresh_device_btn.pack(side="left")
        self._device_info = ctk.CTkLabel(device_btn_frame, text="", text_color="#94A3B8", anchor="w")
        self._device_info.pack(side="left", padx=(10, 0))

        def _toggle_appium():
            appium_collapsed[0] = not appium_collapsed[0]
            if appium_collapsed[0]:
                sf.pack_forget()
                toggle_btn.configure(text="\u25BC")
            else:
                sf.pack(fill="x", padx=16, pady=(0, 14))
                toggle_btn.configure(text="\u25B2")
        toggle_btn.configure(command=_toggle_appium)

        self._build_params_card()
        self._build_schedule_card()
        self._build_advanced_card()
        self._build_config_mgr_card()

    def _build_web_config(self) -> None:
        self._build_env_card()

        card = ctk.CTkFrame(self._left_panel, corner_radius=12)
        card.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(card, text="\uD83C\uDF10 网页配置", font=("Microsoft YaHei", 14, "bold")).pack(anchor="w", padx=16, pady=(14, 4))
        wf = ctk.CTkFrame(card, fg_color="transparent")
        wf.pack(fill="x", padx=16, pady=(0, 14))
        wf.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(wf, text="目标 URL", font=("Microsoft YaHei", 12)).grid(row=0, column=0, sticky="w", pady=3)
        self._web_url_entry = ctk.CTkEntry(wf, height=32, placeholder_text="https://detail.damai.cn/...")
        self._web_url_entry.insert(0, "https://detail.damai.cn/")
        self._web_url_entry.grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=3)

        ctk.CTkLabel(wf, text="关键词", font=("Microsoft YaHei", 12)).grid(row=1, column=0, sticky="w", pady=3)
        self._keyword_entry = ctk.CTkEntry(wf, height=32, placeholder_text="演出名称/关键词")
        self._keyword_entry.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=3)

        ctk.CTkLabel(wf, text="城市", font=("Microsoft YaHei", 12)).grid(row=2, column=0, sticky="w", pady=3)
        self._city_entry = ctk.CTkEntry(wf, height=32, placeholder_text="例: 上海")
        self._city_entry.grid(row=2, column=1, sticky="ew", padx=(8, 0), pady=3)

        ctk.CTkLabel(wf, text="日期", font=("Microsoft YaHei", 12)).grid(row=3, column=0, sticky="w", pady=3)
        self._date_picker = DatePickerCtk(wf)
        self._date_picker.grid(row=3, column=1, sticky="ew", padx=(8, 0), pady=3)

        ctk.CTkLabel(wf, text="价格档位", font=("Microsoft YaHei", 12)).grid(row=4, column=0, sticky="w", pady=3)
        self._web_price_entry = ctk.CTkEntry(wf, height=32, placeholder_text="例: 580(可留空)")
        self._web_price_entry.grid(row=4, column=1, sticky="ew", padx=(8, 0), pady=3)

        cookie_row = ctk.CTkFrame(wf, fg_color="transparent")
        cookie_row.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self._clear_cookie_btn = ctk.CTkButton(
            cookie_row, text="\uD83D\uDDD1 清除登录状态", height=30,
            fg_color="#EF4444", hover_color="#DC2626",
            command=self._clear_cookies,
        )
        self._clear_cookie_btn.pack(side="left")
        self._cookie_status = ctk.CTkLabel(
            cookie_row, text="", text_color="#94A3B8", anchor="w",
        )
        self._cookie_status.pack(side="left", padx=(10, 0))
        self._refresh_cookie_status()

        self._build_config_mgr_card()

    def _build_env_card(self) -> None:
        card = ctk.CTkFrame(self._left_panel, corner_radius=12)
        card.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(card, text="\u2699\uFE0F 环境检测", font=("Microsoft YaHei", 14, "bold")).pack(anchor="w", padx=16, pady=(14, 4))
        env_frame = ctk.CTkFrame(card, fg_color="transparent")
        env_frame.pack(fill="x", padx=16, pady=(0, 14))
        self._env_btn = ctk.CTkButton(env_frame, text="\uD83D\uDD0D 检测环境", height=34, command=self._check_env)
        self._env_btn.pack(side="left")
        self._env_status = ctk.CTkLabel(env_frame, text="等待检测", text_color="#94A3B8", anchor="w")
        self._env_status.pack(side="left", padx=(12, 0))

    def _build_params_card(self) -> None:
        card2 = ctk.CTkFrame(self._left_panel, corner_radius=12)
        card2.pack(fill="x", pady=(0, 3))
        hdr = ctk.CTkFrame(card2, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(14, 4))

        title_lbl = ctk.CTkLabel(hdr, text="\uD83C\uDFA4 抢票参数", font=("Microsoft YaHei", 14, "bold"), anchor="w")
        title_lbl.pack(side="left")
        params_collapsed = [False]
        toggle_btn = ctk.CTkButton(hdr, text="\u25B2", width=24, height=22,
                                   fg_color="transparent", text_color=("#1E293B", "#F1F5F9"),
                                   hover_color="#E2E8F0", corner_radius=4)
        toggle_btn.pack(side="left", padx=(4, 0))

        pf = ctk.CTkFrame(card2, fg_color="transparent")
        pf.pack(fill="x", padx=16, pady=(0, 14))
        pf.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(pf, text="关键词", font=("Microsoft YaHei", 12)).grid(row=0, column=0, sticky="w", pady=3)
        self._keyword_entry = ctk.CTkEntry(pf, height=32, placeholder_text="演出名称/关键词")
        self._keyword_entry.grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=3)

        ctk.CTkLabel(pf, text="城市", font=("Microsoft YaHei", 12)).grid(row=1, column=0, sticky="w", pady=3)
        self._city_entry = ctk.CTkEntry(pf, height=32, placeholder_text="例: 上海")
        self._city_entry.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=3)

        ctk.CTkLabel(pf, text="场次索引", font=("Microsoft YaHei", 12)).grid(row=2, column=0, sticky="w", pady=3)
        self._session_idx = ctk.CTkEntry(pf, height=32, placeholder_text="从 0 开始")
        self._session_idx.grid(row=2, column=1, sticky="ew", padx=(8, 0), pady=3)

        ctk.CTkLabel(pf, text="票价索引", font=("Microsoft YaHei", 12)).grid(row=3, column=0, sticky="w", pady=3)
        self._price_idx = ctk.CTkEntry(pf, height=32, placeholder_text="从 0 开始")
        self._price_idx.grid(row=3, column=1, sticky="ew", padx=(8, 0), pady=3)

        ctk.CTkLabel(pf, text="购票数量", font=("Microsoft YaHei", 12)).grid(row=4, column=0, sticky="w", pady=3)
        self._quantity_entry = ctk.CTkEntry(pf, height=32, placeholder_text="1-6")
        self._quantity_entry.grid(row=4, column=1, sticky="ew", padx=(8, 0), pady=3)
        self._quantity_entry.insert(0, "1")

        opt_frame = ctk.CTkFrame(pf, fg_color="transparent")
        opt_frame.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self._commit_switch = ctk.CTkSwitch(opt_frame, text="自动提交订单", onvalue=True, offvalue=False)
        self._commit_switch.pack(side="left")
        self._commit_switch.select()

        def _toggle_params():
            params_collapsed[0] = not params_collapsed[0]
            if params_collapsed[0]:
                pf.pack_forget()
                toggle_btn.configure(text="\u25BC")
            else:
                pf.pack(fill="x", padx=16, pady=(0, 14))
                toggle_btn.configure(text="\u25B2")
        toggle_btn.configure(command=_toggle_params)

    def _build_schedule_card(self) -> None:
        card3 = ctk.CTkFrame(self._left_panel, corner_radius=12)
        card3.pack(fill="x", pady=(0, 3))
        hdr = ctk.CTkFrame(card3, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(14, 4))
        title_lbl = ctk.CTkLabel(hdr, text="\u23F0 定时抢票", font=("Microsoft YaHei", 14, "bold"), anchor="w")
        title_lbl.pack(side="left")
        sched_collapsed = [False]
        toggle_btn = ctk.CTkButton(hdr, text="\u25B2", width=24, height=22,
                                   fg_color="transparent", text_color=("#1E293B", "#F1F5F9"),
                                   hover_color="#E2E8F0", corner_radius=4)
        toggle_btn.pack(side="left", padx=(4, 0))

        tf = ctk.CTkFrame(card3, fg_color="transparent")
        tf.pack(fill="x", padx=16, pady=(0, 14))
        tf.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(tf, text="开抢时间", font=("Microsoft YaHei", 12)).grid(row=0, column=0, sticky="w", pady=3)
        self._schedule_picker = DatePickerCtk(tf)
        self._schedule_picker.grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=3)

        ctk.CTkLabel(tf, text="预热秒数", font=("Microsoft YaHei", 12)).grid(row=1, column=0, sticky="w", pady=3)
        self._warmup_spin = ctk.CTkEntry(tf, height=32, placeholder_text="120")
        self._warmup_spin.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=3)
        self._warmup_spin.insert(0, "120")

        sch_btn_frame = ctk.CTkFrame(tf, fg_color="transparent")
        sch_btn_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self._schedule_btn = ctk.CTkButton(sch_btn_frame, text="\u23F0 预约开抢", height=30, command=self._on_schedule, fg_color="#F59E0B", hover_color="#D97706")
        self._schedule_btn.pack(side="left", padx=(0, 8))
        self._schedule_cancel_btn = ctk.CTkButton(sch_btn_frame, text="\u274C 取消", height=30, command=self._cancel_schedule, fg_color="#64748B", hover_color="#475569")
        self._schedule_cancel_btn.pack(side="left")

        self._schedule_status = ctk.CTkLabel(tf, text="", text_color="#94A3B8", anchor="w")
        self._schedule_status.grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))

        def _toggle_sched():
            sched_collapsed[0] = not sched_collapsed[0]
            if sched_collapsed[0]:
                tf.pack_forget()
                toggle_btn.configure(text="\u25BC")
            else:
                tf.pack(fill="x", padx=16, pady=(0, 14))
                toggle_btn.configure(text="\u25B2")
        toggle_btn.configure(command=_toggle_sched)

    def _build_advanced_card(self) -> None:
        adv_card = ctk.CTkFrame(self._left_panel, corner_radius=12)
        adv_card.pack(fill="x", pady=(0, 3))
        hdr = ctk.CTkFrame(adv_card, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(14, 4))
        title_lbl = ctk.CTkLabel(hdr, text="\u2699 高级选项", font=("Microsoft YaHei", 14, "bold"), anchor="w")
        title_lbl.pack(side="left")
        adv_collapsed = [False]
        toggle_btn = ctk.CTkButton(hdr, text="\u25B2", width=24, height=22,
                                   fg_color="transparent", text_color=("#1E293B", "#F1F5F9"),
                                   hover_color="#E2E8F0", corner_radius=4)
        toggle_btn.pack(side="left", padx=(4, 0))

        af = ctk.CTkFrame(adv_card, fg_color="transparent")
        af.pack(fill="x", padx=16, pady=(0, 14))
        af.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(af, text="等待超时(s)", font=("Microsoft YaHei", 12)).grid(row=0, column=0, sticky="w", pady=3)
        self._wait_timeout_entry = ctk.CTkEntry(af, height=32, width=80)
        self._wait_timeout_entry.grid(row=0, column=1, sticky="w", padx=(8, 0), pady=3)
        self._wait_timeout_entry.insert(0, "2.0")

        ctk.CTkLabel(af, text="重试间隔(s)", font=("Microsoft YaHei", 12)).grid(row=1, column=0, sticky="w", pady=3)
        self._retry_delay_entry = ctk.CTkEntry(af, height=32, width=80)
        self._retry_delay_entry.grid(row=1, column=1, sticky="w", padx=(8, 0), pady=3)
        self._retry_delay_entry.insert(0, "1.5")

        ctk.CTkLabel(af, text="最大重试", font=("Microsoft YaHei", 12)).grid(row=2, column=0, sticky="w", pady=3)
        self._retries_entry = ctk.CTkEntry(af, height=32, width=80)
        self._retries_entry.grid(row=2, column=1, sticky="w", padx=(8, 0), pady=3)
        self._retries_entry.insert(0, "3")

        def _toggle_adv():
            adv_collapsed[0] = not adv_collapsed[0]
            if adv_collapsed[0]:
                af.pack_forget()
                toggle_btn.configure(text="\u25BC")
            else:
                af.pack(fill="x", padx=16, pady=(0, 14))
                toggle_btn.configure(text="\u25B2")
        toggle_btn.configure(command=_toggle_adv)

    def _build_config_mgr_card(self) -> None:
        card = ctk.CTkFrame(self._left_panel, corner_radius=12)
        card.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(card, text="\uD83D\uDCC1 配置管理", font=("Microsoft YaHei", 14, "bold")).pack(anchor="w", padx=16, pady=(14, 4))
        mgr = ctk.CTkFrame(card, fg_color="transparent")
        mgr.pack(fill="x", padx=16, pady=(0, 14))
        self._save_cfg_btn = ctk.CTkButton(mgr, text="\uD83D\uDCBE 保存配置", height=30, command=self._save_config_to_file, fg_color="#22C55E", hover_color="#16A34A")
        self._save_cfg_btn.pack(side="left", padx=(0, 8))
        self._load_cfg_btn = ctk.CTkButton(mgr, text="\uD83D\uDCC2 加载配置", height=30, command=self._load_config_from_file, fg_color="#6366F1", hover_color="#4F46E5")
        self._load_cfg_btn.pack(side="left")
        self._cfg_status = ctk.CTkLabel(mgr, text="", text_color="#94A3B8", anchor="w")
        self._cfg_status.pack(side="left", padx=(10, 0))

    def _load_config_from_file(self) -> None:
        path = self._config_path
        if not path.exists():
            self._cfg_status.configure(text="未找到配置文件")
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self._populate_from_dict(data)
            self._cfg_status.configure(text="\u2713 已加载", text_color="#22C55E")
            self.log(f"配置已加载: {path.name}", "success")
        except Exception as e:
            self._cfg_status.configure(text=f"\u2717 {e}", text_color="#EF4444")
            self.log(f"配置加载失败: {e}", "error")

    def _save_config_to_file(self) -> None:
        data = self._collect_dict()
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            self._config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            self._cfg_status.configure(text="\u2713 已保存", text_color="#22C55E")
            self.log(f"配置已保存: {self._config_path}", "success")
        except Exception as e:
            self._cfg_status.configure(text=f"\u2717 {e}", text_color="#EF4444")
            self.log(f"配置保存失败: {e}", "error")

    def _refresh_cookie_status(self) -> None:
        path = Path(self._cookie_file)
        if path.exists():
            size = path.stat().st_size
            self._cookie_status.configure(text=f"已登录 ({size/1024:.1f}KB)", text_color="#22C55E")
        else:
            self._cookie_status.configure(text="未登录", text_color="#94A3B8")

    def _clear_cookies(self) -> None:
        path = Path(self._cookie_file)
        try:
            if path.exists():
                path.unlink()
                self.log("登录状态已清除", "success")
            else:
                self.log("没有已保存的登录状态", "info")
            self._refresh_cookie_status()
        except Exception as e:
            self.log(f"清除登录状态失败: {e}", "error")

    def _save_web_cookies(self) -> None:
        if not self._driver:
            return
        try:
            import pickle
            cookies = self._driver.get_cookies()
            path = Path(self._cookie_file)
            path.write_bytes(pickle.dumps(cookies))
            self._last_cookie_save = time.time()
        except Exception:
            pass

    def _populate_from_dict(self, data: dict) -> None:
        def _safe_get(d, *keys):
            for k in keys:
                if isinstance(d, dict):
                    d = d.get(k)
                else:
                    return None
            return d

        def _set_entry(w, val):
            try:
                w.delete(0, "end")
                w.insert(0, str(val))
            except Exception:
                pass

        def _set_picker(w, val):
            try:
                w.set(str(val))
            except Exception:
                pass

        sv = _safe_get(data, "server_url") or ""
        if sv:
            _set_entry(self._server_url, sv)
        udid = _safe_get(data, "device_caps", "udid") or ""
        if udid:
            _set_entry(self._udid_entry, udid)
        url = _safe_get(data, "target_url") or ""
        if url:
            _set_entry(self._web_url_entry, url)
        kw = _safe_get(data, "keyword") or ""
        if kw:
            _set_entry(self._keyword_entry, kw)
        city = _safe_get(data, "city") or ""
        if city:
            _set_entry(self._city_entry, city)
        try:
            _set_picker(self._date_picker, _safe_get(data, "date") or "")
        except AttributeError:
            pass
        p = _safe_get(data, "price") or ""
        if p:
            _set_entry(self._web_price_entry, p)

        si = _safe_get(data, "session_index")
        if si is not None:
            _set_entry(self._session_idx, si)
        pi = _safe_get(data, "price_index")
        if pi is not None:
            _set_entry(self._price_idx, pi)
        qty = _safe_get(data, "ticket_quantity")
        if qty is not None:
            _set_entry(self._quantity_entry, qty)

        commit = _safe_get(data, "if_commit_order")
        if commit is not None:
            try:
                if commit:
                    self._commit_switch.select()
                else:
                    self._commit_switch.deselect()
            except Exception:
                pass

        wt = _safe_get(data, "wait_timeout")
        if wt is not None:
            _set_entry(self._wait_timeout_entry, wt)
        rd = _safe_get(data, "retry_delay")
        if rd is not None:
            _set_entry(self._retry_delay_entry, rd)
        ret = _safe_get(data, "max_retries")
        if ret is not None:
            _set_entry(self._retries_entry, ret)

        date_val = _safe_get(data, "date") or ""
        sch = _safe_get(data, "schedule_time") or date_val or ""
        if sch:
            _set_picker(self._schedule_picker, sch)
        wp = _safe_get(data, "warmup_sec")
        if wp is not None:
            _set_entry(self._warmup_spin, wp)

    def _collect_dict(self) -> dict:
        d: dict = {}
        def _wget(w, default=""):
            try:
                return w.get().strip()
            except Exception:
                return default

        if self._current_mode == "app":
            sv = _wget(self._server_url, "http://127.0.0.1:4723")
            d["server_url"] = sv or "http://127.0.0.1:4723"
            udid = _wget(self._udid_entry)
            if udid:
                d["device_caps"] = {"udid": udid, "automationName": "UiAutomator2"}
        else:
            url = _wget(self._web_url_entry)
            if url:
                d["target_url"] = url
            p = _wget(self._web_price_entry)
            if p:
                d["price"] = p

        try:
            _dt = _wget(self._date_picker)
            if _dt:
                d["date"] = _dt
        except AttributeError:
            pass
        kw = _wget(self._keyword_entry)
        if kw:
            d["keyword"] = kw
        city = _wget(self._city_entry)
        if city:
            d["city"] = city


        si = _wget(self._session_idx)
        if si:
            try:
                d["session_index"] = int(si)
            except ValueError:
                pass
        pi = _wget(self._price_idx)
        if pi:
            try:
                d["price_index"] = int(pi)
            except ValueError:
                pass
        qty = _wget(self._quantity_entry)
        if qty:
            try:
                d["ticket_quantity"] = int(qty)
            except ValueError:
                pass

        try:
            d["if_commit_order"] = bool(self._commit_switch.get())
        except Exception:
            pass

        wt = _wget(self._wait_timeout_entry)
        if wt:
            try:
                d["wait_timeout"] = float(wt)
            except ValueError:
                pass
        rd = _wget(self._retry_delay_entry)
        if rd:
            try:
                d["retry_delay"] = float(rd)
            except ValueError:
                pass
        ret = _wget(self._retries_entry)
        if ret:
            try:
                d["max_retries"] = int(ret)
            except ValueError:
                pass

        sch = _wget(self._schedule_picker)
        if sch:
            d["schedule_time"] = sch
        wp = _wget(self._warmup_spin)
        if wp:
            try:
                d["warmup_sec"] = int(wp)
            except ValueError:
                pass
        d["users"] = []
        return d

    def _footer(self) -> None:
        f = ctk.CTkFrame(self.root, fg_color="transparent", height=64)
        f.grid(row=3, column=0, sticky="ew", padx=24, pady=(12, 16))
        f.grid_columnconfigure(0, weight=1)

        btn_frame = ctk.CTkFrame(f, fg_color="transparent")
        btn_frame.pack(anchor="center")

        self._start_btn = ctk.CTkButton(
            btn_frame, text="\uD83C\uDFAF 开始抢票", height=42, width=180,
            font=("Microsoft YaHei", 14, "bold"), corner_radius=12,
            fg_color="#3B82F6", hover_color="#2563EB",
            command=self._on_start,
        )
        self._start_btn.pack(side="left", padx=6)

        self._stop_btn = ctk.CTkButton(
            btn_frame, text="\u23F8 停止", height=42, width=100,
            font=("Microsoft YaHei", 14, "bold"), corner_radius=12,
            fg_color=["#FEF2F2", "#450A0A"], text_color=["#EF4444", "#FCA5A5"],
            border_width=2, border_color=["#EF4444", "#FCA5A5"],
            hover_color=["#FEE2E2", "#7F1D1D"], state="disabled",
            command=self._on_stop,
        )
        self._stop_btn.pack(side="left", padx=6)

        self._clear_log_btn = ctk.CTkButton(
            btn_frame, text="\uD83D\uDDD1 清空日志", height=34, width=100,
            font=("Microsoft YaHei", 12), corner_radius=10,
            fg_color="#64748B", hover_color="#475569",
            command=self._clear_log,
        )
        self._clear_log_btn.pack(side="left", padx=6)

        self._export_btn = ctk.CTkButton(
            btn_frame, text="\uD83D\uDCE4 导出日志", height=34, width=100,
            font=("Microsoft YaHei", 12), corner_radius=10,
            fg_color="#64748B", hover_color="#475569",
            command=self._export_log,
        )
        self._export_btn.pack(side="left", padx=6)

    def _bind_events(self) -> None:
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ============================
    # EVENTS
    # ============================
    def _on_mode_change(self, val: str) -> None:
        self._current_mode = val.lower()
        self._update_status("mode", val, "#6366F1")
        self.log(f"切换到 {val} 模式", "info")
        self._rebuild_config_panel()
        self._load_config_from_file()

    def _toggle_theme(self) -> None:
        current = ctk.get_appearance_mode()
        ctk.set_appearance_mode("Dark" if current == "Light" else "Light")
        self.log(f"主题切换为 {ctk.get_appearance_mode()}", "info")

    def _on_close(self) -> None:
        self._should_stop = True
        if self._driver:
            try:
                self._driver.quit()
            except Exception:
                pass
        self.root.destroy()

    # ============================
    # STATUS UPDATES
    # ============================
    def _update_status(self, key: str, text: str, color: str = "#94A3B8") -> None:
        if key in self._status_labels:
            _, _, lbl = self._status_labels[key]
            try:
                lbl.configure(text=text, text_color=color)
            except Exception:
                pass

    def _set_status_ok(self, key: str, text: str) -> None:
        self._update_status(key, text, "#22C55E")

    def _set_status_warn(self, key: str, text: str) -> None:
        self._update_status(key, text, "#F59E0B")

    def _set_status_err(self, key: str, text: str) -> None:
        self._update_status(key, text, "#EF4444")

    # ============================
    # LOG
    # ============================
    def log(self, message: str, level: str = "info") -> None:
        self._log_mgr.add(message, level)

    def _clear_log(self) -> None:
        self._log_mgr.clear()
        self.log("日志已清空", "info")

    def _export_log(self) -> None:
        try:
            from tkinter import filedialog
            path = filedialog.asksaveasfilename(
                defaultextension=".json",
                filetypes=[("JSON", "*.json")],
                initialfile=f"damai_log_{datetime.now():%Y%m%d_%H%M%S}.json",
            )
            if not path:
                return
            payload = {
                "exported_at": datetime.now().isoformat(),
                "entries": [
                    {"time": t, "message": m, "level": l}
                    for t, m, l in self._log_mgr.entries
                ],
                "report": self._last_app_report.to_dict() if self._last_app_report else None,
            }
            Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            self.log(f"日志已导出: {path}", "success")
        except Exception as e:
            self.log(f"导出失败: {e}", "error")

    # ============================
    # ENV CHECK
    # ============================
    def _check_env(self) -> None:
        self._env_btn.configure(state="disabled", text="检测中...")
        self._env_status.configure(text="检测中...", text_color="#F59E0B")
        self.log("开始环境检测...", "info")
        threading.Thread(target=self._env_worker, daemon=True).start()

    def _env_worker(self) -> None:
        try:
            py_ver = sys.version.split()[0]
            self.log(f"Python {py_ver}", "success")

            if self._current_mode == "app":
                self._check_app_env()
            else:
                self._check_web_env()

            self._update_status("env", "\u2713 就绪", "#22C55E")
            self._env_status.configure(text="\u2713 环境正常", text_color="#22C55E")
            self.log("环境检测通过", "success")
        except Exception as e:
            self._update_status("env", "\u2717 失败", "#EF4444")
            self._env_status.configure(text=f"\u2717 {e}", text_color="#EF4444")
            self.log(f"环境检测失败: {e}", "error")
        finally:
            try:
                self._env_btn.configure(state="normal", text="\uD83D\uDD0D 检测环境")
            except Exception:
                pass

    def _check_app_env(self) -> None:
        import urllib.request
        from urllib.error import URLError

        if not APPIUM_AVAILABLE:
            raise RuntimeError("Appium 依赖未安装: pip install Appium-Python-Client")

        url_val = self._server_url.get().strip() or "http://127.0.0.1:4723"
        status_url = url_val.rstrip("/") + "/status"
        try:
            with urllib.request.urlopen(status_url, timeout=5) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"Appium 返回 {resp.status}")
            self.log(f"Appium {url_val} 响应正常", "success")
        except URLError as e:
            raise RuntimeError(f"无法连接 Appium: {e.reason}") from e

    def _check_web_env(self) -> None:
        if not SELENIUM_AVAILABLE:
            raise RuntimeError("Selenium 未安装")
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        d = webdriver.Chrome(options=options)
        d.quit()
        self.log("ChromeDriver 正常", "success")

    # ============================
    # DEVICES
    # ============================
    def _refresh_devices(self) -> None:
        self._refresh_device_btn.configure(state="disabled", text="刷新中...")
        self._device_info.configure(text="检测中...")
        threading.Thread(target=self._device_worker, daemon=True).start()

    def _device_worker(self) -> None:
        try:
            result = subprocess.run(
                ["adb", "devices", "-l"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0 or not result.stdout:
                raise RuntimeError("adb 执行失败")
            devices = parse_adb_devices(result.stdout) if parse_adb_devices else []
            ready = [d for d in devices if d.is_ready]
            if not ready:
                raise RuntimeError("未发现可用设备")
            self._detected_devices = [d.serial for d in ready]
            first = ready[0]

            if not self._udid_entry.get().strip():
                self._udid_entry.delete(0, "end")
                self._udid_entry.insert(0, first.serial)

            self._device_info.configure(text=f"{len(ready)} 台设备就绪", text_color="#22C55E")
            self._update_status("device", f"{len(ready)} 台在线", "#22C55E")
            self.log(f"设备: {', '.join(d.serial for d in ready)}", "success")
        except Exception as e:
            self._device_info.configure(text=str(e), text_color="#EF4444")
            self._update_status("device", "未连接", "#EF4444")
            self.log(f"设备检测: {e}", "warning")
        finally:
            try:
                self._refresh_device_btn.configure(state="normal", text="\uD83D\uDD04 刷新设备")
            except Exception:
                pass

    # ============================
    # COLLECT CONFIG
    # ============================
    def _collect_config(self) -> Optional[Any]:
        server_url = self._server_url.get().strip() or "http://127.0.0.1:4723"
        keyword = self._keyword_entry.get().strip() or None
        city = self._city_entry.get().strip() or None
        date = (self._schedule_picker.get().strip() or None) if hasattr(self, "_schedule_picker") else None

        session_raw = self._session_idx.get().strip()
        session_index = int(session_raw) if session_raw else 0

        price_raw = self._price_idx.get().strip()
        price_index = int(price_raw) if price_raw else 0

        qty_raw = self._quantity_entry.get().strip()
        ticket_quantity = int(qty_raw) if qty_raw else 1

        udid = self._udid_entry.get().strip()
        device_caps = {"udid": udid, "automationName": "UiAutomator2"} if udid else {"automationName": "UiAutomator2"}

        try:
            wait_timeout = float(self._wait_timeout_entry.get().strip() or 2.0)
        except ValueError:
            wait_timeout = 2.0
        try:
            retry_delay = float(self._retry_delay_entry.get().strip() or 1.5)
        except ValueError:
            retry_delay = 1.5
        try:
            self._app_retries = int(self._retries_entry.get().strip() or 3)
        except ValueError:
            self._app_retries = 3
        self._if_commit_order = bool(self._commit_switch.get())
        try:
            self._warmup_sec = int(self._warmup_spin.get().strip() or 120)
        except ValueError:
            self._warmup_sec = 120

        if AppTicketConfig is None:
            return None

        payload = {
            "server_url": server_url,
            "keyword": keyword,
            "city": city,
            "date": date,
            "session_index": session_index,
            "price_index": price_index,
            "ticket_quantity": ticket_quantity,
            "if_commit_order": self._if_commit_order,
            "device_caps": device_caps,
            "wait_timeout": wait_timeout,
            "retry_delay": retry_delay,
            "warmup_sec": self._warmup_sec,
            "users": [],
        }
        self._config_payload = payload
        return AppTicketConfig.from_mapping(payload)

    # ============================
    # SCHEDULE
    # ============================
    def _on_schedule(self) -> None:
        raw = self._schedule_picker.get().strip()
        if not raw:
            self.log("请填写开抢时间", "warning")
            return
        try:
            target = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            try:
                target = datetime.strptime(raw, "%Y-%m-%d %H:%M")
            except ValueError:
                self.log(f"时间格式错误: {raw}，使用 YYYY-MM-DD HH:MM:SS", "error")
                return

        now = datetime.now()
        if target <= now:
            self.log("开抢时间不能早于当前时间", "warning")
            return

        self._sprint_target_epoch = target.timestamp()
        self._schedule_running = True
        self._preheat_executed = False
        self._schedule_btn.configure(state="disabled")

        cfg = self._collect_config()
        self.log(f"已预约: {raw}", "success")
        self._schedule_status.configure(text=f"等待至 {raw}...")
        self._schedule_tick()

    def _cancel_schedule(self) -> None:
        self._schedule_running = False
        self._preheat_executed = False
        self._sprint_target_epoch = None
        if self._schedule_timer_id:
            try:
                self.root.after_cancel(self._schedule_timer_id)
            except Exception:
                pass
            self._schedule_timer_id = None
        self._schedule_btn.configure(state="normal")
        self._schedule_status.configure(text="")
        self.log("已取消预约", "info")

    def _schedule_tick(self) -> None:
        if not self._schedule_running or self._sprint_target_epoch is None:
            return

        now = time.time()
        remaining = self._sprint_target_epoch - now
        if remaining <= 0:
            self._schedule_running = False
            self._schedule_btn.configure(state="normal")
            self._schedule_status.configure(text="\u23F0 到点，开始抢票!")
            self.log("到点! 开始抢票", "success")
            self._start_sprint()
            return

        mins, secs = divmod(int(remaining), 60)
        display = f"{mins:02d}:{secs:02d}"
        warmup = max(int(self._warmup_spin.get().strip() or 120), 0)
        self._schedule_status.configure(text=f"倒计时 {display} | 预热 {warmup}s")

        if warmup > 0 and remaining <= warmup and not self._preheat_executed:
            self._preheat_executed = True
            self.log(f"进入预热阶段 ({warmup}s)", "info")
            self._do_preheat()

        self._schedule_timer_id = self.root.after(200, self._schedule_tick)

    def _do_preheat(self) -> None:
        threading.Thread(target=self._preheat_worker, daemon=True).start()

    def _preheat_worker(self) -> None:
        try:
            config = self._collect_config()
            if config is None:
                self.log("预热: 配置无效", "error")
                return
            self._app_runner = DamaiAppTicketRunner(
                config=config,
                logger=lambda l, m, c=None: self.log(f"[预热] {m}", l),
                stop_signal=lambda: self._should_stop,
            )
            self._app_runner.preheat()
            self.log("预热完成! 已进入选票页", "success")
            self._update_status("status", "预热就绪", "#22C55E")
        except Exception as e:
            self.log(f"预热失败: {e}", "error")
            self._app_runner = None

    def _start_sprint(self) -> None:
        if self._app_runner is None:
            self.log("没有预热好的 runner，使用普通模式", "warning")
            self._start_normal()
            return

        target = self._sprint_target_epoch
        if target is None:
            self.log("缺少开抢时间戳", "error")
            return

        self._is_grabbing = True
        self._should_stop = False
        self._update_status("status", "冲刺中...", "#3B82F6")
        self._start_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        self.log("启动极速冲刺模式", "info")

        def run():
            try:
                ok = self._app_runner.sprint(target)
                if ok:
                    self.log("抢票成功! 进入付款页", "success")
                    self._update_status("status", "抢票成功!", "#22C55E")
                else:
                    self.log("抢票未成功，尝试传统模式", "warning")
                    self._app_runner.run(max_retries=self._app_retries)
            except Exception as e:
                self.log(f"冲刺异常: {e}", "error")
                self._update_status("status", "异常", "#EF4444")
            finally:
                self._is_grabbing = False
                self._start_btn.configure(state="normal")
                self._stop_btn.configure(state="disabled")

        threading.Thread(target=run, daemon=True).start()

    # ============================
    # START / STOP
    # ============================
    def _on_start(self) -> None:
        if self._schedule_running:
            self.log("已预约定时抢票，等待到点执行", "info")
            return
        self._start_normal()

    def _start_normal(self) -> None:
        if self._current_mode == "app":
            self._start_app()
        else:
            self._start_web()

    def _start_app(self) -> None:
        config = self._collect_config()
        if config is None:
            self.log("AppTicketConfig 不可用，请安装 Appium 依赖", "error")
            return

        self._is_grabbing = True
        self._should_stop = False
        self._update_status("status", "抢票中...", "#3B82F6")
        self._start_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")

        def run():
            try:
                runner = DamaiAppTicketRunner(
                    config=config,
                    logger=lambda l, m, c=None: self.log(m, l),
                    stop_signal=lambda: self._should_stop,
                )
                self._app_runner = runner
                ok = runner.run(max_retries=self._app_retries)
                self._last_app_report = runner.get_last_report()
                if ok:
                    self.log("抢票流程执行完成", "success")
                    self._update_status("status", "已完成", "#22C55E")
                else:
                    self.log("抢票未成功", "warning")
                    self._update_status("status", "未成功", "#F59E0B")
            except Exception as e:
                self.log(f"抢票异常: {e}", "error")
                self._update_status("status", "异常", "#EF4444")
            finally:
                self._is_grabbing = False
                self._start_btn.configure(state="normal")
                self._stop_btn.configure(state="disabled")

        threading.Thread(target=run, daemon=True).start()

    def _start_web(self) -> None:
        self._is_grabbing = True
        self._should_stop = False
        self._update_status("status", "抢票中...", "#3B82F6")
        self._start_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")

        def run():
            try:
                from damai_web import WebConcert
                if not self._driver:
                    options = webdriver.ChromeOptions()
                    options.add_experimental_option("excludeSwitches", ["enable-automation"])
                    options.add_argument("--disable-blink-features=AutomationControlled")
                    self._driver = webdriver.Chrome(options=options)
                    self._driver.get("https://www.damai.cn")
                    self.log("请手动登录大麦网", "warning")
                    target = self._web_url_entry.get().strip() if hasattr(self, "_web_url_entry") else ""
                    if target:
                        self._driver.get(target)
                    time.sleep(2)

                target = self._web_url_entry.get().strip() if hasattr(self, "_web_url_entry") else ""
                config = {
                    "target_url": target,
                    "city": self._city_entry.get().strip() or "",
                    "date": self._schedule_picker.get().strip() if hasattr(self, "_schedule_picker") else "",
                    "price": self._web_price_entry.get().strip() if hasattr(self, "_web_price_entry") else "",
                    "users": [],
                    "if_commit_order": self._if_commit_order,
                    "if_listen": True,
                }
                concert = WebConcert(
                    driver=self._driver, config=config,
                    log_callback=lambda m: self.log(m, "info"),
                    cookie_callback=self._save_web_cookies,
                    stop_check=lambda: self._should_stop,
                )
                concert.choose_ticket()
                self._refresh_cookie_status()
                self.log("Web 抢票流程完成", "success")
                self._update_status("status", "已完成", "#22C55E")
            except Exception as e:
                self.log(f"Web 抢票异常: {e}", "error")
                self._update_status("status", "异常", "#EF4444")
            finally:
                self._is_grabbing = False
                self._start_btn.configure(state="normal")
                self._stop_btn.configure(state="disabled")

        threading.Thread(target=run, daemon=True).start()

    def _on_stop(self) -> None:
        self._should_stop = True
        self._is_grabbing = False
        self.log("正在停止...", "warning")
        self._update_status("status", "已停止", "#F59E0B")
        self._start_btn.configure(state="normal")
        self._stop_btn.configure(state="disabled")

    # ============================
    # RUN
    # ============================
    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    app = DamaiGUI()
    app.run()


if __name__ == "__main__":
    main()
