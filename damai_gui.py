# -*- coding: utf-8 -*-
"""
大麦抢票 GUI 工具
一键from式图形界面抢票工具，适合小白用户使用
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
from comment import DateTimePicker, CountdownTimer
import threading
import subprocess
import sys
import os
import json
import re
import time
import webbrowser
import pickle
from pathlib import Path
import importlib.util
import shutil
from dataclasses import asdict
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timedelta

# 确保能够导入selenium等模块
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.wait import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

# 导入App端运行器（如果可用）
try:
    from damai_appium import (
        AppTicketConfig,
        ConfigValidationError,
        DamaiAppTicketRunner,
        FailureReason,
        LogLevel,
        TicketRunReport,
    )
    from damai_appium.config import AdbDeviceInfo, parse_adb_devices

    APPIUM_AVAILABLE = True
except Exception:  # noqa: BLE001
    AppTicketConfig = None  # type: ignore[assignment]
    ConfigValidationError = None  # type: ignore[assignment]
    DamaiAppTicketRunner = None  # type: ignore[assignment]
    LogLevel = None  # type: ignore[assignment]
    FailureReason = None  # type: ignore[assignment]
    TicketRunReport = None  # type: ignore[assignment]
    AdbDeviceInfo = None  # type: ignore[assignment]
    parse_adb_devices = None  # type: ignore[assignment]
    APPIUM_AVAILABLE = False


class DamaiGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("大麦抢票工具 v3.0.0")
        self.root.geometry("1200x800")  # 调整为适中的尺寸比例
        self.root.resizable(True, True)
        
        # 设置最小窗口尺寸
        self.root.minsize(1000, 650)
        
        # 设置图标（如果有的话）
        try:
            self.root.iconbitmap("icon.ico")
        except:
            pass
        
        # 初始化变量
        self.driver = None
        self.target_url = ""
        self.is_grabbing = False  # 抢票状态标志
        self.config = {
            "city": "",
            "date": "",
            "price": "",
            "users": ["自动选择全部"],
            "if_commit_order": False
        }

        # 模式管理：web / app
        self.mode_var = tk.StringVar(value="web")
        self.steps_config = {
            "web": [
                "1. 环境检测",
                "2. 网页登录",
                "3. 页面分析",
                "4. 参数配置",
                "5. 开始抢票",
            ],
            "app": [
                "1. 环境检测",
                "2. 设备检查",
                "3. 参数配置",
                "4. 开始抢票",
                "5. 查看结果",
            ],
        }
        self.step_status = []
        self.app_config_data = {}
        self.app_loaded_config = None
        self.app_env_ready = False
        self.app_config_ready = False
        self.app_should_stop = False
        self.app_detected_devices: List[str] = []
        self.app_detected_device_records: List[Dict[str, Any]] = []
        self._device_refresh_in_progress = False
        self.app_device_status_var: Optional[tk.StringVar] = None
        self.app_device_detail_var: Optional[tk.StringVar] = None
        self.app_device_options_var: Optional[tk.StringVar] = None
        self.app_device_combobox: Optional[ttk.Combobox] = None
        self.log_entries = []  # type: List[Tuple[str, str, str]]
        self._last_config_errors: List[str] = []
        self.last_app_report = None
        self.log_filter_var = tk.StringVar(value="全部")
        self.app_runner_thread: Optional[threading.Thread] = None
        self._init_app_form_vars()
        self.app_metrics_var = tk.StringVar(value="尚未运行 App 抢票流程")
        # Appium 服务器启动/停止控制状态
        self.appium_process: Optional[subprocess.Popen] = None
        self.appium_pid: Optional[int] = None
        self.appium_running = False
        self.appium_status_var = tk.StringVar(value="Appium 未运行")
        
        # 定时抢票相关变量
        self.schedule_warmup_var = tk.IntVar(value=120)
        self.schedule_status_var = tk.StringVar(value="未预约")
        # 初始化新的倒计时组件
        self.countdown_timer = CountdownTimer(self.root, self.schedule_status_var)
        
        # Cookie管理
        self.cookie_file = "damai_cookies.pkl"
        self.last_cookie_save = time.time()  # 记录上次保存cookie的时间
        
        # 设置字体 - 增加两个号
        self.default_font = ("微软雅黑", 12)  # 从10增加到12
        self.title_font = ("微软雅黑", 18, "bold")  # 从16增加到18
        self.button_font = ("微软雅黑", 11)  # 从9增加到11
        
        # 配置默认字体
        self.root.option_add("*Font", self.default_font)
        
        # 现代化配色方案 - 更协调的色彩搭配
        self.colors = {
            "primary": "#1890ff",
            "primary_light": "#e6f7ff",
            "primary_dark": "#096dd9",
            "success": "#52c41a",
            "success_light": "#f6ffed",
            "warning": "#faad14",
            "warning_light": "#fffbe6",
            "error": "#f5222d",
            "error_dark": "#d91818",
            "error_light": "#fff1f0",
            "info": "#1890ff",
            "info_light": "#e6f7ff",
            "background": "#f0f2f5",  # 更柔和的背景色
            "card_bg": "#ffffff",
            "text_primary": "#262626",
            "text_secondary": "#666666",  # 更清晰的次要文本
            "border": "#e8e8e8",  # 更柔和的边框色
            "border_light": "#f0f0f0",
            "shadow": "#00000014",  # 更自然的阴影效果
        }
        
        # 初始化样式
        self._init_styles()
        
        # 创建主界面
        self.create_interface()
        
        # 自动加载默认配置
        self._setup_auto_config_load()
        
        # 初始环境检测
        if not SELENIUM_AVAILABLE:
            self.log("⚠️ 警告：selenium模块未安装，部分功能可能无法使用")
        
        # 添加Appium状态检测
        self._appium_status_check_interval = 2000  # 2秒检测一次
        self._appium_status_timer_id = None
        self._check_appium_status()  # 立即执行一次状态检查
        self._start_appium_status_check()
    
    def save_cookies(self):
        """保存当前浏览器的cookies到文件"""
        try:
            if self.driver:
                cookies = self.driver.get_cookies()
                with open(self.cookie_file, 'wb') as f:
                    pickle.dump(cookies, f)
                self.last_cookie_save = time.time()  # 更新保存时间
                self.log("✅ Cookie已保存，下次启动时将自动登录")
                return True
        except Exception as e:
            self.log(f"❌ Cookie保存失败: {e}")
        return False
    
    def auto_save_cookies_if_needed(self):
        """如果需要，自动保存cookies（每5分钟保存一次）"""
        try:
            current_time = time.time()
            # 如果距离上次保存超过5分钟，就自动保存
            if self.driver and (current_time - self.last_cookie_save > 300):  # 300秒 = 5分钟
                if self.save_cookies():
                    self.log("🔄 自动保存Cookie（定期保存）")
        except Exception as e:
            self.log(f"⚠️ 自动保存Cookie失败: {e}")
        
        # 设置下次检查（30秒后）
        self.root.after(30000, self.auto_save_cookies_if_needed)
    
    def load_cookies(self):
        """从文件加载cookies到浏览器"""
        try:
            if os.path.exists(self.cookie_file) and self.driver:
                with open(self.cookie_file, 'rb') as f:
                    cookies = pickle.load(f)
                
                # 先访问大麦网主页
                self.driver.get("https://www.damai.cn")
                time.sleep(2)
                
                # 添加所有cookies
                for cookie in cookies:
                    try:
                        self.driver.add_cookie(cookie)
                    except Exception as e:
                        # 某些cookie可能已过期或无效，忽略错误
                        continue
                
                # 刷新页面使cookies生效
                self.driver.refresh()
                time.sleep(2)
                
                # 检查是否登录成功
                if self.check_login_status():
                    self.log("✅ 自动登录成功，使用已保存的登录状态")
                    return True
                else:
                    self.log("⚠️ Cookie已过期，需要重新登录")
                    self.clear_cookies()
                    
        except Exception as e:
            self.log(f"⚠️ Cookie加载失败: {e}")
        return False
    
    def check_login_status(self):
        """检查当前是否已登录"""
        try:
            if not self.driver:
                return False
                
            # 检查是否有登录标识元素
            login_indicators = [
                ".login-after",  # 登录后显示的元素
                ".user-info",    # 用户信息
                ".user-name",    # 用户名
                "[class*='login-after']",
                "[class*='user']"
            ]
            
            for selector in login_indicators:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements and any(elem.is_displayed() for elem in elements):
                        return True
                except:
                    continue
            
            # 检查是否还有"登录"按钮
            login_buttons = self.driver.find_elements(By.XPATH, "//*[contains(text(), '登录') or contains(text(), '登陆')]")
            if not login_buttons:  # 没有登录按钮说明已经登录
                return True
                
            return False
            
        except Exception as e:
            self.log(f"登录状态检查失败: {e}")
            return False
    
    def clear_cookies(self):
        """清除保存的cookies"""
        try:
            if os.path.exists(self.cookie_file):
                os.remove(self.cookie_file)
                self.log("✅ Cookie已清除")
            if self.driver:
                self.driver.delete_all_cookies()
        except Exception as e:
            self.log(f"Cookie清除失败: {e}")
            
    def run(self):
        """启动GUI"""
        self.root.mainloop()
        
    def create_interface(self):
        """创建主界面"""
        # 主框架
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.grid(row=0, column=0, sticky="nsew")
        
        # 配置根窗口网格权重
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        # 调整主区域网格比例：左侧（网页/App模式）更宽，右侧日志稍窄
        main_frame.columnconfigure(0, weight=3)  # 左侧功能面板（Notebook）
        main_frame.columnconfigure(1, weight=2)  # 右侧日志面板

        # 提升“网页模式/App模式”内容区域的可用高度
        main_frame.rowconfigure(0, weight=0)  # 标题行（上方）不增高
        main_frame.rowconfigure(1, weight=0)  # 步骤行（上方）不增高
        main_frame.rowconfigure(2, weight=1)  # 主要功能区域（中间）占据剩余高度
        main_frame.rowconfigure(3, weight=0)  # 控制按钮行（下方）不增高
        
        # 标题区域 - 现代化设计
        title_container = ttk.Frame(main_frame)
        title_container.grid(row=0, column=0, columnspan=2, pady=(0, 20), sticky="we")
        
        title_frame = ttk.Frame(title_container)
        title_frame.pack(fill="x", expand=True)
        title_frame.configure(style="Title.TFrame")
        
        # 添加自定义样式配置
        style = ttk.Style(self.root)
        style.configure(
            "Title.TFrame",
            background=self.colors["primary_light"],
            relief="flat",
            padding="15",
        )
        
        title_label = ttk.Label(title_frame, text="🎫 大麦抢票工具 v3.0.0", font=self.title_font, foreground=self.colors["primary_dark"])
        title_label.pack(anchor="center")
        
        # 步骤显示区域
        self.create_steps_frame(main_frame, row=1)
        
        # 主要功能区域
        self.create_main_functions(main_frame, row=2)
        
        # 控制按钮区域
        self.create_control_buttons(main_frame, row=3)

        # 根据默认模式刷新界面
        self.switch_mode()
        
    def create_steps_frame(self, parent, row):
        """创建步骤显示框架"""
        steps_frame = ttk.LabelFrame(parent, text="📋 操作步骤", padding="10")
        steps_frame.grid(row=row, column=0, columnspan=2, sticky="we", pady=(0, 10))
        
        self.step_labels = []
        max_steps = max(len(steps) for steps in self.steps_config.values())
        for i in range(max_steps):
            label = ttk.Label(steps_frame, text="", foreground="gray", font=self.default_font)
            label.grid(row=0, column=i * 2, padx=5)
            self.step_labels.append(label)

            if i < max_steps - 1:
                sep = ttk.Label(steps_frame, text="→", foreground="gray", font=self.default_font)
                sep.grid(row=0, column=i * 2 + 1, padx=3)

        self.refresh_steps()
    
    def refresh_steps(self):
        """根据当前模式刷新步骤显示"""
        current_mode = self.mode_var.get()
        current_steps = self.steps_config.get(current_mode, [])
        self.steps = current_steps

        # 重置状态并更新标签文本
        self.step_status = ["inactive"] * len(self.step_labels)
        for idx, label in enumerate(self.step_labels):
            if idx < len(current_steps):
                label.config(text=current_steps[idx], foreground="gray")
            else:
                label.config(text="", foreground="gray")

    def create_main_functions(self, parent, row):
        """创建主要功能区域"""
        # 左侧功能面板
        left_frame = ttk.Frame(parent, padding="10", relief="solid", borderwidth=1)
        left_frame.grid(row=row, column=0, sticky="nsew", padx=(0, 5))
        
        # 环境检测区域
        env_container = ttk.Frame(left_frame, padding=(0, 0, 0, 10))
        env_container.pack(fill="x")
        
        # 使用grid布局确保文本和按钮在同一行
        env_container.columnconfigure(1, weight=1)
        
        self.env_status_label = ttk.Label(env_container, text="点击检测环境", foreground=self.colors["warning"], font=self.default_font)
        self.env_status_label.grid(row=0, column=0, sticky="w", padx=(0, 15), pady=2)
        
        self.check_env_btn = ttk.Button(env_container, text="🔍 检测环境", command=self.check_environment)
        self.check_env_btn.grid(row=0, column=1, sticky="w", pady=2)

        # 模式面板容器
        self.mode_notebook = ttk.Notebook(left_frame, style="Modern.TNotebook")
        self.mode_notebook.pack(fill="both", expand=True, pady=(0, 20))

        self.web_panel = ttk.Frame(self.mode_notebook)
        self.app_panel = ttk.Frame(self.mode_notebook)

        self.create_web_panel(self.web_panel)
        self._build_app_panel(self.app_panel)

        self.mode_notebook.add(
            self.web_panel,
            text="🌐 网页模式",
            padding=(20, 15),
        )
        self.mode_notebook.add(
            self.app_panel,
            text="📱 App 模式",
            padding=(20, 15),
        )
        self.mode_notebook.bind("<<NotebookTabChanged>>", self._on_mode_tab_changed)
        
        # 右侧信息面板 - 改为运行日志
        right_frame = ttk.Frame(parent, padding="20", relief="solid", borderwidth=1)
        right_frame.grid(row=row, column=1, sticky="nsew", padx=(10, 0))
        
        log_toolbar = ttk.Frame(right_frame)
        log_toolbar.pack(fill="x", pady=(0, 15))

        ttk.Label(log_toolbar, text="筛选：", font=self.button_font).pack(side="left", padx=(0, 10))
        filter_values = ("全部", "仅信息", "仅成功", "仅警告", "仅错误")
        self.log_filter_combo = ttk.Combobox(
            log_toolbar,
            textvariable=self.log_filter_var,
            values=filter_values,
            state="readonly",
            width=12,
        )
        self.log_filter_combo.current(0)
        self.log_filter_combo.pack(side="left", padx=(4, 20))
        self.log_filter_combo.bind("<<ComboboxSelected>>", self._on_log_filter_changed)

        # 按钮容器
        btn_container = ttk.Frame(log_toolbar)
        btn_container.pack(side="right")
        
        export_btn = ttk.Button(btn_container, text="💾 导出日志", command=self.export_logs)
        export_btn.pack(side="right", padx=(0, 10))
        clear_btn = ttk.Button(btn_container, text="🧹 清空日志", command=self.clear_logs)
        clear_btn.pack(side="right")

        # 日志文本区域
        self.log_text = scrolledtext.ScrolledText(
            right_frame,
            height=15,
            width=40,
            font=self.default_font,
            bg=self.colors["card_bg"],
            fg=self.colors["text_primary"],
            borderwidth=1,
            relief="solid",
            highlightthickness=0,
            padx=15,
            pady=10
        )
        self.log_text.pack(fill="both", expand=True)
        
        # 初始日志
        self.log("🚀 大麦抢票工具启动成功")
        self.log("💡 提示：请先检测环境，然后根据模式完成参数配置")
        self.log("ℹ️ 登录为可选项，可在抢票时再进行登录")
        
        # 启动定期保存cookie功能
        self.root.after(30000, self.auto_save_cookies_if_needed)  # 30秒后开始第一次检查

        # 启动后台授权复检（被吊销时立即退出）
        try:
            self._start_authz_watchdog()
        except Exception as exc:  # noqa: BLE001
            self.log(f"⚠️ 授权监控未启动: {exc}")
        
    def create_web_panel(self, container: ttk.Frame) -> None:
        """构建网页模式下的控制面板"""
        # 配置容器网格
        container.columnconfigure(0, weight=1)

        # 演出链接区域
        url_frame = ttk.LabelFrame(container, text="演出链接", padding="5")
        url_frame.pack(fill="x", pady=(0, 10))

        self.url_entry = ttk.Entry(url_frame, width=50, font=self.default_font)
        self.url_entry.pack(fill="x", pady=2)
        self.url_entry.insert(0, "请输入大麦网演出详情页链接...")
        self.url_entry.bind("<FocusIn>", self.clear_url_placeholder)

        url_buttons_frame = ttk.Frame(url_frame)
        url_buttons_frame.pack(fill="x", pady=5)

        self.login_btn = ttk.Button(
            url_buttons_frame,
            text="🔐 网页登录",
            command=self.web_login,
            state="disabled"
        )
        self.login_btn.pack(side="left", padx=(0, 5))

        self.analyze_btn = ttk.Button(
            url_buttons_frame,
            text="🔍 分析页面",
            command=self.analyze_page,
            state="disabled"
        )
        self.analyze_btn.pack(side="left")

        # 抢票配置区域
        config_frame = ttk.LabelFrame(container, text="抢票配置", padding="5")
        config_frame.pack(fill="x", pady=(0, 10))

        self.config_label = ttk.Label(
            config_frame,
            text="请先分析页面",
            foreground="gray",
            font=self.default_font,
        )
        self.config_label.pack()

    def _init_app_form_vars(self) -> None:
        """初始化 App 模式表单变量"""

        self.app_form_vars: dict[str, Any] = {
            # 推荐值：Appium 标准网关 /wd/hub
            "server_url": tk.StringVar(value="http://127.0.0.1:4723"),
            "keyword": tk.StringVar(value=""),
            "city": tk.StringVar(value=""),
            "date": tk.StringVar(value=""),
            "session_text": tk.StringVar(value=""),
            "session_index": tk.StringVar(value="0"),
            "price": tk.StringVar(value=""),
            # 推荐：优先从第一个票档开始（如需其它档位请修改为实际索引）
            "price_index": tk.StringVar(value="0"),
            # 购票数量
            "ticket_quantity": tk.StringVar(value="5"),
            # 推荐：开售冲刺参数
            "wait_timeout": tk.StringVar(value="1.5"),
            "retry_delay": tk.StringVar(value="1.2"),
            # 设备能力推荐：UiAutomator2
            "device_name": tk.StringVar(value=""),
            "platform_version": tk.StringVar(value=""),
            "udid": tk.StringVar(value=""),
            "automation_name": tk.StringVar(value="UiAutomator2"),
            "if_commit_order": tk.BooleanVar(value=True),
        }

        def _binding_callback(*_args: Any) -> None:
            self._on_app_form_changed()

        for key, var in self.app_form_vars.items():
            if isinstance(var, (tk.StringVar, tk.BooleanVar)):
                var.trace_add("write", _binding_callback)

        self.app_users_text = None
        self.app_form_entries: dict[str, tk.Widget] = {}

    def _build_app_panel(self, container: ttk.Frame) -> None:
        """构建App模式下的控制面板"""

        container.columnconfigure(0, weight=1)

        scroll_container = ttk.Frame(container)
        scroll_container.pack(fill="both", expand=True)

        canvas = tk.Canvas(scroll_container, borderwidth=0, highlightthickness=0)
        v_scroll = ttk.Scrollbar(scroll_container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=v_scroll.set)

        canvas.pack(side="left", fill="both", expand=True)
        v_scroll.pack(side="right", fill="y")

        content = ttk.Frame(canvas)
        content.columnconfigure(0, weight=1)
        content_window = canvas.create_window((0, 0), window=content, anchor="nw")

        def _sync_scrollregion(_event=None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _expand_canvas(event: tk.Event) -> None:  # type: ignore[override]
            canvas.itemconfigure(content_window, width=event.width)
        
        content.bind("<Configure>", _sync_scrollregion)
        canvas.bind("<Configure>", _expand_canvas)
        
        # 移除之前可能存在的全局鼠标滚轮绑定
        try:
            self.root.unbind_all("<MouseWheel>")
        except:
            pass
        
        # 统一的鼠标滚轮事件处理函数
        def _on_mouse_wheel_all(event: tk.Event) -> None:
            # 获取鼠标当前位置下的控件
            try:
                current_widget = self.root.winfo_containing(event.x_root, event.y_root)
            except KeyError:
                # 处理控件不存在的情况
                return
            
            # 检查鼠标是否在配置区域的canvas内或其内部控件上
            if current_widget:
                # 向上查找父控件，检查是否属于配置区域
                widget = current_widget
                is_in_config_area = False
                while widget:
                    if widget == canvas:
                        is_in_config_area = True
                        break
                    widget = widget.master
                
                if is_in_config_area:
                    # 在配置区域内，执行配置区域的滚动
                    canvas.yview_scroll(int(-1*(event.delta/120)), "units")
                    # 阻止事件继续传播
                    return "break"
        
        # 在根窗口级别绑定鼠标滚轮事件
        self.root.bind_all("<MouseWheel>", _on_mouse_wheel_all)

        info_frame = ttk.Frame(content)
        info_frame.pack(fill="x", pady=(0, 5))

        ttk.Label(
            info_frame,
            text="通过 Appium 控制大麦 App 自动抢票",
            font=self.default_font,
            wraplength=320,
            justify="left",
        ).pack(anchor="w")

        if not APPIUM_AVAILABLE:
            ttk.Label(
                info_frame,
                text="⚠️ 未检测到 Appium 运行环境，请先安装依赖",
                foreground="red",
                wraplength=320,
                justify="left",
            ).pack(anchor="w", pady=(5, 0))
        
        # App 模式：新增 Appium 启动/停止按钮与状态
        appium_toolbar = ttk.Frame(info_frame)
        appium_toolbar.pack(fill="x", pady=(6, 0))
        self.appium_toggle_btn = ttk.Button(
            appium_toolbar,
            text="🚀 启动 Appium",
            command=self._toggle_appium_server
        )
        self.appium_toggle_btn.pack(side="left")
        ttk.Label(appium_toolbar, textvariable=self.appium_status_var).pack(side="left", padx=(8, 0))
        
        config_file_frame = ttk.LabelFrame(content, text="配置文件", padding="5")
        config_file_frame.pack(fill="x", pady=(0, 10))

        default_path = self._get_default_app_config_path()
        self.app_config_path_var = tk.StringVar(value=default_path or "")

        path_entry = ttk.Entry(
            config_file_frame,
            textvariable=self.app_config_path_var,
            font=self.default_font,
        )
        path_entry.pack(fill="x", pady=2)

        btn_row = ttk.Frame(config_file_frame)
        btn_row.pack(fill="x", pady=2)

        ttk.Button(btn_row, text="📂 选择文件", command=self.select_app_config).pack(
            side="left", padx=(0, 5)
        )
        ttk.Button(btn_row, text="🔄 重新加载", command=self.load_app_config).pack(side="left")

        ttk.Button(btn_row, text="📘 配置说明", command=self.open_app_docs).pack(side="left", padx=(5, 0))

        params_frame = ttk.LabelFrame(content, text="运行参数", padding="5")
        params_frame.pack(fill="x", pady=(0, 10))

        # 推荐：最大重试次数（开售冲刺）
        self.app_retries_var = tk.IntVar(value=6)
        ttk.Label(params_frame, text="最大重试次数:").grid(row=0, column=0, sticky="w")
        retries_spin = ttk.Spinbox(
            params_frame,
            from_=1,
            to=10,
            textvariable=self.app_retries_var,
            width=5,
        )
        retries_spin.grid(row=0, column=1, sticky="w", padx=(5, 0))

        self.app_config_status = ttk.Label(
            params_frame,
            text="尚未加载配置",
            foreground="gray",
        )
        self.app_config_status.grid(row=1, column=0, columnspan=2, sticky="w", pady=(5, 0))

        device_frame = ttk.LabelFrame(content, text="设备状态", padding="5")
        device_frame.pack(fill="x", pady=(0, 10))

        device_header = ttk.Frame(device_frame)
        device_header.pack(fill="x")

        self.app_device_status_var = tk.StringVar(value="尚未检测设备")
        self.app_device_status_label = ttk.Label(
            device_header,
            textvariable=self.app_device_status_var,
            foreground="gray",
        )
        self.app_device_status_label.pack(side="left", expand=True, fill="x")

        self.app_device_refresh_btn = ttk.Button(
            device_header,
            text="🔄 刷新设备",
            command=self._refresh_devices_clicked
        )
        self.app_device_refresh_btn.pack(side="right")

        options_row = ttk.Frame(device_frame)
        options_row.pack(fill="x", pady=(6, 0))

        ttk.Label(options_row, text="选择设备：").pack(side="left")
        self.app_device_options_var = tk.StringVar(value="")
        self.app_device_combobox = ttk.Combobox(
            options_row,
            textvariable=self.app_device_options_var,
            state="disabled",
            width=36,
        )
        self.app_device_combobox.pack(side="left", fill="x", expand=True, padx=(4, 0))
        self.app_device_combobox.bind("<<ComboboxSelected>>", self._on_device_selection_changed)

        default_device_hint = "点击“刷新设备”或执行环境检测查看最新状态。"
        self.app_device_detail_var = tk.StringVar(value=default_device_hint)
        self.app_device_detail_label = ttk.Label(
            device_frame,
            textvariable=self.app_device_detail_var,
            wraplength=420,
            justify="left",
            foreground="gray",
        )
        self.app_device_detail_label.pack(anchor="w", pady=(4, 0))

        if not (APPIUM_AVAILABLE and parse_adb_devices is not None):
            self.app_device_refresh_btn.config(state="disabled")
            if not APPIUM_AVAILABLE:
                unsupported_hint = "当前环境未启用 Appium，安装完成后可刷新设备列表。"
            else:
                unsupported_hint = "缺少 adb 解析能力，安装 damai_appium 依赖后重启程序。"
            self.app_device_detail_var.set(unsupported_hint)
            self.app_device_detail_label.config(foreground="red")
            if self.app_device_combobox is not None:
                self.app_device_combobox.config(state="disabled")

        form_frame = ttk.LabelFrame(content, text="图形化配置", padding="5")
        form_frame.pack(fill="both", expand=True, pady=(0, 10))
        self._create_app_form_fields(form_frame)

        # 取消“高级选项”分组，改为在抢票信息中单独展示“自动提交订单”开关

        self.app_form_status_label = ttk.Label(
            content,
            text="⬆️ 请完善以上参数后即可启动",
            foreground="gray",
        )
        self.app_form_status_label.pack(anchor="w", pady=(0, 10))

        # 定时抢票面板
        schedule_frame = ttk.LabelFrame(content, text="定时抢票", padding="5")
        schedule_frame.pack(fill="x", pady=(0, 10))

        # 初始化日期时间选择器
        ttk.Label(schedule_frame, text="时间选择").grid(row=1, column=0, sticky="w", pady=2)
        self.datetime_picker_frame = ttk.Frame(schedule_frame)
        self.datetime_picker_frame.grid(row=1, column=1, columnspan=2, sticky="we", padx=(5, 0), pady=2)
        self.schedule_datetime_picker = DateTimePicker(self.datetime_picker_frame, gui=self)

        ttk.Label(schedule_frame, text="预热秒数").grid(row=2, column=0, sticky="w", pady=2)
        warmup_spin = ttk.Spinbox(schedule_frame, from_=5, to=600, textvariable=self.schedule_warmup_var, width=8)
        warmup_spin.grid(row=2, column=1, sticky="w", padx=(5, 0), pady=2)

        btns = ttk.Frame(schedule_frame)
        btns.grid(row=3, column=0, columnspan=4, sticky="we", pady=(4, 0))
        self.schedule_start_btn = ttk.Button(btns, text="⏰ 预约开抢", command=self._schedule_start_clicked)
        self.schedule_start_btn.pack(side="left", padx=(0, 6))
        self.schedule_cancel_btn = ttk.Button(btns, text="❌ 取消预约", command=self._schedule_cancel)
        self.schedule_cancel_btn.pack(side="left")

        self.schedule_status_label = ttk.Label(schedule_frame, textvariable=self.schedule_status_var, foreground="gray")
        self.schedule_status_label.grid(row=4, column=0, columnspan=4, sticky="w", pady=(4, 0))
        
        summary_frame = ttk.LabelFrame(content, text="配置摘要", padding="5")
        summary_frame.pack(fill="both", expand=True)

        self.app_summary_text = tk.Text(
            summary_frame,
            height=10,
            wrap="word",
            bg=self.root.cget("bg"),
            relief="flat",
            font=self.default_font,
        )
        self.app_summary_text.pack(fill="both", expand=True)
        self.app_summary_text.insert(tk.END, "请在左侧表单填写 Appium 配置，完成后将在此展示摘要。")
        self.app_summary_text.config(state="disabled")

    def _create_app_form_fields(self, container: ttk.LabelFrame) -> None:
        """创建 App 模式基础配置表单（分隔设备信息与抢票信息）"""
    
        # 设备信息分组
        device_frame = ttk.LabelFrame(container, text="设备信息", padding="6")
        device_frame.pack(fill="x", pady=(0, 8))
        for col in range(4):
            device_frame.columnconfigure(col, weight=1 if col in (1, 3) else 0)
    
        ttk.Label(device_frame, text="Appium 服务地址").grid(row=0, column=0, sticky="w", pady=2)
        server_entry = ttk.Entry(device_frame, textvariable=self.app_form_vars["server_url"], width=35)
        server_entry.grid(row=0, column=1, columnspan=3, sticky="we", padx=(5, 0), pady=2)
        self.app_form_entries["server_url"] = server_entry
    
        ttk.Label(device_frame, text="设备名称").grid(row=1, column=0, sticky="w", pady=2)
        device_entry = ttk.Entry(device_frame, textvariable=self.app_form_vars["device_name"], width=24)
        device_entry.grid(row=1, column=1, sticky="we", padx=(5, 0), pady=2)
        self.app_form_entries["device_name"] = device_entry
    
        ttk.Label(device_frame, text="设备 UDID").grid(row=1, column=2, sticky="w", pady=2)
        udid_entry = ttk.Entry(device_frame, textvariable=self.app_form_vars["udid"], width=24)
        udid_entry.grid(row=1, column=3, sticky="we", padx=(5, 0), pady=2)
        self.app_form_entries["udid"] = udid_entry
    
        # 抢票信息分组
        ticket_frame = ttk.LabelFrame(container, text="抢票信息", padding="6")
        ticket_frame.pack(fill="x", pady=(0, 8))
        for col in range(4):
            ticket_frame.columnconfigure(col, weight=1 if col in (1, 3) else 0)
    
        ttk.Label(ticket_frame, text="关键词").grid(row=0, column=0, sticky="w", pady=2)
        keyword_entry = ttk.Entry(ticket_frame, textvariable=self.app_form_vars["keyword"], width=24)
        keyword_entry.grid(row=0, column=1, sticky="we", padx=(5, 0), pady=2)
        self.app_form_entries["keyword"] = keyword_entry
    
        ttk.Label(ticket_frame, text="城市").grid(row=0, column=2, sticky="w", pady=2)
        city_entry = ttk.Entry(ticket_frame, textvariable=self.app_form_vars["city"], width=24)
        city_entry.grid(row=0, column=3, sticky="we", padx=(5, 0), pady=2)
        self.app_form_entries["city"] = city_entry
    
        ttk.Label(ticket_frame, text="场次文本").grid(row=1, column=0, sticky="w", pady=2)
        session_text_entry = ttk.Entry(ticket_frame, textvariable=self.app_form_vars["session_text"], width=24)
        session_text_entry.grid(row=1, column=1, sticky="we", padx=(5, 0), pady=2)
        self.app_form_entries["session_text"] = session_text_entry
    
        ttk.Label(ticket_frame, text="场次索引").grid(row=1, column=2, sticky="w", pady=2)
        session_index_entry = ttk.Entry(ticket_frame, textvariable=self.app_form_vars["session_index"], width=24)
        session_index_entry.grid(row=1, column=3, sticky="we", padx=(5, 0), pady=2)
        self.app_form_entries["session_index"] = session_index_entry
    
        ttk.Label(ticket_frame, text="票价文本").grid(row=2, column=0, sticky="w", pady=2)
        price_entry = ttk.Entry(ticket_frame, textvariable=self.app_form_vars["price"], width=24)
        price_entry.grid(row=2, column=1, sticky="we", padx=(5, 0), pady=2)
        self.app_form_entries["price"] = price_entry
    
        ttk.Label(ticket_frame, text="票价索引").grid(row=2, column=2, sticky="w", pady=2)
        price_index_entry = ttk.Entry(ticket_frame, textvariable=self.app_form_vars["price_index"], width=24)
        price_index_entry.grid(row=2, column=3, sticky="we", padx=(5, 0), pady=2)
        self.app_form_entries["price_index"] = price_index_entry
    
        ttk.Label(ticket_frame, text="等待超时(s)").grid(row=3, column=0, sticky="w", pady=2)
        wait_entry = ttk.Entry(ticket_frame, textvariable=self.app_form_vars["wait_timeout"], width=24)
        wait_entry.grid(row=3, column=1, sticky="we", padx=(5, 0), pady=2)
        self.app_form_entries["wait_timeout"] = wait_entry
    
        ttk.Label(ticket_frame, text="重试间隔(s)").grid(row=3, column=2, sticky="w", pady=2)
        retry_entry = ttk.Entry(ticket_frame, textvariable=self.app_form_vars["retry_delay"], width=24)
        retry_entry.grid(row=3, column=3, sticky="we", padx=(5, 0), pady=2)
        self.app_form_entries["retry_delay"] = retry_entry

        # 购票数量
        ttk.Label(ticket_frame, text="购票数量").grid(row=4, column=0, sticky="w", pady=2)
        ticket_quantity_entry = ttk.Entry(ticket_frame, textvariable=self.app_form_vars["ticket_quantity"], width=24)
        ticket_quantity_entry.grid(row=4, column=1, sticky="we", padx=(5, 0), pady=2)
        self.app_form_entries["ticket_quantity"] = ticket_quantity_entry

        # 自动提交订单开关（从高级选项迁移到抢票信息分组）
        ttk.Label(ticket_frame, text="自动提交订单").grid(row=5, column=0, sticky="w", pady=2)
        commit_check = ttk.Checkbutton(
            ticket_frame,
            text="完成下单流程后自动提交",
            variable=self.app_form_vars["if_commit_order"],
            onvalue=True,
            offvalue=False,
        )
        commit_check.grid(row=5, column=1, columnspan=3, sticky="w", pady=2)
        self.app_form_entries["if_commit_order"] = commit_check

        viewers_note = ttk.Label(ticket_frame, text="观演人：默认全选，无需填写", foreground="gray")
        viewers_note.grid(row=6, column=0, columnspan=4, sticky="w", pady=(2, 0))

        self._update_app_summary_from_form()

    def _create_app_advanced_fields(self, container: ttk.Frame) -> None:
        """创建 App 模式高级配置字段"""

        container.columnconfigure(1, weight=1)
        container.columnconfigure(3, weight=1)

        ttk.Label(container, text="AutomationName").grid(row=0, column=0, sticky="w", pady=2)
        auto_entry = ttk.Entry(container, textvariable=self.app_form_vars["automation_name"], width=24)
        auto_entry.grid(row=0, column=1, sticky="we", padx=(5, 0), pady=2)
        self.app_form_entries["automation_name"] = auto_entry

        ttk.Label(container, text="票价索引").grid(row=0, column=2, sticky="w", pady=2)
        price_index_entry = ttk.Entry(container, textvariable=self.app_form_vars["price_index"], width=24)
        price_index_entry.grid(row=0, column=3, sticky="we", padx=(5, 0), pady=2)
        self.app_form_entries["price_index"] = price_index_entry

        ttk.Label(container, text="等待超时(s)").grid(row=1, column=0, sticky="w", pady=2)
        wait_entry = ttk.Entry(container, textvariable=self.app_form_vars["wait_timeout"], width=24)
        wait_entry.grid(row=1, column=1, sticky="we", padx=(5, 0), pady=2)
        self.app_form_entries["wait_timeout"] = wait_entry

        ttk.Label(container, text="重试间隔(s)").grid(row=1, column=2, sticky="w", pady=2)
        retry_entry = ttk.Entry(container, textvariable=self.app_form_vars["retry_delay"], width=24)
        retry_entry.grid(row=1, column=3, sticky="we", padx=(5, 0), pady=2)
        self.app_form_entries["retry_delay"] = retry_entry

        ttk.Label(container, text="自动提交订单").grid(row=2, column=0, sticky="w", pady=2)
        commit_check = ttk.Checkbutton(
            container,
            text="完成下单流程后自动提交",
            variable=self.app_form_vars["if_commit_order"],
            onvalue=True,
            offvalue=False,
        )
        commit_check.grid(row=2, column=1, columnspan=3, sticky="w", pady=2)
        self.app_form_entries["if_commit_order"] = commit_check

        ttk.Label(
            container,
            text="如需保留默认行为，可不用修改此处配置。",
            foreground="gray",
            wraplength=420,
            justify="left",
        ).grid(row=3, column=0, columnspan=4, sticky="w", pady=(2, 0))

    def _create_collapsible_section(
        self,
        parent: ttk.Frame,
        title: str,
        description: Optional[str] = None,
        initially_open: bool = False,
    ) -> ttk.Frame:
        """创建可折叠的配置面板并返回内容容器"""

        section = ttk.Frame(parent)
        section.pack(fill="x", pady=(0, 10))

        state_text = tk.StringVar()

        body = ttk.Frame(section)

        def _open() -> None:
            body.pack(fill="both", expand=True, pady=(6, 0))
            state_text.set(f"▼ {title}")

        def _close() -> None:
            body.pack_forget()
            state_text.set(f"▶ {title}")

        def _toggle() -> None:
            if body.winfo_ismapped():
                _close()
            else:
                _open()

        toggle_btn = ttk.Button(
            section,
            textvariable=state_text,
            command=_toggle,
            style="Toolbutton",
        )
        toggle_btn.pack(fill="x")

        if initially_open:
            _open()
        else:
            _close()

        if description:
            ttk.Label(
                body,
                text=description,
                foreground="gray",
                wraplength=420,
                justify="left",
            ).pack(anchor="w", pady=(0, 6))

        content_frame = ttk.Frame(body)
        content_frame.pack(fill="both", expand=True)

        toggle_btn.bind("<Return>", lambda _event: _toggle())
        toggle_btn.bind("<space>", lambda _event: _toggle())

        if not hasattr(self, "_collapsible_controls"):
            self._collapsible_controls: list[tuple[ttk.Button, ttk.Frame]] = []
        self._collapsible_controls.append((toggle_btn, body))

        return content_frame

    def _init_styles(self) -> None:
        """初始化现代化的ttk样式"""
        style = ttk.Style(self.root)
        
        # 设置主题为clam（更现代化的外观）
        style.theme_use("clam")
        
        # 配置主窗口样式
        style.configure(
            ".",
            background=self.colors["background"],
            foreground=self.colors["text_primary"],
            font=self.default_font,
        )
        
        # 配置LabelFrame样式
        style.configure(
            "TLabelframe",
            background=self.colors["card_bg"],
            borderwidth=1,
            relief="flat",
        )
        style.configure(
            "TLabelframe.Label",
            background=self.colors["card_bg"],
            foreground=self.colors["text_primary"],
            font=(self.default_font[0], self.default_font[1], "bold"),
            padding=(5, 2),
        )
        
        # 配置Button样式
        style.configure(
            "TButton",
            background=self.colors["primary"],
            foreground="white",
            font=self.button_font,
            borderwidth=0,
            relief="flat",
            padding=(10, 5),
            borderradius=4,
        )
        style.map(
            "TButton",
            background=[
                ("active", self.colors["primary_dark"]),
                ("disabled", self.colors["border_light"]),
            ],
            foreground=[
                ("disabled", self.colors["text_secondary"]),
            ],
        )
        
        # 配置Entry样式
        style.configure(
            "TEntry",
            background=self.colors["card_bg"],
            foreground=self.colors["text_primary"],
            font=self.default_font,
            borderwidth=1,
            relief="flat",
            fieldbackground=self.colors["card_bg"],
            padding=5,
        )
        style.map(
            "TEntry",
            bordercolor=[
                ("focus", self.colors["primary"]),
                ("!focus", self.colors["border"]),
            ],
        )
        
        # 配置Combobox样式
        style.configure(
            "TCombobox",
            background=self.colors["card_bg"],
            foreground=self.colors["text_primary"],
            font=self.default_font,
            borderwidth=1,
            relief="flat",
            padding=5,
        )
        style.map(
            "TCombobox",
            bordercolor=[
                ("focus", self.colors["primary"]),
                ("!focus", self.colors["border"]),
            ],
        )
        
        # 配置Notebook样式
        style.configure(
            "Modern.TNotebook",
            background=self.colors["background"],
            borderwidth=0,
            relief="flat",
        )
        style.configure(
            "Modern.TNotebook.Tab",
            background=self.colors["card_bg"],
            foreground=self.colors["text_secondary"],
            font=self.default_font,
            padding=(15, 8),
            borderwidth=1,
            relief="flat",
        )
        style.map(
            "Modern.TNotebook.Tab",
            background=[
                ("selected", self.colors["card_bg"]),
                ("!selected", self.colors["border_light"]),
            ],
            foreground=[
                ("selected", self.colors["primary"]),
                ("!selected", self.colors["text_secondary"]),
            ],
            bordercolor=[
                ("selected", self.colors["primary"]),
                ("!selected", self.colors["border_light"]),
            ],
        )
        
        # 配置Checkbutton样式
        style.configure(
            "TCheckbutton",
            background=self.colors["card_bg"],
            foreground=self.colors["text_primary"],
            font=self.default_font,
            padding=5,
        )
        style.map(
            "TCheckbutton",
            background=[
                ("active", self.colors["card_bg"]),
            ],
        )
        
        # 配置Spinbox样式
        style.configure(
            "TSpinbox",
            background=self.colors["card_bg"],
            foreground=self.colors["text_primary"],
            font=self.default_font,
            borderwidth=1,
            relief="flat",
            padding=5,
        )
        style.map(
            "TSpinbox",
            bordercolor=[
                ("focus", self.colors["primary"]),
                ("!focus", self.colors["border"]),
            ],
        )
    
    def _setup_mode_notebook_style(self) -> None:
        """初始化 Notebook 标签的样式与状态颜色"""
        # 此方法已被 _init_styles 替代，保留为空以确保兼容性
        pass
    
    def _init_styles(self) -> None:
        """初始化现代化的ttk样式"""
        style = ttk.Style(self.root)
        
        # 设置主题为clam（更现代化的外观）
        style.theme_use("clam")
        
        # 配置基础样式
        style.configure(
            ".",
            background=self.colors["background"],
            foreground=self.colors["text_primary"],
            font=self.default_font,
        )
        
        # 配置Frame样式
        style.configure(
            "Modern.TFrame",
            background=self.colors["background"]
        )
        
        # 配置LabelFrame样式
        style.configure(
            "TLabelframe",
            background=self.colors["card_bg"],
            borderwidth=1,
            relief="flat",
        )
        style.configure(
            "TLabelframe.Label",
            background=self.colors["card_bg"],
            foreground=self.colors["text_primary"],
            font=self.default_font,
            padding=(5, 2),
        )
        
        # 配置Notebook样式
        style.configure(
            "Modern.TNotebook",
            background=self.colors["background"],
            borderwidth=0,
            relief="flat",
        )
        
        style.configure(
            "Modern.TNotebook.Tab",
            background=self.colors["card_bg"],
            foreground=self.colors["text_secondary"],
            font=self.default_font,
            padding=(15, 8),
            borderwidth=1,
            relief="flat",
        )
        
        style.map(
            "Modern.TNotebook.Tab",
            background=[
                ("selected", self.colors["card_bg"]),
                ("!selected", self.colors["border_light"]),
            ],
            foreground=[
                ("selected", self.colors["primary"]),
                ("!selected", self.colors["text_secondary"]),
            ],
            bordercolor=[
                ("selected", self.colors["primary"]),
                ("!selected", self.colors["border_light"]),
            ],
        )
        
        # 配置Button样式
        style.configure(
            "TButton",
            background=self.colors["primary"],
            foreground="white",
            font=self.button_font,
            borderwidth=0,
            relief="flat",
            padding=(10, 5),
            borderradius=4,
        )
        
        style.map(
            "TButton",
            background=[
                ("active", self.colors["primary_dark"]),
                ("disabled", self.colors["border_light"]),
            ],
            foreground=[
                ("disabled", self.colors["text_secondary"]),
            ],
        )
        
        # 配置主要按钮样式
        style.configure(
            "Primary.TButton",
            background=self.colors["primary"],
            foreground="white",
            font=self.button_font,
            padding=(15, 8),
        )
        
        # 配置次要按钮样式
        style.configure(
            "Secondary.TButton",
            background=self.colors["border_light"],
            foreground=self.colors["text_primary"],
            font=self.button_font,
            padding=(10, 6),
        )
        
        # 配置危险按钮样式
        style.configure(
            "Danger.TButton",
            background=self.colors["error"],
            foreground="white",
            font=self.button_font,
            padding=(10, 6),
        )
        
        style.map(
            "Danger.TButton",
            background=[("active", self.colors["error_dark"])],
        )

    def _on_app_users_modified(self, event):  # type: ignore[override]
        if not getattr(event.widget, "edit_modified", None):
            return
        event.widget.edit_modified(False)
        self._on_app_form_changed()

    def _on_app_form_changed(self, *_args: Any) -> None:
        self.app_config_ready = self._validate_app_form()
        self._update_app_summary_from_form()
        self._refresh_app_start_button()

    def _refresh_app_start_button(self) -> None:
        if not hasattr(self, "start_btn"):
            return
        if self.mode_var.get() != "app":
            return
        state = "normal" if (self.app_env_ready and self.app_config_ready) else "disabled"
        self.start_btn.config(state=state)

    def _validate_app_form(self, update_label: bool = True) -> bool:
        config = self._collect_app_config_from_form(strict=False)
        errors = list(self._last_config_errors)

        ready = config is not None and not errors

        if update_label and hasattr(self, "app_form_status_label"):
            if errors:
                self.app_form_status_label.config(text=" ❌ " + errors[0], foreground="red")
            else:
                status = "✅ 配置已就绪" if ready else "⬆️ 请完善以上参数后即可启动"
                color = "green" if ready else "gray"
                self.app_form_status_label.config(text=status, foreground=color)

        if update_label and hasattr(self, "app_config_status"):
            if errors:
                self.app_config_status.config(text="配置不完整", foreground="red")
            elif self.app_loaded_config is not None:
                # 如果已经加载了配置文件，显示"配置加载成功"
                self.app_config_status.config(text="配置加载成功", foreground="green")
            else:
                status_text = "配置已就绪" if ready else "尚未完成配置"
                status_color = "green" if ready else "gray"
                self.app_config_status.config(text=status_text, foreground=status_color)

        return ready

    def _update_app_summary_from_form(self) -> None:
        if not hasattr(self, "app_summary_text"):
            return

        if AppTicketConfig is None:
            self.app_summary_text.config(state="normal")
            self.app_summary_text.delete("1.0", tk.END)
            self.app_summary_text.insert(tk.END, "当前环境未启用 Appium，请先安装相关依赖。")
            self.app_summary_text.config(state="disabled")
            return

        config = self._collect_app_config_from_form(strict=False)
        self._set_app_summary_text(config)

    def _populate_app_form(self, config: Any) -> None:
        if not config:
            return

        self.app_form_vars["server_url"].set(getattr(config, "server_url", ""))
        self.app_form_vars["keyword"].set(getattr(config, "keyword", "") or "")
        self.app_form_vars["city"].set(getattr(config, "city", "") or "")
        self.app_form_vars["date"].set(getattr(config, "date", "") or "")
        self.app_form_vars["session_text"].set(getattr(config, "session_text", "") or "")
        self.app_form_vars["price"].set(getattr(config, "price", "") or "")

        session_index = getattr(config, "session_index", None)
        self.app_form_vars["session_index"].set("" if session_index is None else str(session_index))

        price_index = getattr(config, "price_index", None)
        self.app_form_vars["price_index"].set("" if price_index is None else str(price_index))

        ticket_quantity = getattr(config, "ticket_quantity", None)
        self.app_form_vars["ticket_quantity"].set("" if ticket_quantity is None else str(ticket_quantity))

        self.app_form_vars["wait_timeout"].set(str(getattr(config, "wait_timeout", 2.0)))
        self.app_form_vars["retry_delay"].set(str(getattr(config, "retry_delay", 2.0)))
        self.app_form_vars["if_commit_order"].set(bool(getattr(config, "if_commit_order", True)))

        device_caps = getattr(config, "device_caps", {}) or {}
        self.app_form_vars["device_name"].set(device_caps.get("deviceName", ""))
        self.app_form_vars["platform_version"].set(device_caps.get("platformVersion", ""))
        self.app_form_vars["udid"].set(device_caps.get("udid", ""))
        
        # 加载开抢时间配置
        event_date = getattr(config, "date", "")
        if event_date and hasattr(self, 'schedule_datetime_picker'):
            # 如果配置文件中有日期字段，设置为默认开抢日期
            try:
                # 解析日期字符串为datetime对象
                
                # 尝试不同的日期格式
                date_formats = ["%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"]
                for fmt in date_formats:
                    try:
                        dt = datetime.strptime(event_date, fmt)
                        # 使用DateTimePicker的方法来设置日期时间
                        self.schedule_datetime_picker.selected_datetime = dt
                        self.schedule_datetime_picker.update_display(dt)
                        break
                    except ValueError:
                        continue
            except Exception:
                # 如果解析失败，忽略该配置
                pass
        self.app_form_vars["automation_name"].set(device_caps.get("automationName", ""))

        # 加载预热秒数配置
        warmup_sec = getattr(config, "warmup_sec", None)
        if warmup_sec is not None:
            self.schedule_warmup_var.set(warmup_sec)

        if self.app_users_text is not None:
            self.app_users_text.delete("1.0", tk.END)
            users = getattr(config, "users", []) or []
            if users:
                self.app_users_text.insert(tk.END, "\n".join(users))

        self._on_app_form_changed()

    def _build_app_config_payload(self, *, strict: bool) -> Dict[str, Any]:
        base_config = self.app_loaded_config
        payload: Dict[str, Any] = {}
        if base_config is not None:
            try:
                payload.update(asdict(base_config))
            except Exception:
                payload.update(
                    {
                        "server_url": getattr(base_config, "server_url", ""),
                        "keyword": getattr(base_config, "keyword", None),
                        "users": list(getattr(base_config, "users", []) or []),
                        "city": getattr(base_config, "city", None),
                        "date": getattr(base_config, "date", None),
                        "session_text": getattr(base_config, "session_text", None),
                        "session_index": getattr(base_config, "session_index", None),
                        "price": getattr(base_config, "price", None),
                        "price_index": getattr(base_config, "price_index", None),
                        "if_commit_order": getattr(base_config, "if_commit_order", True),
                        "device_caps": dict(getattr(base_config, "device_caps", {}) or {}),
                        "wait_timeout": getattr(base_config, "wait_timeout", 2.0),
                        "retry_delay": getattr(base_config, "retry_delay", 2.0),
                    }
                )

        server_url_raw = self.app_form_vars["server_url"].get().strip()
        if server_url_raw:
            payload["server_url"] = server_url_raw
        elif "server_url" not in payload:
            payload["server_url"] = ""

        for key in ("keyword", "city", "session_text", "price"):
            value = self.app_form_vars[key].get().strip()
            payload[key] = value or None

        session_index_raw = self.app_form_vars["session_index"].get().strip()
        if session_index_raw:
            payload["session_index"] = session_index_raw
        elif base_config is not None:
            payload["session_index"] = getattr(base_config, "session_index", None)
        else:
            payload["session_index"] = None

        price_index_raw = self.app_form_vars["price_index"].get().strip()
        if price_index_raw:
            payload["price_index"] = price_index_raw
        elif base_config is not None:
            payload["price_index"] = getattr(base_config, "price_index", None)
        else:
            payload["price_index"] = None

        # 处理购票数量
        ticket_quantity_raw = self.app_form_vars["ticket_quantity"].get().strip()
        if ticket_quantity_raw:
            payload["ticket_quantity"] = ticket_quantity_raw
        elif base_config is not None:
            payload["ticket_quantity"] = getattr(base_config, "ticket_quantity", None)
        else:
            payload["ticket_quantity"] = None

        payload["if_commit_order"] = bool(self.app_form_vars["if_commit_order"].get())

        users = self._get_users_from_widget()
        if users:
            payload["users"] = users
        elif base_config is None:
            payload["users"] = list(payload.get("users", []) or [])
        else:
            payload["users"] = list(getattr(base_config, "users", []) or [])
        
        # 添加时间选择器的时间到配置中
        selected_dt = self.schedule_datetime_picker.get_datetime()
        if selected_dt is not None:
            # 格式化为包含时间的格式
            payload["date"] = selected_dt.strftime("%Y-%m-%d %H:%M:%S")
        
        # 添加预热秒数到配置中
        payload["warmup_sec"] = self.schedule_warmup_var.get()

        wait_timeout_raw = self.app_form_vars["wait_timeout"].get().strip()
        if wait_timeout_raw:
            payload["wait_timeout"] = wait_timeout_raw
        elif base_config is not None:
            payload["wait_timeout"] = getattr(base_config, "wait_timeout", 2.0)
        else:
            payload["wait_timeout"] = None

        retry_delay_raw = self.app_form_vars["retry_delay"].get().strip()
        if retry_delay_raw:
            payload["retry_delay"] = retry_delay_raw
        elif base_config is not None:
            payload["retry_delay"] = getattr(base_config, "retry_delay", 2.0)
        else:
            payload["retry_delay"] = None

        existing_caps = dict(payload.get("device_caps", {}) or {})
        caps_mapping = {
            "device_name": "deviceName",
            "platform_version": "platformVersion",
            "udid": "udid",
            "automation_name": "automationName",
        }
        for field_key, cap_key in caps_mapping.items():
            value = self.app_form_vars[field_key].get().strip()
            if value:
                existing_caps[cap_key] = value
            elif strict and cap_key in existing_caps:
                existing_caps.pop(cap_key, None)
        payload["device_caps"] = existing_caps

        return payload

    def _collect_app_config_from_form(self, *, strict: bool = True) -> Optional[Any]:
        if AppTicketConfig is None:
            raise RuntimeError("当前环境未启用 Appium")

        payload = self._build_app_config_payload(strict=strict)

        try:
            config = AppTicketConfig.from_mapping(payload)
        except Exception as exc:  # noqa: BLE001
            if ConfigValidationError is not None and isinstance(exc, ConfigValidationError):
                self._last_config_errors = list(exc.errors)
                if strict:
                    raise
                return None
            self._last_config_errors = [str(exc)]
            if strict:
                raise
            return None

        self._last_config_errors = []
        return config

    def _format_config_errors(self, errors: List[str]) -> str:
        if not errors:
            return ""
        return "\n".join(f"• {item}" for item in errors if item)

    def _show_config_validation_error(self, title: str, message: str, errors: List[str]) -> None:
        detail = self._format_config_errors(errors)
        full_message = message if not detail else f"{message}\n\n{detail}"
        messagebox.showerror(title, full_message)
        self.log(f"❌ {message}")
        for item in errors:
            self.log(f"    ↳ {item}")

    def _get_users_from_widget(self) -> List[str]:
        if self.app_users_text is None:
            return []
        content = self.app_users_text.get("1.0", tk.END).strip()
        if not content:
            return []
        candidates = re.split(r"[\n,;]", content)
        return [item.strip() for item in candidates if item.strip()]

    def create_control_buttons(self, parent, row):
        """创建控制按钮区域"""
        control_frame = ttk.Frame(parent)
        control_frame.grid(row=row, column=0, columnspan=2, pady=20)
        
        # 左侧按钮组
        left_btn_frame = ttk.Frame(control_frame)
        left_btn_frame.pack(side="left")
        
        self.start_btn = ttk.Button(
            left_btn_frame, 
            text="🎯 开始抢票", 
            command=self.start_grabbing, 
            state="disabled"
        )
        self.start_btn.pack(side="left", padx=5)
        
        self.stop_btn = ttk.Button(
            left_btn_frame, 
            text="⏹ 停止", 
            command=self.stop_grabbing, 
            state="disabled"
        )
        self.stop_btn.pack(side="left", padx=5)
        
        self.return_btn = ttk.Button(
            left_btn_frame, 
            text="🏠 回到主界面", 
            command=self.return_to_main
        )
        self.return_btn.pack(side="left", padx=5)
        
        self.clear_login_btn = ttk.Button(
            left_btn_frame, 
            text="🗑️ 清除登录状态", 
            command=self.clear_login_status
        )
        self.clear_login_btn.pack(side="left", padx=5)
        
        self.help_btn = ttk.Button(
            left_btn_frame, 
            text="❓ 帮助", 
            command=self.show_help
        )
        self.help_btn.pack(side="left", padx=5)
        
        ttk.Button(control_frame, text="❌ 退出", command=self.root.quit).pack(side="right", padx=5)
        
    def _on_mode_tab_changed(self, event: tk.Event) -> None:  # type: ignore[override]
        if not hasattr(self, "mode_notebook"):
            return
        try:
            current_index = event.widget.index("current")  # type: ignore[attr-defined]
        except Exception:
            current_index = 0
        mode = "web" if current_index == 0 else "app"
        if self.mode_var.get() != mode:
            self.mode_var.set(mode)
        self.switch_mode(from_notebook=True)

    def switch_mode(self, *, from_notebook: bool = False) -> None:
        """切换网页/App 模式"""

        mode = self.mode_var.get()
        self.refresh_steps()

        if not from_notebook and hasattr(self, "mode_notebook"):
            desired_index = 0 if mode == "web" else 1
            try:
                current_index = self.mode_notebook.index("current")
            except Exception:
                current_index = desired_index
            if current_index != desired_index:
                self.mode_notebook.select(desired_index)

        self.env_status_label.config(text="点击检测环境", foreground="orange")

        if mode == "web":
            if hasattr(self, "login_btn"):
                self.login_btn.config(state="disabled")
            if hasattr(self, "analyze_btn"):
                self.analyze_btn.config(state="disabled")
            if hasattr(self, "start_btn"):
                self.start_btn.config(state="disabled")
            self.log("🔁 已切换到网页模式")
        else:
            if hasattr(self, "start_btn"):
                self.start_btn.config(state="disabled")
            if hasattr(self, "stop_btn"):
                self.stop_btn.config(state="disabled")
            self._refresh_app_start_button()
            self.log("🔁 已切换到 App 模式，请先检测环境并完善配置表单")

    def _get_default_app_config_path(self) -> Optional[str]:
        """尝试查找默认的 App 配置文件路径"""

        candidates = [
            Path.cwd() / "damai_appium" / "config.jsonc",
            Path.cwd() / "damai_appium" / "config.json",
        ]
        for path in candidates:
            if path.exists():
                return str(path)
        return None

    def select_app_config(self) -> None:
        """选择 App 配置文件"""

        file_path = filedialog.askopenfilename(
            title="选择 App 配置文件",
            filetypes=[("JSON/JSONC", "*.jsonc *.json"), ("所有文件", "*.*")],
        )
        if file_path:
            self.app_config_path_var.set(file_path)
            self._auto_load_app_config()
    
    def _setup_auto_config_load(self) -> None:
        """设置自动加载配置"""
        # 尝试获取默认配置文件路径
        default_path = self._get_default_app_config_path()
        if default_path:
            # 设置配置文件路径
            self.app_config_path_var.set(default_path)
            # 自动加载配置
            self._auto_load_app_config()
    
    def _auto_load_app_config(self) -> None:
        """自动加载 App 配置到 UI 界面"""
        if not APPIUM_AVAILABLE or AppTicketConfig is None:
            return
        
        config_path = self.app_config_path_var.get().strip()
        if not config_path:
            return
        
        path = Path(config_path)
        if not path.exists():
            return
        
        try:
            config = AppTicketConfig.load(path)
            self.app_loaded_config = config
            self.app_config_data = {
                "path": str(path),
                "config": config,
            }
            self._populate_app_form(config)
            self.app_config_status.config(text="配置加载成功", foreground="green")
            self.log(f"✅ 已自动加载 App 配置: {path.name}")
            self._last_config_errors = []

            if self.mode_var.get() == "app":
                self.mark_step("3. 参数配置", "completed")
            self._refresh_app_start_button()
        except Exception as exc:  # noqa: BLE001
            self.app_config_status.config(text="配置加载失败", foreground="red")
            self.app_config_ready = False
            if ConfigValidationError is not None and isinstance(exc, ConfigValidationError):
                errors = list(exc.errors)
                self._last_config_errors = errors
                self._show_config_validation_error("配置校验失败", exc.message, errors)
            else:
                self._last_config_errors = [str(exc)]
                self.log(f"❌ 配置自动加载失败: {exc}")

    def open_app_docs(self) -> None:
        """打开 App 模式文档"""

        doc_candidates = [
            Path.cwd() / "damai_appium" / "app.md",
            Path.cwd() / "doc" / "app.md",
        ]
        for doc_path in doc_candidates:
            if doc_path.exists():
                try:
                    os.startfile(doc_path)  # type: ignore[attr-defined]
                except Exception:
                    webbrowser.open(doc_path.as_uri())
                return
        messagebox.showinfo("提示", "未找到 App 模式文档，可访问项目 README 了解详情。")

    def load_app_config(self) -> None:
        """加载 App 模式配置"""

        if not APPIUM_AVAILABLE or AppTicketConfig is None:
            messagebox.showerror("错误", "当前环境未启用 Appium，无法加载配置。")
            return

        config_path = self.app_config_path_var.get().strip()
        if not config_path:
            messagebox.showwarning("提示", "请先选择配置文件路径。")
            return

        path = Path(config_path)
        if not path.exists():
            messagebox.showerror("错误", f"配置文件不存在: {path}")
            return

        if self.mode_var.get() == "app":
            self.mark_step("3. 参数配置", "active")

        try:
            config = AppTicketConfig.load(path)
            self.app_loaded_config = config
            self.app_config_data = {
                "path": str(path),
                "config": config,
            }
            self._populate_app_form(config)
            self.app_config_status.config(text="配置加载成功", foreground="green")
            self.log(f"✅ 已加载 App 配置: {path.name}")
            self._last_config_errors = []

            if self.mode_var.get() == "app":
                self.mark_step("3. 参数配置", "completed")
            self._refresh_app_start_button()
        except Exception as exc:  # noqa: BLE001
            self.app_config_status.config(text="配置加载失败", foreground="red")
            self.app_config_ready = False
            if ConfigValidationError is not None and isinstance(exc, ConfigValidationError):
                errors = list(exc.errors)
                self._last_config_errors = errors
                self._show_config_validation_error("配置校验失败", exc.message, errors)
            else:
                self._last_config_errors = [str(exc)]
                messagebox.showerror("错误", f"配置加载失败: {exc}")
                self.log(f"❌ 配置加载失败: {exc}")

    def save_app_config(self) -> None:
        """保存 App 模式配置到文件"""
        
        if not APPIUM_AVAILABLE or AppTicketConfig is None:
            messagebox.showerror("错误", "当前环境未启用 Appium，无法保存配置。")
            return
        
        config_path = self.app_config_path_var.get().strip()
        if not config_path:
            messagebox.showwarning("提示", "请先选择配置文件路径。")
            return
        
        path = Path(config_path)
        
        try:
            # 从表单收集配置
            config = self._collect_app_config_from_form(strict=True)
            
            # 保存配置到文件

            with open(path, 'w', encoding='utf-8') as f:
                json.dump(asdict(config), f, ensure_ascii=False, indent=2)
            
            # 更新状态
            self.app_config_status.config(text="配置保存成功", foreground="green")
            self.log(f"✅ 已保存 App 配置到: {path.name}")
            
            # 更新内存中的配置
            self.app_loaded_config = config
            self.app_config_data["config"] = config
            
        except Exception as exc:  # noqa: BLE001
            self.app_config_status.config(text="配置保存失败", foreground="red")
            if ConfigValidationError is not None and isinstance(exc, ConfigValidationError):
                errors = list(exc.errors)
                self._last_config_errors = errors
                self._show_config_validation_error("配置校验失败", exc.message, errors)
            else:
                self._last_config_errors = [str(exc)]
                messagebox.showerror("错误", f"配置保存失败: {exc}")
                self.log(f"❌ 配置保存失败: {exc}")

    def _save_web_config(self) -> None:
        """保存 Web 模式配置到文件"""
        try:
            # Web 模式配置保存到 config.json
            config_path = "config.json"
            path = Path(config_path)
            
            # 确保配置存在
            if not self.config:
                self.log("⚠️ Web 配置尚未完成，跳过保存")
                return
            
            # 添加目标 URL 到配置
            web_config = self.config.copy()
            if hasattr(self, 'target_url'):
                web_config['target_url'] = self.target_url
            
            # 保存配置到文件
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(web_config, f, ensure_ascii=False, indent=2)
            
            self.log(f"✅ 已保存 Web 配置到: {path.name}")
        except Exception as exc:  # noqa: BLE001
            self.log(f"❌ 保存 Web 配置失败: {exc}")
    
    def _set_app_summary_text(self, config: Any) -> None:
        """更新配置摘要显示"""

        self.app_summary_text.config(state="normal")
        self.app_summary_text.delete("1.0", tk.END)

        if not config:
            self.app_summary_text.insert(
                tk.END,
                "暂无有效配置，请在左侧表单填写 Appium 服务、设备信息和抢票参数。",
            )
            self.app_summary_text.config(state="disabled")
            return

        summary_lines = [
            f"🔌 Appium 服务: {config.server_url}",
        ]
        if config.city:
            summary_lines.append(f"🏙️ 城市: {config.city}")
        if config.keyword:
            summary_lines.append(f"🔎 关键词: {config.keyword}")
        if config.price:
            summary_lines.append(f"💰 价格: {config.price}")
        if config.price_index is not None:
            summary_lines.append(f"🎯 价格索引: {config.price_index}")
        summary_lines.append("👥 观演人: 默认全选")
        summary_lines.append(f"🕒 等待超时: {config.wait_timeout}s")
        summary_lines.append(f"🔁 重试间隔: {config.retry_delay}s")

        if getattr(self, "app_detected_devices", None):
            summary_lines.append("📱 已连接设备: " + ", ".join(self.app_detected_devices))
        elif self.mode_var.get() == "app":
            summary_lines.append("📱 已连接设备: 暂未检测到，可在“环境检测”后查看日志。")

        self.app_summary_text.insert(tk.END, "\n".join(summary_lines))
        self.app_summary_text.config(state="disabled")

    # ------------------------------
    # 定时抢票：预约、解析、倒计时、预热与触发
    # ------------------------------
    def _schedule_start_clicked(self) -> None:
        """预约定时抢票：校验模式/配置/时间并启动倒计时。"""
        if self.mode_var.get() != "app":
            messagebox.showwarning("提示", "请先切换到 App 模式")
            return
        if not (self.app_env_ready and self.app_config_ready):
            messagebox.showwarning("提示", "请先完成环境检测与参数配置")
            return

        target_epoch = None
        selection = ""
        
        # 从日期时间选择器获取日期时间
        selected_dt = self.schedule_datetime_picker.get_datetime()
        if selected_dt is None:
            messagebox.showerror("错误", "请选择开抢时间")
            return
            
        target_epoch = time.mktime(selected_dt.timetuple())
        selection = selected_dt.strftime("%Y-%m-%d %H:%M:%S")
        
        # 检查时间是否在未来
        if target_epoch <= time.time():
            messagebox.showerror("错误", "开抢时间不能早于当前时间")
            return

        now = time.time()
        if target_epoch <= now:
            messagebox.showerror("错误", "开抢时间不能早于当前时间")
            return

        
        self.schedule_status_var.set("已预约：倒计时准备中…")
        self.log(f"⏰ 已预约定时抢票：{selection}")
        # 计算并显示剩余时间
        remaining_seconds = int(target_epoch - now)
        remaining_time = time.strftime("%H:%M:%S", time.gmtime(remaining_seconds))
        self.log(f"📅 距离开抢还有：{remaining_time}")
        
        # 保存配置到文件
        self.save_app_config()
        
        # 禁用预约按钮，防止重复点击
        self.schedule_start_btn.config(state="disabled")
        
        # 预热相关状态初始化
        self._preheat_executed = False
        
        # 定义倒计时更新回调函数
        def on_countdown_update(remaining):
            try:
                warmup = max(int(self.schedule_warmup_var.get() or 0), 0)
            except Exception:
                warmup = 0
            
            # 更新状态文本，包含预热信息
            self.schedule_status_var.set(f"倒计时：{remaining} 秒（预热 {warmup}s）")
            
            # 预热检查触发点 - 当剩余时间小于等于预热秒数且未执行过预热时触发
            if warmup > 0 and remaining <= warmup and not self._preheat_executed:
                # 使用 after_idle 执行日志记录，避免阻塞主线程
                def log_preheat_start():
                    self.log("🔧 进入预热阶段，开始执行城市选择和搜索目标")
                self.root.after_idle(log_preheat_start)
                
                self._preheat_executed = True  # 立即标记为已执行，避免重复触发
                # 在单独的线程中执行预热操作，避免阻塞倒计时
                def run_preheat():
                    try:
                        # 执行预热健康检查
                        self._preheat_checks()
                        
                        # 执行实际的预热操作（城市选择和搜索）
                        if APPIUM_AVAILABLE and DamaiAppTicketRunner is not None:
                            config = self._collect_app_config_from_form()
                            self.app_runner = DamaiAppTicketRunner(
                                config=config,
                                logger=self._app_runner_logger,
                                stop_signal=lambda: self.app_should_stop,
                            )
                            self.app_runner.preheat()
                            # 使用 after_idle 执行日志记录，避免阻塞主线程
                            self.root.after_idle(lambda: self.log("✅ 预热完成：已连接Appium、选择城市并搜索目标"))
                        else:
                            # 使用 after_idle 执行日志记录，避免阻塞主线程
                            self.root.after_idle(lambda: self.log("⚠️ Appium环境不可用，跳过预热操作"))
                    except Exception as exc:  # noqa: BLE001
                        self.root.after_idle(lambda: self.schedule_status_var.set(f"预热失败：{exc}"))
                        self.root.after_idle(lambda: self.countdown_timer.stop())
                
                # 启动预热线程
                preheat_thread = threading.Thread(target=run_preheat, daemon=True)
                preheat_thread.start()
        
        # 定义倒计时结束回调函数
        def on_countdown_finish():
            # 清理预热相关属性
            if hasattr(self, '_preheat_executed'):
                delattr(self, '_preheat_executed')
                
            self.schedule_status_var.set("到点执行：开始抢票…")
            
            # 如果有预热好的runner，直接使用它的run方法
            if hasattr(self, 'app_runner') and self.app_runner is not None:
                try:
                    max_retries = max(1, int(self.app_retries_var.get()))
                except Exception:
                    max_retries = 1
                    
                self.start_btn.config(state="disabled")
                self.stop_btn.config(state="normal")
                self.is_grabbing = True
                self.app_should_stop = False
                self.last_app_report = None
                self.app_metrics_var.set("App 抢票流程运行中…")
                self.mark_step("4. 开始抢票", "active")
                self.log("🎯 使用预热好的环境开始执行 App 抢票流程...")
                
                # 在新线程中运行抢票流程
                self.app_runner_thread = threading.Thread(
                    target=self._run_preheated_app_runner,
                    args=(max_retries,),
                    daemon=True,
                )
                self.app_runner_thread.start()
        
        # 启动新的倒计时组件
        self.countdown_timer.start(remaining_seconds, on_finish=on_countdown_finish, on_update=on_countdown_update)

    def _parse_start_time_to_epoch(self, text: str) -> Optional[float]:
        """解析用户输入的开抢时间为 epoch 秒，支持 ISO8601 或 'YYYY-MM-DD HH:MM:SS' 本地时区。"""
        if not text:
            return None
        # 优先尝试 ISO8601
        try:
            dt = datetime.fromisoformat(text)
            return dt.timestamp()
        except Exception:
            pass
        # 回退为 'YYYY-MM-DD HH:MM:SS' 本地时区
        try:
            dt = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
            return time.mktime(dt.timetuple())
        except Exception:
            return None

    def _show_datetime_picker(self) -> None:
        """显示日期时间选择器"""
        from tkinter import simpledialog
        from datetime import datetime
        
        # 获取当前时间作为默认值
        now = datetime.now()
        default_datetime = now.strftime("%Y-%m-%d %H:%M")
        
        # 显示输入对话框
        datetime_str = simpledialog.askstring(
            "选择开抢时间",
            "请输入开抢时间 (格式: YYYY-MM-DD HH:MM)",
            parent=self.root,
            initialvalue=default_datetime
        )
        
        if datetime_str:
            # 验证格式
            try:
                # 尝试解析为 YYYY-MM-DD HH:MM 格式
                dt = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")
                # 更新输入框（使用新的DateTimePicker组件）
                if hasattr(self, 'schedule_datetime_picker'):
                    try:
                        self.schedule_datetime_picker.selected_datetime = dt
                        self.schedule_datetime_picker.update_display(dt)
                    except Exception:
                        pass
            except ValueError:
                try:
                    # 尝试解析为 YYYY-MM-DD HH:MM:SS 格式
                    dt = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M:%S")
                    # 更新输入框（使用新的DateTimePicker组件）
                    if hasattr(self, 'schedule_datetime_picker'):
                        try:
                            self.schedule_datetime_picker.selected_datetime = dt
                            self.schedule_datetime_picker.update_display(dt)
                        except Exception:
                            pass
                except ValueError:
                    messagebox.showerror("错误", "日期时间格式不正确，请使用 YYYY-MM-DD HH:MM 或 YYYY-MM-DD HH:MM:SS 格式")
    

        
        if not self._schedule_running:
            return

        # 初始化必要的属性
        if not hasattr(self, '_preheat_executed'):
            self._preheat_executed = False
        if not hasattr(self, '_current_displayed_time'):
            self._current_displayed_time = -1  # 初始值设为-1，确保第一次能更新

        # 每次都重新计算剩余时间，确保基于实际当前时间
        now = time.time()
        remaining = max(int(self._schedule_target_epoch - now), 0)
        try:
            warmup = max(int(self.schedule_warmup_var.get() or 0), 0)
        except Exception:
            warmup = 0

        if remaining > 0:
            
            # 只有当剩余时间确实减少了才更新UI，确保不会跳过数字
            if remaining != self._current_displayed_time:
                self.schedule_status_var.set(f"倒计时：{remaining} 秒（预热 {warmup}s）")
                self._current_displayed_time = remaining
            
            # 预热检查触发点 - 当剩余时间小于等于预热秒数且未执行过预热时触发
            if warmup > 0 and remaining <= warmup and not self._preheat_executed:
                # 使用 after_idle 执行日志记录，避免阻塞主线程
                def log_preheat_start():
                    self.log("🔧 进入预热阶段，开始执行城市选择和搜索目标")
                self.root.after_idle(log_preheat_start)
                
                self._preheat_executed = True  # 立即标记为已执行，避免重复触发
                
                # 在单独的线程中执行预热操作，避免阻塞倒计时
                def run_preheat():
                    try:
                        # 执行预热健康检查
                        self._preheat_checks()
                        
                        # 执行实际的预热操作（城市选择和搜索）
                        if APPIUM_AVAILABLE and DamaiAppTicketRunner is not None:
                            config = self._collect_app_config_from_form()
                            self.app_runner = DamaiAppTicketRunner(
                                config=config,
                                logger=self._app_runner_logger,
                                stop_signal=lambda: self.app_should_stop,
                            )
                            self.app_runner.preheat()
                            # 使用 after_idle 执行日志记录，避免阻塞主线程
                            self.root.after_idle(lambda: self.log("✅ 预热完成：已连接Appium、选择城市并搜索目标"))
                        else:
                            # 使用 after_idle 执行日志记录，避免阻塞主线程
                            self.root.after_idle(lambda: self.log("⚠️ Appium环境不可用，跳过预热操作"))
                    except Exception as exc:  # noqa: BLE001
                        self.root.after_idle(lambda: self.schedule_status_var.set(f"预热失败：{exc}"))
                        self.root.after_idle(lambda: setattr(self, '_schedule_running', False))
                
                # 启动预热线程
                import threading
                preheat_thread = threading.Thread(target=run_preheat, daemon=True)
                preheat_thread.start()
            # 使用高频检查（100ms）确保不会跳过数字
            self._schedule_timer_id = self.root.after(100, self._schedule_tick)
            return

        # 到点执行
        self.schedule_status_var.set("到点执行：开始抢票…")
        self._schedule_running = False
        self._schedule_timer_id = None
        
        # 清理倒计时相关属性
        if hasattr(self, '_preheat_executed'):
            delattr(self, '_preheat_executed')
        if hasattr(self, '_current_displayed_time'):
            delattr(self, '_current_displayed_time')
        
        # 如果有预热好的runner，直接使用它的run方法
        if hasattr(self, 'app_runner') and self.app_runner is not None:
            try:
                max_retries = max(1, int(self.app_retries_var.get()))
            except Exception:
                max_retries = 1
                
            self.start_btn.config(state="disabled")
            self.stop_btn.config(state="normal")
            self.is_grabbing = True
            self.app_should_stop = False
            self.last_app_report = None
            self.app_metrics_var.set("App 抢票流程运行中…")
            self.mark_step("4. 开始抢票", "active")
            self.log("🎯 使用预热好的环境开始执行 App 抢票流程...")
            
            # 在新线程中运行抢票流程
            self.app_runner_thread = threading.Thread(
                target=self._run_preheated_app_runner,
                args=(max_retries,),
                daemon=True,
            )
            self.app_runner_thread.start()
        else:
            # 没有预热好的runner，使用传统方式
            self._start_app_grabbing()

    def _preheat_checks(self) -> None:
        """执行预热健康检查：Appium /status 与 adb 设备可用性。"""
        # Appium 服务探活与能力解析
        config = self._validate_app_server()
        # 设备就绪性检查
        has_ready_device = self._detect_connected_devices()
        if not has_ready_device:
            raise RuntimeError("未检测到可用设备，请检查 USB/授权后重试")
        # 更新摘要（可选） - 确保在主线程中执行UI更新
        try:
            self.root.after(0, lambda: self._set_app_summary_text(config))
            self.root.after(0, lambda: self.schedule_status_var.set("预热检查通过"))
        except Exception:  # noqa: BLE001
            pass

    def _schedule_cancel(self) -> None:
        """取消预约：停止倒计时并重置状态。"""
        # 使用新的倒计时组件停止倒计时
        self.countdown_timer.stop()
        
        # 清理倒计时相关属性
        if hasattr(self, '_preheat_executed'):
            delattr(self, '_preheat_executed')
            
        self.schedule_status_var.set("未预约")
        self.log("❌ 已取消定时预约")
        
        # 恢复预约按钮状态
        self.schedule_start_btn.config(state="normal")

    def update_step(self, step_index, status="active"):
        """更新步骤状态"""
        colors = {
            "inactive": "gray",
            "active": "blue", 
            "completed": "green",
            "error": "red"
        }
        
        if 0 <= step_index < len(self.step_labels):
            color = colors.get(status, "gray")
            self.step_labels[step_index].config(foreground=color)
            if status == "completed":
                text = "✓ " + self.steps[step_index]
                self.step_labels[step_index].config(text=text)
    
    def mark_step(self, step_label: str, status: str = "active") -> None:
        """根据名称更新当前模式步骤状态"""

        try:
            index = self.steps.index(step_label)
        except (ValueError, AttributeError):
            return
        self.update_step(index, status)
                
    def _on_log_filter_changed(self, *_args: Any) -> None:
        self._refresh_log_view()

    def clear_logs(self) -> None:
        """清空日志窗口与历史记录。"""

        self.log_entries.clear()
        if hasattr(self, "log_text"):
            self.log_text.delete("1.0", tk.END)
            self.log_text.see(tk.END)
            self.root.update_idletasks()

    def _infer_log_level(self, message: str) -> str:
        normalized = message.strip()
        lowered = normalized.lower()

        if normalized.startswith("❌") or "错误" in normalized or "fail" in lowered:
            return "error"
        if normalized.startswith("⚠️") or "警告" in normalized or "warning" in lowered:
            return "warning"
        if normalized.startswith("✅") or normalized.startswith("✔") or "成功" in normalized:
            return "success"
        if normalized.startswith("ℹ️") or normalized.startswith("📢"):
            return "info"
        return "info"

    def _log_passes_filter(self, level: str) -> bool:
        selected = self.log_filter_var.get()
        if selected == "全部":
            return True

        mapping = {
            "仅信息": "info",
            "仅成功": "success",
            "仅警告": "warning",
            "仅错误": "error",
        }
        target_level = mapping.get(selected)
        return target_level is None or level == target_level

    def _append_log_entry(self, entry: Tuple[str, str, str], *, auto_scroll: bool = True) -> None:
        timestamp, message, _level = entry
        log_message = f"[{timestamp}] {message}\n"
        self.log_text.insert(tk.END, log_message)
        if auto_scroll:
            self.log_text.see(tk.END)

    def _refresh_log_view(self) -> None:
        if not hasattr(self, "log_text"):
            return

        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", tk.END)

        for entry in self.log_entries:
            if self._log_passes_filter(entry[2]):
                self._append_log_entry(entry, auto_scroll=False)

        self.log_text.see(tk.END)
        self.root.update_idletasks()

    def log(self, message: str, level: Optional[str] = None) -> None:
        """添加日志信息并记录在历史中。"""

        if level is None:
            level = self._infer_log_level(message)

        timestamp = time.strftime("%H:%M:%S")
        entry = (timestamp, message, level)
        self.log_entries.append(entry)

        if not hasattr(self, "log_text"):
            return

        if self._log_passes_filter(level):
            self._append_log_entry(entry)
        else:
            # 过滤后不显示，但保持滚动位置
            self.log_text.see(tk.END)
            self.root.update_idletasks()

    def _update_app_metrics_display(self, report: Optional[Any]) -> None:
        if report is None or not hasattr(report, "metrics"):
            self.app_metrics_var.set("尚未运行 App 抢票流程")
            return

        metrics = report.metrics
        duration = max(metrics.end_time - metrics.start_time, 0.0)
        retries = max(metrics.attempts - 1, 0)
        finished_at = datetime.fromtimestamp(metrics.end_time).strftime("%H:%M:%S")

        lines = [
            f"状态：{'成功' if metrics.success else '失败'}",
            f"总耗时：{duration:.2f} 秒",
            f"尝试次数：{metrics.attempts}（重试 {retries} 次）",
            f"最终阶段：{metrics.final_phase.value}",
            f"结束时间：{finished_at}",
        ]

        if not metrics.success:
            failure_text = self._format_failure_for_display(report)
            lines.append(f"失败说明：{failure_text}")

        self.app_metrics_var.set("\n".join(lines))

    def _format_failure_for_display(self, report: Optional[Any]) -> str:
        if report is None or not hasattr(report, "metrics"):
            return "未能成功抢票，原因未知。"

        metrics = report.metrics
        base_reason = metrics.failure_reason or "未能成功抢票"
        code = getattr(metrics, "failure_code", None)

        if FailureReason is None or code is None:
            return base_reason

        if code == FailureReason.MAX_RETRIES:
            return f"多次尝试仍未成功（共 {metrics.attempts} 次）。建议检查网络或稍后重试。"
        if code == FailureReason.APPIUM_CONNECTION:
            return f"无法连接 Appium 服务：{base_reason}"
        if code == FailureReason.FLOW_FAILURE:
            return f"流程执行失败：{base_reason}"
        if code == FailureReason.UNEXPECTED:
            return f"发生未预期的错误：{base_reason}"
        if code == FailureReason.USER_STOP:
            return base_reason or "流程已被用户停止。"
        return base_reason

    def export_logs(self) -> None:
        default_name = datetime.now().strftime("damai_logs_%Y%m%d_%H%M%S.json")
        target_path = filedialog.asksaveasfilename(
            title="导出运行日志",
            defaultextension=".json",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
            initialfile=default_name,
        )
        if not target_path:
            return

        payload = {
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "app_run_report": self.last_app_report.to_dict() if self.last_app_report else None,
            "log_entries": [
                {"timestamp": ts, "message": msg, "level": level}
                for ts, msg, level in self.log_entries
            ],
        }

        try:
            with open(target_path, "w", encoding="utf-8") as fp:
                json.dump(payload, fp, ensure_ascii=False, indent=2)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("导出失败", f"无法写入日志文件：{exc}")
            return

        self.log(f"💾 日志已导出到 {target_path}")
        
    def clear_url_placeholder(self, event):
        """清除URL输入框占位符"""
        if self.url_entry.get() == "请输入大麦网演出详情页链接...":
            self.url_entry.delete(0, tk.END)
            
    def check_environment(self):
        """检测环境"""
        step_label = "1. 环境检测"
        self.mark_step(step_label, "active")
        self.log("🔍 开始检测环境...")

        if self.mode_var.get() == "app":
            self._check_app_environment()
        else:
            self._check_web_environment()

    def _check_web_environment(self) -> None:
        try:
            python_version = sys.version.split()[0]
            self.log(f"✅ Python版本: {python_version}")

            if not SELENIUM_AVAILABLE:
                raise RuntimeError("Selenium未安装，请先安装：pip install selenium")
            self.log("✅ Selenium已安装")

            options = webdriver.ChromeOptions()
            options.add_argument('--headless')
            driver = webdriver.Chrome(options=options)
            driver.quit()
            self.log("✅ Chrome浏览器驱动正常")

        except Exception as exc:
            self.log(f"❌ 环境检测出错: {exc}")
            self.env_status_label.config(text="环境检测异常", foreground="red")
            self.mark_step("1. 环境检测", "error")
            messagebox.showerror("错误", str(exc))
            return

        self.env_status_label.config(text="环境检测完成", foreground="green")
        self.mark_step("1. 环境检测", "completed")
        self.log("✅ 环境检测完成，所有组件正常")

        if hasattr(self, "login_btn"):
            self.login_btn.config(state="normal")
        if hasattr(self, "analyze_btn"):
            self.analyze_btn.config(state="normal")

        self._try_auto_login()

    # ------------------------------------------------------------------
    # App 模式依赖检测
    # ------------------------------------------------------------------

    def _resolve_cli_command(self, command: str) -> Optional[str]:
        """Locate an executable on PATH with Windows fallbacks."""

        resolved = shutil.which(command)
        if resolved:
            return resolved

        if os.name == "nt":
            candidates: list[Path] = []

            appdata = os.environ.get("APPDATA")
            if appdata:
                npm_dir = Path(appdata) / "npm"
                candidates.extend(
                    npm_dir / f"{command}{suffix}"
                    for suffix in (".cmd", ".exe", "")
                )

            program_files = os.environ.get("PROGRAMFILES")
            if program_files:
                candidates.append(Path(program_files) / "nodejs" / f"{command}.exe")

            program_files_x86 = os.environ.get("PROGRAMFILES(X86)")
            if program_files_x86:
                candidates.append(Path(program_files_x86) / "nodejs" / f"{command}.exe")

            for candidate in candidates:
                if candidate and candidate.exists():
                    return str(candidate)

        return None

    def _check_cli_dependency(self, command: str, args: List[str], friendly_name: str) -> Tuple[bool, str]:
        """尝试运行外部命令来检查依赖是否存在。"""

        executable = self._resolve_cli_command(command)
        if not executable:
            return False, f"未找到 {friendly_name}（命令：{command}），请先安装并添加到 PATH。"

        try:
            result = subprocess.run(  # noqa: S603,S607
                [executable, *args],
                capture_output=True,
                text=True,
                timeout=8,
            )
        except Exception as exc:  # noqa: BLE001
            return False, f"{friendly_name} 检测失败：{exc}"

        output = (result.stdout or result.stderr or "").strip()
        if result.returncode != 0:
            message = output or "未知错误"
            return False, f"{friendly_name} 返回码 {result.returncode}：{message}"

        summary = output.splitlines()[0] if output else "检测通过"
        if executable != command:
            summary = f"{summary}（路径：{executable}）"
        return True, summary

    def _check_node_cli(self) -> Tuple[bool, str]:
        return self._check_cli_dependency("node", ["--version"], "Node.js")

    def _check_appium_cli(self) -> Tuple[bool, str]:
        return self._check_cli_dependency("appium", ["-v"], "Appium CLI")

    def _check_adb_cli(self) -> Tuple[bool, str]:
        return self._check_cli_dependency("adb", ["version"], "ADB")

    def _check_app_environment(self) -> None:
        self.app_env_ready = False
        tracking_device_status = self.mode_var.get() == "app"

        if tracking_device_status:
            self._device_refresh_in_progress = True
            if hasattr(self, "app_device_refresh_btn") and (
                APPIUM_AVAILABLE and parse_adb_devices is not None
            ):
                self.app_device_refresh_btn.config(state="disabled")
            if APPIUM_AVAILABLE and parse_adb_devices is not None:
                self._set_device_status("正在检查 Appium 环境...", color="blue")
                self._set_device_detail("正在请求 Appium 服务并检测已连接的设备...", color="blue")
        try:
            config: Any = None

            node_ok, node_message = self._check_node_cli()
            if node_ok:
                self.log(f"✅ Node.js: {node_message}")
            else:
                install_hint = (
                    "请先安装 Node.js（https://nodejs.org/），安装时勾选添加到 PATH，"
                    "完成后重新启动本工具。"
                )
                self.log(f"❌ {node_message}")
                self.env_status_label.config(text="缺少 Node.js 环境", foreground="red")
                self.mark_step("1. 环境检测", "error")
                if tracking_device_status:
                    self._set_device_status("无法检测设备", color="red")
                    self._set_device_detail(install_hint, color="red")
                messagebox.showerror("缺少依赖", f"{node_message}\n\n{install_hint}")
                return

            appium_cli_ok, appium_message = self._check_appium_cli()
            if appium_cli_ok:
                self.log(f"✅ Appium CLI: {appium_message}")
            else:
                install_hint = (
                    "未检测到 Appium CLI。可在命令行执行 `npm install -g appium` 安装，"
                    "或使用 Appium Inspector 自带的服务器。安装完成后请重新打开本程序。"
                )
                self.log(f"❌ {appium_message}")
                self.env_status_label.config(text="缺少 Appium CLI", foreground="red")
                self.mark_step("1. 环境检测", "error")
                if tracking_device_status:
                    self._set_device_status("无法检测设备", color="red")
                    self._set_device_detail(install_hint, color="red")
                messagebox.showerror("缺少依赖", f"{appium_message}\n\n{install_hint}")
                return

            adb_ok, adb_message = self._check_adb_cli()
            if adb_ok:
                self.log(f"✅ ADB: {adb_message}")
            else:
                adb_hint = (
                    "未检测到 adb，请安装 Android 平台工具（Platform Tools）并将其加入 PATH。"
                    "没有 adb 将无法列出设备。"
                )
                self.log(f"⚠️ {adb_message}")
                if tracking_device_status:
                    self._set_device_status("未检测到 adb", color="orange")
                    self._set_device_detail(adb_hint, color="orange")

            if not APPIUM_AVAILABLE or DamaiAppTicketRunner is None:
                self.env_status_label.config(text="Appium 环境不可用", foreground="red")
                self.mark_step("1. 环境检测", "error")
                self._reset_device_status_ui()
                messagebox.showerror("错误", "未检测到 Appium 运行环境，请先安装依赖并配置 Python 包。")
                return

            try:
                python_version = sys.version.split()[0]
                self.log(f"✅ Python版本: {python_version}")
            except Exception:
                pass

            if not self.app_config_ready:
                self.log("⚠️ 尚未完成配置表单，检测将使用当前输入的默认值。")
            else:
                self.mark_step("3. 参数配置", "completed")

            try:
                config = self._validate_app_server()
            except Exception as exc:  # noqa: BLE001
                self.env_status_label.config(text="Appium 服务异常", foreground="red")
                self.mark_step("1. 环境检测", "error")
                # 立即更新Appium按钮状态，修复检测到服务异常但按钮显示不一致的bug
                self._check_appium_status()
                messagebox.showerror("错误", f"Appium 服务不可用: {exc}")
                return

            if adb_ok:
                has_ready_device = self._detect_connected_devices()
            else:
                has_ready_device = False
            self._update_device_status_from_result(has_ready_device)

            self.app_env_ready = True
            if has_ready_device:
                status_text = "Appium 环境准备就绪"
                status_color = "green"
                self.mark_step("2. 设备检查", "completed")
                self.log("✅ Appium 环境检测通过，可以连接设备")
            else:
                status_text = "Appium 服务可用（未检测到设备）"
                status_color = "orange"
                self.mark_step("2. 设备检查", "error")
                self.log("⚠️ Appium 服务正常，但未检测到可用设备，请检查 adb 连接或设备授权。")

            self.env_status_label.config(text=status_text, foreground=status_color)
            self.mark_step("1. 环境检测", "completed")
            
            # 更新Appium状态变量，修复检测环境后状态不一致的bug
            self._check_appium_status()

            if config is not None:
                try:
                    self._set_app_summary_text(config)
                except Exception:
                    pass

            if self.app_config_ready and hasattr(self, "start_btn"):
                self.start_btn.config(state="normal")
        finally:
            if tracking_device_status:
                self._device_refresh_in_progress = False
                if hasattr(self, "app_device_refresh_btn"):
                    can_refresh = APPIUM_AVAILABLE and parse_adb_devices is not None
                    state = "normal" if can_refresh else "disabled"
                    self.app_device_refresh_btn.config(state=state)

    # ------------------------------
    # App 模式：Appium 服务启动/停止控制（新控制台）
    # ------------------------------
    def _toggle_appium_server(self) -> None:
        """根据当前状态启动或停止 Appium 服务器（通过 cmd.exe /k appium）。"""
        try:
            if self.appium_running and self.appium_pid:
                self._stop_appium_server()
            else:
                self._start_appium_server()
        except Exception as exc:  # noqa: BLE001
            self.log(f"❌ 切换 Appium 状态失败: {exc}")
            messagebox.showerror("错误", f"切换 Appium 状态失败：{exc}")

    def _start_appium_server(self) -> None:
        """在新的命令提示符窗口启动 Appium（不阻塞 GUI）。"""
        if self.appium_running:
            messagebox.showinfo("提示", "Appium 已在运行中。")
            return

        # 友好提示：若未在 PATH 检测到 appium，仍尝试启动，但给出提示
        if not self._resolve_cli_command("appium"):
            self.log("⚠️ 未在 PATH 中检测到 appium 命令，仍尝试通过 cmd.exe 启动。")

        try:
            creation_flags = subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0
        except Exception:
            creation_flags = 0

        try:
            # 在新的控制台窗口执行：cmd.exe /k appium
            proc = subprocess.Popen(  # noqa: S603,S607
                ["cmd.exe", "/k", "appium"],
                creationflags=creation_flags,
            )
            self.appium_process = proc
            self.appium_pid = proc.pid
            self.appium_running = True
            self.appium_status_var.set(f"Appium 运行中（PID {proc.pid}）")
            try:
                self.appium_toggle_btn.config(text="⏹ 停止 Appium")
            except Exception:
                pass
            self.log(f"✅ 已启动 Appium（新控制台，PID {proc.pid}）")
        except FileNotFoundError as exc:
            self.log(f"❌ 启动 Appium 失败：{exc}")
            messagebox.showerror("错误", f"无法启动命令提示符：{exc}\n请确认系统可用 cmd.exe。")
        except Exception as exc:  # noqa: BLE001
            self.log(f"❌ 启动 Appium 失败：{exc}")
            messagebox.showerror("错误", f"启动 Appium 失败：{exc}")

    def _stop_appium_server(self) -> None:
        """使用 taskkill /T /F 结束整棵进程树，可靠停止 Appium。"""
        if not self.appium_pid:
            messagebox.showinfo("提示", "当前未检测到 Appium 进程。")
            return

        # 若控制台已被用户手动关闭，复位状态即可
        try:
            if self.appium_process is not None and (self.appium_process.poll() is not None):
                self._reset_appium_state()
                self.log("ℹ️ Appium 控制台已关闭，状态已复位。")
                return
        except Exception:
            pass

        try:
            result = subprocess.run(  # noqa: S603,S607
                ["taskkill", "/T", "/F", "/PID", str(self.appium_pid)],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                self.log(f"✅ 已停止 Appium（PID {self.appium_pid}）")
            else:
                msg = (result.stderr or result.stdout or "").strip() or "未知错误"
                self.log(f"⚠️ 停止 Appium 返回码 {result.returncode}：{msg}")
        except Exception as exc:  # noqa: BLE001
            self.log(f"❌ 停止 Appium 失败：{exc}")
            messagebox.showerror("错误", f"停止 Appium 失败：{exc}")
            return

        self._reset_appium_state()

    def _reset_appium_state(self) -> None:
        """复位 Appium 控制状态与按钮文案。"""
        self.appium_running = False
        self.appium_pid = None
        self.appium_process = None
        self.appium_status_var.set("Appium 未运行")
        try:
            self.appium_toggle_btn.config(text="🚀 启动 Appium")
        except Exception:
            pass
    
    def _start_appium_status_check(self) -> None:
        """启动 Appium 状态检测定时器"""
        if self._appium_status_timer_id:
            self.root.after_cancel(self._appium_status_timer_id)
        self._appium_status_timer_id = self.root.after(self._appium_status_check_interval, self._check_appium_status)
    
    def _check_appium_status(self) -> None:
        """检测 Appium 实际运行状态"""
        try:
            import requests
            # 尝试连接 Appium 服务
            response = requests.get("http://localhost:4723/status", timeout=1)
            is_running = response.status_code == 200
        except:
            is_running = False
        
        # 更新状态
        self._update_appium_button_state(is_running)
        # 继续下一次检测
        self._start_appium_status_check()
    
    def _update_appium_button_state(self, is_running: bool) -> None:
        """根据 Appium 实际运行状态更新按钮状态"""
        if not hasattr(self, "appium_toggle_btn") or not hasattr(self, "appium_status_var"):
            return
        
        # 如果状态没有变化，不需要更新
        if self.appium_running == is_running:
            return
        
        # 更新状态变量
        self.appium_running = is_running
        
        # 更新按钮文本和状态信息
        if is_running:
            self.appium_status_var.set("Appium 已运行")
            try:
                self.appium_toggle_btn.config(text="⏹ 停止 Appium")
            except Exception:
                pass
        else:
            self.appium_status_var.set("Appium 未运行")
            try:
                self.appium_toggle_btn.config(text="🚀 启动 Appium")
            except Exception:
                pass

    def _validate_app_server(self) -> Any:
        config = self._collect_app_config_from_form(strict=False)
        if config is None:
            error_detail = self._format_config_errors(self._last_config_errors)
            message = error_detail or "请先完善 App 配置后再检测服务"
            raise RuntimeError(message)

        try:
            caps = config.desired_capabilities
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"解析设备能力失败: {exc}") from exc

        server_url = config.server_url.rstrip("/")
        if not server_url:
            raise RuntimeError("Appium 服务地址不能为空")

        status_url = f"{server_url}/status"

        try:
            import urllib.request
            from urllib.error import URLError

            req = urllib.request.Request(status_url)
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status != 200:
                    raise RuntimeError(f"状态码异常: {response.status}")
                self.log("✅ Appium 服务响应正常")
                device_name = caps.get("deviceName") if isinstance(caps, dict) else None
                if device_name:
                    self.log(f"📱 目标设备: {device_name}")
        except URLError as exc:
            raise RuntimeError(f"无法连接 Appium 服务: {exc}") from exc
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"检测 Appium 服务失败: {exc}") from exc

        return config

    def _set_device_status(self, message: str, *, color: str = "gray") -> None:
        var = getattr(self, "app_device_status_var", None)
        if var is None:
            return
        var.set(message)
        if hasattr(self, "app_device_status_label"):
            self.app_device_status_label.config(foreground=color)

    def _set_device_detail(self, message: str, *, color: Optional[str] = None) -> None:
        var = getattr(self, "app_device_detail_var", None)
        if var is None:
            return
        var.set(message)
        if hasattr(self, "app_device_detail_label") and color is not None:
            self.app_device_detail_label.config(foreground=color)

    def _reset_device_status_ui(self) -> None:
        can_refresh = APPIUM_AVAILABLE and parse_adb_devices is not None
        if can_refresh:
            self._set_device_status("尚未检测设备", color="gray")
            hint = "点击“刷新设备”或执行环境检测查看最新状态。"
            self._set_device_detail(hint, color="gray")
        else:
            if not APPIUM_AVAILABLE:
                hint = "当前环境未启用 Appium，安装完成后可刷新设备列表。"
            else:
                hint = "缺少 adb 解析能力，安装 damai_appium 依赖后重启程序。"
            self._set_device_status("无法检测设备", color="red")
            self._set_device_detail(hint, color="red")

        if hasattr(self, "app_device_refresh_btn"):
            state = "normal" if can_refresh else "disabled"
            self.app_device_refresh_btn.config(state=state)
        if self.app_device_combobox is not None:
            self.app_device_combobox.set("")
            self.app_device_combobox.config(values=())
            self.app_device_combobox.config(state="disabled")
        if self.app_device_options_var is not None:
            self.app_device_options_var.set("")
        self.app_detected_device_records = []
        self._device_refresh_in_progress = False

    def _refresh_devices_clicked(self) -> None:
        if not (APPIUM_AVAILABLE and parse_adb_devices is not None):
            messagebox.showwarning("提示", "当前环境未启用 Appium 或缺少 adb 支持，请先完成依赖安装。")
            return

        if self._device_refresh_in_progress:
            self.log("ℹ️ 正在刷新设备列表，请稍候...")
            return

        self._device_refresh_in_progress = True
        if hasattr(self, "app_device_refresh_btn"):
            self.app_device_refresh_btn.config(state="disabled")

        self._set_device_status("正在刷新设备列表...", color="blue")
        self._set_device_detail("正在执行 adb devices -l，请稍候...", color="blue")

        # 使用 after 避免阻塞当前事件循环
        self.root.after(50, self._perform_device_refresh)

    def _perform_device_refresh(self) -> None:
        try:
            has_ready_device = self._detect_connected_devices()
            self._update_device_status_from_result(has_ready_device)
            
            # 更新环境检测标签和步骤状态，修复刷新设备后状态不一致的bug
            if has_ready_device:
                status_text = "Appium 环境准备就绪"
                status_color = "green"
                self.mark_step("2. 设备检查", "completed")
                self.log("✅ 已检测到可用设备，Appium 环境准备就绪")
            else:
                status_text = "Appium 服务可用（未检测到设备）"
                status_color = "orange"
                self.mark_step("2. 设备检查", "error")
                self.log("⚠️ Appium 服务正常，但未检测到可用设备，请检查 adb 连接或设备授权。")
            
            if hasattr(self, "env_status_label"):
                self.env_status_label.config(text=status_text, foreground=status_color)
            
            self.app_env_ready = has_ready_device
            self._update_app_summary_from_form()
        finally:
            self._device_refresh_in_progress = False
            if hasattr(self, "app_device_refresh_btn") and (APPIUM_AVAILABLE and parse_adb_devices is not None):
                self.app_device_refresh_btn.config(state="normal")

    def _update_device_status_from_result(self, has_ready_device: bool) -> None:
        if not (APPIUM_AVAILABLE and parse_adb_devices is not None):
            self._reset_device_status_ui()
            return

        combo = self.app_device_combobox
        if not self.app_detected_device_records and self.app_detected_devices:
            self.app_detected_device_records = [
                {"label": label, "serial": label}
                for label in self.app_detected_devices
            ]

        device_labels = [record.get("label", "") for record in self.app_detected_device_records]

        if has_ready_device and device_labels:
            device_count = len(device_labels)
            status_text = f"已检测到 {device_count} 台可用设备"
            self._set_device_status(status_text, color="green")

            list_detail = self._format_detected_device_list(self.app_detected_device_records)
            self._set_device_detail(list_detail, color="green")

            if combo is not None:
                combo.config(values=device_labels)
                combo.config(state="readonly")

                previous = self.app_device_options_var.get().strip() if self.app_device_options_var else ""
                if previous and previous in device_labels:
                    combo.set(previous)
                else:
                    combo.current(0)
                    if self.app_device_options_var is not None:
                        self.app_device_options_var.set(device_labels[0])

                self._on_device_selection_changed()
        else:
            hint = "请检查 USB 连接、驱动和授权状态，然后点击“刷新设备”。"
            self._set_device_status("未检测到可用设备", color="orange")
            self._set_device_detail(hint, color="orange")

            if combo is not None:
                combo.set("")
                combo.config(values=())
                combo.config(state="disabled")
            if self.app_device_options_var is not None:
                self.app_device_options_var.set("")

    def _format_detected_device_list(self, records: List[Dict[str, Any]]) -> str:
        lines: List[str] = []
        for idx, record in enumerate(records, start=1):
            label = record.get("label") or record.get("serial") or "未知设备"
            lines.append(f"{idx}. {label}")
        return "\n".join(lines) or "设备已成功连接，可直接开始抢票。"

    def _find_device_record_by_label(self, label: str) -> Optional[Dict[str, Any]]:
        for record in self.app_detected_device_records:
            if record.get("label") == label:
                return record
        return None

    def _apply_device_record_to_form(self, record: Dict[str, Any]) -> None:
        if not record:
            return

        device_name_value = record.get("model") or record.get("device") or record.get("serial") or ""
        if device_name_value:
            self.app_form_vars["device_name"].set(device_name_value)

        serial = record.get("serial", "")
        if serial:
            self.app_form_vars["udid"].set(serial)

        if not self.app_form_vars["automation_name"].get().strip():
            self.app_form_vars["automation_name"].set("UiAutomator2")

    def _build_device_detail_message(self, record: Dict[str, Any]) -> str:
        lines: List[str] = []
        primary_label = record.get("label") or record.get("serial") or "未知设备"
        lines.append(f"当前选择：{primary_label}")
        serial = record.get("serial")
        if serial:
            lines.append(f"序列号：{serial}")
        model = record.get("model")
        if model:
            lines.append(f"型号：{model}")
        device_name = record.get("device")
        if device_name and device_name != model:
            lines.append(f"设备代号：{device_name}")
        transport_id = record.get("transport_id")
        if transport_id:
            lines.append(f"Transport ID：{transport_id}")
        lines.append("已自动填充“设备名称”和“设备 UDID”字段。")
        lines.append("如需修改，可在下方表单中手动调整。")

        other_devices = [
            other.get("label") or other.get("serial") or "未知设备"
            for other in self.app_detected_device_records
            if other is not record
        ]
        if other_devices:
            lines.append("其他设备：")
            lines.extend(f"• {label}" for label in other_devices)
        return "\n".join(lines)

    def _on_device_selection_changed(self, event: Optional[Any] = None) -> None:
        if self.app_device_options_var is None:
            return

        selected_label = self.app_device_options_var.get().strip()
        if not selected_label:
            return

        record = self._find_device_record_by_label(selected_label)
        if record is None:
            return

        self._apply_device_record_to_form(record)
        detail_message = self._build_device_detail_message(record)
        self._set_device_detail(detail_message, color="green")

        if event is not None:
            display_label = record.get("label") or record.get("serial") or "未知设备"
            self.log(f"ℹ️ 已应用设备：{display_label}")

    def _detect_connected_devices(self) -> bool:
        """Run ``adb devices -l`` and record any connected Android devices."""

        self.app_detected_devices = []
        self.app_detected_device_records = []

        if parse_adb_devices is None:
            return False

        adb_command = ["adb", "devices", "-l"]
        try:
            result = subprocess.run(  # noqa: S603,S607 - 受控命令
                adb_command,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except FileNotFoundError:
            self.log("⚠️ 未找到 adb 命令，请安装 Android SDK 平台工具并配置到 PATH。")
            return False
        except Exception as exc:  # noqa: BLE001
            self.log(f"⚠️ 执行 adb 命令失败: {exc}")
            return False

        output = (result.stdout or "").strip()
        if result.returncode != 0:
            message = (result.stderr or "").strip() or output or "未知错误"
            self.log(f"⚠️ adb 命令执行失败: {message}")
            return False

        devices = parse_adb_devices(output)
        if not devices:
            self.log("⚠️ adb 未检测到任何设备，请确认设备已连接并授权 USB 调试。")
            return False

        ready_devices: List[str] = []
        ready_records: List[Dict[str, Any]] = []
        for device in devices:
            try:
                label = device.describe()
            except Exception:  # noqa: BLE001
                label = device.serial

            if device.is_ready:
                ready_devices.append(label)
                self.log(f"✅ 检测到设备: {label}")
                ready_records.append(
                    {
                        "label": label,
                        "serial": device.serial,
                        "model": device.properties.get("model"),
                        "device": device.properties.get("device"),
                        "transport_id": device.properties.get("transport_id"),
                        "properties": dict(device.properties),
                        "info": device,
                    }
                )
            else:
                self.log(f"⚠️ 设备状态 {device.status}: {label}")

        self.app_detected_devices = ready_devices
        self.app_detected_device_records = ready_records

        if ready_devices:
            self.log(f"✅ 共检测到 {len(ready_devices)} 台处于可用状态的设备。")
        else:
            self.log("⚠️ 设备已被识别，但尚未进入 device 状态，请确认已授权 USB 调试。")

        return bool(ready_devices)

        
    def _try_auto_login(self):
        """尝试自动登录"""
        if os.path.exists(self.cookie_file):
            self.log("🔍 发现已保存的登录信息，尝试自动登录...")
            threading.Thread(target=self._auto_login_worker, daemon=True).start()
        else:
            self.log("ℹ️ 未发现保存的登录信息，请手动登录")
    
    def _auto_login_worker(self):
        """自动登录工作线程"""
        try:
            # 创建临时driver用于测试登录状态
            options = webdriver.ChromeOptions()
            options.add_experimental_option("excludeSwitches", ['enable-automation'])
            options.add_argument('--disable-blink-features=AutomationControlled')
            
            temp_driver = webdriver.Chrome(options=options)
            self.driver = temp_driver
            
            # 尝试加载cookies
            if self.load_cookies():
                self.root.after(0, lambda: self.update_step(1, "completed"))  # 网页登录完成
                self.root.after(0, lambda: self.log("🎉 自动登录成功！"))
            else:
                temp_driver.quit()
                self.driver = None
                self.root.after(0, lambda: self.log("⚠️ 自动登录失败，请手动登录"))
                
        except Exception as e:
            if 'temp_driver' in locals():
                temp_driver.quit()
            self.driver = None
            self.root.after(0, lambda: self.log(f"❌ 自动登录出错: {e}"))
        
    def web_login(self):
        """网页登录功能"""
        self.update_step(1, "active")  # 网页登录是index=1
        self.log("🔐 启动网页登录...")
        
        url = self.url_entry.get().strip()
        if not url or url == "请输入大麦网演出详情页链接...":
            messagebox.showwarning("警告", "请先输入演出链接")
            return
            
        # 在新线程中执行登录
        threading.Thread(target=self._web_login_worker, args=(url,), daemon=True).start()
        
    def _web_login_worker(self, url):
        """网页登录工作线程"""
        try:
            # 初始化webdriver
            options = webdriver.ChromeOptions()
            options.add_experimental_option("excludeSwitches", ['enable-automation'])
            options.add_argument('--disable-blink-features=AutomationControlled')
            
            self.driver = webdriver.Chrome(options=options)
            self.log("✅ 浏览器启动成功")
            
            # 打开大麦网首页
            self.driver.get("https://www.damai.cn")
            self.log("🌐 已打开大麦网，请在浏览器中完成登录")
            
            # 等待用户登录
            self.root.after(0, self._show_login_instructions)
            
        except Exception as e:
            self.root.after(0, lambda: self.log(f"❌ 网页登录失败: {e}"))
            self.root.after(0, lambda: self.update_step(1, "error"))  # 网页登录是index=1
            
    def _show_login_instructions(self):
        """显示登录说明"""
        login_window = tk.Toplevel(self.root)
        login_window.title("登录说明")
        login_window.geometry("450x350")
        login_window.transient(self.root)
        login_window.grab_set()
        
        ttk.Label(login_window, text="🔐 请在浏览器中完成登录", 
                 font=self.title_font).pack(pady=20)
        
        instructions = [
            "1. 浏览器已自动打开大麦网",
            "2. 请点击页面上的「登录」按钮",
            "3. 使用手机扫码或账号密码登录",
            "4. 登录成功后点击下方「登录完成」按钮",
            "",
            "注意：请保持浏览器窗口打开",
            "登录状态将用于后续的抢票操作"
        ]
        
        for instruction in instructions:
            label = ttk.Label(login_window, text=instruction, font=self.default_font)
            label.pack(pady=2)
        
        button_frame = ttk.Frame(login_window)
        button_frame.pack(pady=20)
        
        ttk.Button(button_frame, text="✅ 登录完成", 
                  command=lambda: self._login_completed(login_window)).pack(side="left", padx=10)
        ttk.Button(button_frame, text="❌ 取消", 
                  command=lambda: self._login_cancelled(login_window)).pack(side="left", padx=10)
                  
    def _login_completed(self, window):
        """登录完成"""
        window.destroy()
        
        # 保存cookies
        if self.save_cookies():
            self.update_step(1, "completed")  # 网页登录是index=1
            self.log("✅ 网页登录完成，登录状态已保存")
            messagebox.showinfo("成功", "登录完成并已保存登录状态！下次启动将自动登录。")
        else:
            self.update_step(1, "completed")  # 网页登录是index=1
            self.log("✅ 网页登录完成")
            messagebox.showinfo("成功", "登录完成！现在可以输入演出链接进行分析。")
        
    def _login_cancelled(self, window):
        """取消登录"""
        window.destroy()
        if self.driver:
            self.driver.quit()
            self.driver = None
        self.update_step(1, "inactive")  # 网页登录是index=1
        self.log("❌ 登录已取消")
        
    def analyze_page(self):
        """分析页面功能"""
        url = self.url_entry.get().strip()
        if not url or url == "请输入大麦网演出详情页链接...":
            messagebox.showwarning("警告", "请输入演出链接")
            return
            
        # 登录变为可选，不强制要求
        if not self.driver:
            self.log("ℹ️ 未检测到浏览器实例，将创建新的浏览器进行分析")
            
        self.update_step(2, "active")  # 页面分析是index=2
        self.log(f"🔍 开始分析页面: {url}")
        
        # 在新线程中执行分析
        threading.Thread(target=self._analyze_page_worker, args=(url,), daemon=True).start()
        
    def _analyze_page_worker(self, url):
        """页面分析工作线程"""
        try:
            # 如果没有driver，创建一个临时的用于分析
            temp_driver = None
            if not self.driver:
                self.root.after(0, lambda: self.log("🚀 创建临时浏览器进行页面分析..."))
                options = webdriver.ChromeOptions()
                options.add_experimental_option("excludeSwitches", ['enable-automation'])
                options.add_argument('--disable-blink-features=AutomationControlled')
                temp_driver = webdriver.Chrome(options=options)
                analysis_driver = temp_driver
            else:
                analysis_driver = self.driver
            
            # 使用专用的页面分析器
            from gui_concert import PageAnalyzer
            
            analyzer = PageAnalyzer(
                driver=analysis_driver,
                log_callback=lambda msg: self.root.after(0, lambda: self.log(msg))
            )
            
            # 分析页面信息
            page_info = analyzer.analyze_show_page(url)
            
            if page_info:
                self.target_url = url
                # 更新UI
                self.root.after(0, lambda: self._update_page_info(page_info))
                self.root.after(0, lambda: self._create_config_interface(page_info))
            else:
                self.root.after(0, lambda: self.update_step(2, "error"))  # 页面分析是index=2
            
            # 如果使用了临时driver，关闭它
            if temp_driver:
                temp_driver.quit()
                self.root.after(0, lambda: self.log("🗑️ 临时浏览器已关闭"))
            
        except Exception as e:
            self.root.after(0, lambda: self.log(f"❌ 页面分析失败: {e}"))
            self.root.after(0, lambda: self.update_step(2, "error"))  # 页面分析是index=2
            
    def _update_page_info(self, info):
        """更新页面信息显示 - 改为在日志中显示关键信息"""
        
        # 在日志中显示页面分析结果
        self.log(f"📊 演出信息分析结果")
        self.log(f"🎭 演出名称: {info['title']}")
        self.log(f"🏟️ 演出场地: {info['venue']}")
        self.log(f"🎫 售票状态: {info['status']}")
        
        if info['cities']:
            self.log(f"🏙️ 可选城市 ({len(info['cities'])}个): {', '.join(info['cities'][:3])}{'...' if len(info['cities']) > 3 else ''}")
        
        if info['dates']:
            self.log(f"📅 可选日期 ({len(info['dates'])}个): {', '.join(info['dates'][:3])}{'...' if len(info['dates']) > 3 else ''}")
        
        if info['prices']:
            self.log(f"💰 价格档位 ({len(info['prices'])}个): {', '.join(info['prices'][:3])}{'...' if len(info['prices']) > 3 else ''}")
        
        self.update_step(2, "completed")  # 页面分析是index=2
        self.log("✅ 页面分析完成")
        
        # 页面分析完成后自动保存cookies
        self.save_cookies()
        
    def _create_config_interface(self, info):
        """创建配置界面"""
        # 清除现有配置界面
        for widget in self.config_label.master.winfo_children():
            if widget != self.config_label:
                widget.destroy()
                
        self.config_label.config(text="")
        config_frame = self.config_label.master
        
        # 城市选择
        if info['cities']:
            ttk.Label(config_frame, text="🏙️ 选择城市:", font=self.default_font).pack(anchor="w", pady=2)
            self.city_var = tk.StringVar(value=info['cities'][0])
            city_combo = ttk.Combobox(config_frame, textvariable=self.city_var, 
                                     values=info['cities'], state="readonly", font=self.default_font)
            city_combo.pack(fill="x", pady=2)
            
        # 日期选择
        if info['dates']:
            ttk.Label(config_frame, text="📅 选择日期:", font=self.default_font).pack(anchor="w", pady=2)
            self.date_var = tk.StringVar(value=info['dates'][0])
            date_combo = ttk.Combobox(config_frame, textvariable=self.date_var, 
                                     values=info['dates'], state="readonly", font=self.default_font)
            date_combo.pack(fill="x", pady=2)
            
        # 价格选择
        if info['prices']:
            ttk.Label(config_frame, text="💰 选择价格:", font=self.default_font).pack(anchor="w", pady=2)
            self.price_var = tk.StringVar(value=info['prices'][0])
            price_combo = ttk.Combobox(config_frame, textvariable=self.price_var, 
                                      values=info['prices'], state="readonly", font=self.default_font)
            price_combo.pack(fill="x", pady=2)
            
        # 固定配置说明
        ttk.Label(config_frame, text="🎫 购买数量: 1张 (固定)", font=self.default_font).pack(anchor="w", pady=2)
        ttk.Label(config_frame, text="👥 观演人: 自动选择全部", font=self.default_font).pack(anchor="w", pady=2)
        
        # 提交订单选项
        self.commit_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(config_frame, text="自动提交订单 (谨慎使用)", 
                       variable=self.commit_var).pack(anchor="w", pady=2)
                       
        # 回流监听选项
        self.listen_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(config_frame, text="启用回流监听 (售罄后继续等待)", 
                       variable=self.listen_var).pack(anchor="w", pady=2)
        
        # 确认配置按钮
        ttk.Button(config_frame, text="✅ 确认配置", 
                  command=self._confirm_config).pack(pady=10)
                  
        self.update_step(3, "active")  # 参数配置是index=3
        
    def _confirm_config(self):
        """确认配置"""
        try:
            # 收集配置信息
            config = {}
            
            if hasattr(self, 'city_var'):
                config["city"] = self.city_var.get()
            if hasattr(self, 'date_var'):
                config["date"] = self.date_var.get()
            if hasattr(self, 'price_var'):
                config["price"] = self.price_var.get()
                
            config["users"] = ["自动选择全部"]
            config["if_commit_order"] = self.commit_var.get()
            config["if_listen"] = self.listen_var.get()  # 添加回流监听配置
            config["target_url"] = self.target_url
            
            self.config = config
            
            summary = f"""
                ✅ 配置完成

                🏙️ 城市: {config.get('city', '未选择')}
                📅 日期: {config.get('date', '未选择')}  
                💰 价格: {config.get('price', '未选择')}
                🎫 数量: 1张 (固定)
                👥 观演人: 自动选择全部
                📋 提交订单: {'是' if config['if_commit_order'] else '否'}
                🔄 回流监听: {'是' if config['if_listen'] else '否'}
                """
            
            self.log(summary)
            self.update_step(3, "completed")  # 参数配置是index=3
            self.update_step(4, "active")     # 开始抢票是index=4
            self.start_btn.config(state="normal")
            
            messagebox.showinfo("配置完成", "抢票参数配置完成！可以开始抢票了。")
            
        except Exception as e:
            self.log(f"❌ 配置确认失败: {e}")
            
    def start_grabbing(self):
        """开始抢票"""
        if self.mode_var.get() == "app":
            self._start_app_grabbing()
        else:
            self._start_web_grabbing()

    def _start_web_grabbing(self) -> None:
        if not self.config:
            messagebox.showwarning("警告", "请先完成页面分析和参数配置")
            return

        if not self.driver:
            result = messagebox.askyesno(
                "登录确认",
                '您还未登录大麦网。\n\n点击"是"开始抢票（抢票过程中会弹出登录窗口）\n点击"否"取消操作',
            )
            if not result:
                return
            self.log("ℹ️ 将在抢票过程中进行登录")

        # 保存 Web 配置到文件
        self._save_web_config()
        
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.is_grabbing = True
        self.log("🎯 开始执行抢票...")

        threading.Thread(target=self._grabbing_worker, daemon=True).start()

    def _start_app_grabbing(self) -> None:
        if not APPIUM_AVAILABLE or DamaiAppTicketRunner is None:
            messagebox.showerror("错误", "当前环境未配置 Appium，无法启动 App 抢票。")
            return

        if not self.app_env_ready:
            messagebox.showwarning("提示", "请先完成环境检测，确保 Appium 服务可用。")
            return

        if not self.app_config_ready:
            messagebox.showwarning("提示", "请先通过左侧表单完善 App 配置。")
            return

        try:
            config = self._collect_app_config_from_form()
        except Exception as exc:  # noqa: BLE001
            if ConfigValidationError is not None and isinstance(exc, ConfigValidationError):
                errors = list(exc.errors)
                self._last_config_errors = errors
                self._show_config_validation_error("配置校验失败", exc.message, errors)
            else:
                self._last_config_errors = [str(exc)]
                messagebox.showerror("错误", f"解析配置失败: {exc}")
                self.log(f"❌ 解析配置失败: {exc}")
            return

        try:
            max_retries = max(1, int(self.app_retries_var.get()))
        except Exception:
            max_retries = 1

        # 运行使用的配置与表单保持一致
        self.app_loaded_config = config
        
        # 保存配置到文件
        self.save_app_config()

        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.is_grabbing = True
        self.app_should_stop = False
        self.last_app_report = None
        self.app_metrics_var.set("App 抢票流程运行中…")
        self.mark_step("4. 开始抢票", "active")
        self.log("🎯 开始执行 App 抢票流程...")

        self.app_runner_thread = threading.Thread(
            target=self._run_app_runner,
            args=(config, max_retries),
            daemon=True,
        )
        self.app_runner_thread.start()
        
    def _grabbing_worker(self):
        """抢票工作线程"""
        try:
            # 如果没有driver，创建一个并提示用户登录
            if not self.driver:
                self.root.after(0, lambda: self.log("🚀 启动浏览器..."))
                options = webdriver.ChromeOptions()
                options.add_experimental_option("excludeSwitches", ['enable-automation'])
                options.add_argument('--disable-blink-features=AutomationControlled')
                self.driver = webdriver.Chrome(options=options)
                
                # 打开大麦网让用户登录
                self.driver.get("https://www.damai.cn")
                self.root.after(0, lambda: self.log("🌐 已打开大麦网，请在浏览器中完成登录"))
                
                # 弹出登录提示窗口
                self.root.after(0, self._show_login_for_grabbing)
                return  # 等待用户确认登录后再继续
            
            # 使用GUI专用的抢票模块
            from gui_concert import GUIConcert
            
            # 创建抢票实例
            concert = GUIConcert(
                driver=self.driver,
                config=self.config,
                log_callback=lambda msg: self.root.after(0, lambda: self.log(msg)),
                cookie_callback=lambda: self.root.after(0, self.auto_save_cookies_if_needed),
                stop_check=lambda: not self.is_grabbing  # 停止检查回调
            )
            
            self.root.after(0, lambda: self.log("🎫 开始执行抢票流程..."))
            
            # 执行抢票
            concert.choose_ticket()
            
            # 抢票完成后自动保存cookies
            self.root.after(0, lambda: self.save_cookies())
            
            self.root.after(0, lambda: self.log("✅ 抢票流程执行完成"))
            self.root.after(0, lambda: self.update_step(4, "completed"))  # 开始抢票是index=4
            
        except Exception as e:
            self.root.after(0, lambda: self.log(f"❌ 抢票执行失败: {e}"))
            self.root.after(0, lambda: self.update_step(4, "error"))      # 开始抢票是index=4
        finally:
            self.is_grabbing = False  # 重置抢票状态
            self.root.after(0, lambda: self._reset_buttons())

    def _run_app_runner(self, config, max_retries: int) -> None:
        """App 模式抢票线程"""

        def stop_signal() -> bool:
            return self.app_should_stop

        if DamaiAppTicketRunner is None:
            self.root.after(0, lambda: self.log("❌ 当前环境未启用 Appium 运行器"))
            return

        runner = None
        try:
            runner = DamaiAppTicketRunner(
                config=config,
                logger=self._app_runner_logger,
                stop_signal=stop_signal,
            )
            success = runner.run(max_retries=max_retries)
            report = runner.get_last_report()
            stopped = self.app_should_stop
            self.root.after(
                0,
                lambda s=success, st=stopped, r=report: self._handle_app_run_result(s, st, r),
            )
        except Exception as exc:  # noqa: BLE001
            report = runner.get_last_report() if runner is not None else None
            self.root.after(
                0,
                lambda e=exc, r=report: self._handle_app_run_exception(e, r),
            )
        finally:
            self.is_grabbing = False
            self.app_runner_thread = None
            self.app_should_stop = False
            self.root.after(0, lambda: self._reset_buttons())

    def _run_preheated_app_runner(self, max_retries: int) -> None:
        """使用预热好的App模式抢票线程"""

        if not hasattr(self, 'app_runner') or self.app_runner is None:
            self.root.after(0, lambda: self.log("❌ 没有可用的预热运行器"))
            return

        try:
            # 使用预热好的runner直接运行抢票流程
            success = self.app_runner.run(max_retries=max_retries)
            report = self.app_runner.get_last_report()
            stopped = self.app_should_stop
            self.root.after(
                0,
                lambda s=success, st=stopped, r=report: self._handle_app_run_result(s, st, r),
            )
        except Exception as exc:  # noqa: BLE001
            report = self.app_runner.get_last_report() if self.app_runner is not None else None
            self.root.after(
                0,
                lambda e=exc, r=report: self._handle_app_run_exception(e, r),
            )
        finally:
            # 清理预热的runner
            self.app_runner = None
            self.is_grabbing = False
            self.app_runner_thread = None
            self.app_should_stop = False
            self.root.after(0, lambda: self._reset_buttons())

    def _handle_app_run_result(self, success: bool, stopped: bool, report: Optional[Any]) -> None:
        self.last_app_report = report
        self._update_app_metrics_display(report)

        metrics = getattr(report, "metrics", None)
        if metrics is not None:
            duration = max(metrics.end_time - metrics.start_time, 0.0)
            attempts = getattr(metrics, "attempts", 0)
            summary = f"尝试 {attempts} 次，耗时 {duration:.2f} 秒"
        else:
            summary = ""

        if success:
            if summary:
                self.log(f"📊 App 流程完成：{summary}")
            else:
                self.log("📊 App 流程完成")
            self.mark_step("4. 开始抢票", "completed")
            self.mark_step("5. 查看结果", "completed")
            return

        if stopped:
            self.log("⏹️ App 抢票流程已停止")
            self.mark_step("4. 开始抢票", "error")
            return

        reason = self._format_failure_for_display(report)
        self.log(f"⚠️ 未能成功抢票：{reason}")
        messagebox.showwarning("抢票未成功", reason)
        self.mark_step("4. 开始抢票", "error")
        self.mark_step("5. 查看结果", "error")

    def _handle_app_run_exception(self, exc: Exception, report: Optional[Any]) -> None:
        self.last_app_report = report
        self._update_app_metrics_display(report)
        self.log(f"❌ App 抢票异常: {exc}")
        messagebox.showerror("App 抢票异常", str(exc))
        self.mark_step("4. 开始抢票", "error")
        self.mark_step("5. 查看结果", "error")

    def _app_runner_logger(self, level: str, message: str, context=None) -> None:
        """适配 App 运行器日志到 GUI"""

        prefix = {
            "step": "🧭",
            "info": "ℹ️",
            "success": "✅",
            "warning": "⚠️",
            "error": "❌",
        }.get(level, "📄")

        extra = ""
        if context:
            try:
                extras = [f"{key}={value}" for key, value in context.items()]
                if extras:
                    extra = " (" + ", ".join(extras) + ")"
            except Exception:
                extra = ""

        text = f"{prefix} {message}{extra}"
        self.root.after(0, lambda: self.log(text))
            
    def _show_login_for_grabbing(self):
        """显示抢票时的登录说明"""
        login_window = tk.Toplevel(self.root)
        login_window.title("抢票登录")
        login_window.geometry("450x300")
        login_window.transient(self.root)
        login_window.grab_set()
        
        ttk.Label(login_window, text="🔐 请在浏览器中完成登录", 
                 font=self.title_font).pack(pady=20)
        
        instructions = [
            "抢票前需要登录大麦网：",
            "",
            "1. 浏览器已自动打开大麦网",
            "2. 请点击页面上的「登录」按钮",
            "3. 使用手机扫码或账号密码登录",
            "4. 登录成功后点击下方「开始抢票」按钮"
        ]
        
        for instruction in instructions:
            label = ttk.Label(login_window, text=instruction, font=self.default_font)
            label.pack(pady=2)
        
        button_frame = ttk.Frame(login_window)
        button_frame.pack(pady=20)
        
        ttk.Button(button_frame, text="🎯 开始抢票", 
                  command=lambda: self._start_grabbing_after_login(login_window)).pack(side="left", padx=10)
        ttk.Button(button_frame, text="❌ 取消", 
                  command=lambda: self._cancel_grabbing_login(login_window)).pack(side="left", padx=10)
    
    def _start_grabbing_after_login(self, window):
        """登录后开始抢票"""
        window.destroy()
        
        # 保存cookies
        self.save_cookies()
        
        self.log("✅ 开始抢票流程...")
        # 重新启动抢票worker
        threading.Thread(target=self._grabbing_worker, daemon=True).start()
    
    def _cancel_grabbing_login(self, window):
        """取消抢票登录"""
        window.destroy()
        self.log("❌ 抢票已取消")
        self._reset_buttons()
            
    def _reset_buttons(self):
        """重置按钮状态"""
        if self.mode_var.get() == "app":
            start_state = "normal" if (self.app_env_ready and self.app_config_ready) else "disabled"
        else:
            start_state = "normal"
        self.start_btn.config(state=start_state)
        self.stop_btn.config(state="disabled")
        
    def clear_login_status(self):
        """清除登录状态"""
        result = messagebox.askyesno(
            "确认清除", 
            "确定要清除保存的登录状态吗？\n下次启动时需要重新登录。"
        )
        if result:
            self.clear_cookies()
            if self.driver:
                self.driver.quit()
                self.driver = None
            self.update_step(1, "inactive")  # 重置登录状态
            messagebox.showinfo("完成", "登录状态已清除")
            
    def stop_grabbing(self):
        """停止抢票"""
        self.is_grabbing = False  # 设置停止标志
        if self.mode_var.get() == "app":
            self.app_should_stop = True
            self.log("⏹️ 正在请求停止 App 抢票...")
        else:
            self.log("⏹ 正在停止抢票...")
        self._reset_buttons()
        
    def return_to_main(self):
        """回到主UI界面，保留用户配置"""
        self.is_grabbing = False
        if self.mode_var.get() == "app":
            self.app_should_stop = True
        
        # 重置运行统计
        self.app_metrics_var.set("尚未运行 App 抢票流程")
        
        # 重置按钮状态
        self._reset_buttons()
        
        # 只重置当前运行中的步骤状态，保留已完成的配置
        if self.mode_var.get() == "app":
            # 保留已完成的环境检测和参数配置
            # 只重置抢票相关的步骤
            self.mark_step("4. 开始抢票", "inactive")
            self.mark_step("5. 查看结果", "inactive")
        else:
            # 保留已完成的登录、页面分析和参数配置
            self.mark_step("5. 开始抢票", "inactive")
        
        self.log("🏠 已回到主界面，可以重新开始抢票")
        
    def show_help(self):
        """显示帮助信息"""
        help_window = tk.Toplevel(self.root)
        help_window.title("使用帮助")
        help_window.geometry("600x500")
        help_window.transient(self.root)

        help_text = scrolledtext.ScrolledText(help_window, wrap=tk.WORD, font=self.default_font)
        help_text.pack(fill="both", expand=True, padx=10, pady=10)

        help_content = """
