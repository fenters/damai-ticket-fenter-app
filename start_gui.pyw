#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import subprocess


def _ensure_venv() -> None:
    """Re-launch using venv Python if not already running in it."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    venv_python = os.path.join(script_dir, "venv", "Scripts", "python.exe")

    if not os.path.isfile(venv_python):
        return  # no venv found, proceed with current python

    current = os.path.abspath(sys.executable)
    if os.path.abspath(venv_python).lower() == current.lower():
        return  # already running in venv

    # re-launch with venv python
    try:
        subprocess.run(
            [venv_python, os.path.abspath(__file__)] + sys.argv[1:],
            cwd=script_dir,
        )
    except Exception:
        pass
    sys.exit(0)


_ensure_venv()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from damai_gui import main
    main()
except ImportError as e:
    import tkinter as tk
    from tkinter import messagebox
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(
        "依赖缺失",
        f"缺少必要的依赖库！\n\n错误信息：{e}\n\n请确保 venv 已激活并安装了 customtkinter。"
    )
    sys.exit(1)
except Exception as e:
    import tkinter as tk
    from tkinter import messagebox
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(
        "启动失败",
        f"程序启动失败！\n\n错误信息：{e}"
    )
    sys.exit(1)
