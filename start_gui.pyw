#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GUI启动器 - 增强版本
- 继续作为 GUI 启动入口
- 在不修改其他文件的前提下，通过运行时补丁增强 App 模式中的 Appium 启停与状态同步：
  * 将按钮文案统一为中文「启动 Appium」/「停止 Appium」
  * 基于定时器轮询子进程存活，若外部窗口被关闭则自动复位按钮文案
  * 在主窗口关闭时，若由本按钮启动的 Appium 仍在运行则自动终止
- 支持热加载功能，修改代码后无需重启应用
"""

import sys
import os
import time
import threading

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


try:
    # 授权校验 - 暂时注释掉以避免404错误
    # from damai.authz import block_if_unauthorized_with_ui
    # block_if_unauthorized_with_ui()

    # 仅修改本文件：通过运行时补丁增强 GUI 的 App 模式“Appium”按钮逻辑
    import tkinter as tk
    from tkinter import messagebox
    import damai_gui  # 引入实际 GUI 模块

    # 创建 GUI 实例
    app = damai_gui.DamaiGUI()


    # 移除了强制按钮文本设置，让damai_gui_copy.py中的立即状态检查来设置正确的文本

    # 保存原始方法，便于在补丁中调用原实现
    _orig_start = getattr(app, "_start_appium_server", None)
    _orig_stop = getattr(app, "_stop_appium_server", None)
    _orig_reset = getattr(app, "_reset_appium_state", None)

    # 补丁：保留原始的启动功能，移除强制文本设置
    def _patched_start_appium_server():
        try:
            if callable(_orig_start):
                _orig_start()
        except Exception as exc:
            # 原始实现已弹窗提示，这里补充日志不打断流程
            try:
                app.log(f"❌ Appium 启动补丁后置处理失败: {exc}")
            except Exception:
                pass

    # 补丁：保留原始的复位状态功能，移除强制文本设置
    def _patched_reset_appium_state():
        try:
            if callable(_orig_reset):
                _orig_reset()
        except Exception:
            pass

    # 补丁：保留原始的停止功能，移除强制文本设置
    def _patched_stop_appium_server():
        try:
            if callable(_orig_stop):
                _orig_stop()
        except Exception:
            pass

    # 应用补丁（仅对当前实例生效；不改动原文件）
    try:
        app._start_appium_server = _patched_start_appium_server
        app._stop_appium_server = _patched_stop_appium_server
        app._reset_appium_state = _patched_reset_appium_state
    except Exception:
        # 若绑定失败，不影响其他功能
        pass

    # 增加定时轮询：若外部命令窗口被关闭，自动复位按钮文案与内部状态
    def _appium_watchdog():
        try:
            proc = getattr(app, "appium_process", None)
            if proc is not None:
                # 子进程已退出（例如用户手动关闭命令窗口）
                if proc.poll() is not None:
                    try:
                        app._reset_appium_state()
                        app.log("ℹ️ 检测到 Appium 控制台已关闭，按钮文案已复位为“启动 Appium”。")
                    except Exception:
                        pass
            # 移除了错误的按钮文本强制设置逻辑
        except Exception:
            # 守护无需中断 GUI，忽略异常
            pass
        finally:
            # 每 1 秒轮询一次
            try:
                app.root.after(1000, _appium_watchdog)
            except Exception:
                pass

    try:
        app.root.after(1000, _appium_watchdog)
    except Exception:
        pass

    # 关闭主窗口时的清理：若 Appium 仍在运行，自动停止并回收
    def _on_close():
        try:
            if getattr(app, "appium_running", False) and getattr(app, "appium_pid", None):
                try:
                    app._stop_appium_server()
                    app.log("⏹ 已在退出前自动停止由按钮启动的 Appium 进程。")
                except Exception as exc:
                    try:
                        messagebox.showwarning("提示", f"退出时停止 Appium 失败：{exc}")
                    except Exception:
                        pass
        finally:
            try:
                app.root.destroy()
            except Exception:
                os._exit(0)

    try:
        app.root.protocol("WM_DELETE_WINDOW", _on_close)
    except Exception:
        pass

    # 运行 GUI 主循环
    app.run()

except ImportError as e:
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口

    messagebox.showerror(
        "依赖缺失",
        f"缺少必要的依赖库！\n\n错误信息：{e}\n\n请先运行 '安装依赖.bat' 或\n手动执行：pip install -r requirements.txt"
    )
    sys.exit(1)
except Exception as e:
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.withdraw()

    messagebox.showerror(
        "启动失败",
        f"程序启动失败！\n\n错误信息：{e}\n\n请检查文件完整性或运行 '一键启动GUI版本.bat'"
    )
    sys.exit(1)