🎫 大麦抢票工具使用说明

🧭 模式概览：
• 网页模式 (Web)：使用 Chrome + Selenium 自动化网页端购票流程
• App 模式 (App)：通过 Appium 控制大麦 App，适合移动端极速抢票

📋 网页模式流程：
1. 环境检测 —— 检查 Python、Selenium 与 ChromeDriver 是否可用
2. 网页登录 —— 可选，可提前登录或在抢票时登录，状态会自动保存
3. 页面分析 —— 输入演出链接，自动解析城市、日期、价格等选项
4. 参数配置 —— 在界面中选择目标条件并确认
5. 开始抢票 —— 启动自动化流程，实时输出执行日志

📱 App 模式流程：
1. 环境检测 —— 校验 Python 环境与 Appium 客户端依赖
2. 设备检查 —— 请求 Appium Server /status，确认服务与设备在线
3. 参数配置 —— 选择或加载 config.jsonc/JSON，配置城市、价格、观演人
4. 开始抢票 —— 运行移动端抢票流程，可设置重试次数
5. 查看结果 —— 日志中查看 Appium 执行步骤与最终状态

🔧 关键说明：

网页模式：
• 支持自动保存/加载登录 Cookie，减少重复登录
• 页面分析无需登录即可完成，可先确认票务信息
• 观演人自动全选，支持可选的自动提交订单

App 模式前置条件：
• 已安装 Appium Server 并保持运行 (默认 http://127.0.0.1:4723)
• Android 设备已开启开发者模式并与电脑连接
• damai_appium/config.jsonc 配置正确，包含 server_url、device_caps 等
• 若设备未自动识别，请在配置中补充 deviceName、udid 等字段

App 模式小贴士：
• 先点击“重新加载”确认配置无误，再执行环境检测
• 环境检测通过后按钮会自动解锁，可随时停止流程
• 日志前缀：🧭步骤、ℹ️信息、✅成功、⚠️警告、❌异常，便于快速定位

⚠️ 通用注意事项：
• 确保网络与设备连接稳定
• 抢票前检查实名信息、观演人等是否完善
• 谨慎使用自动提交，建议保留人工确认
• 遵守大麦网条款，合理合法地使用工具

💡 使用技巧：
• 新用户推荐通过“环境检测”了解依赖情况
• 自动登录失败时，可清除登录状态后重新登录
• 多场演出可分别分析并保存日志作为参考
• 建议在开票前完成一次全流程演练
"""

        help_text.insert("1.0", help_content)
        help_text.config(state="disabled")


    def _start_authz_watchdog(self) -> None:
        """后台授权复检：已取消授权校验"""
        self.log("ℹ️ 授权监控已取消")
def main():
    """主函数"""
    # 已取消授权校验
    app = DamaiGUI()
    app.run()


if __name__ == "__main__":
    main()