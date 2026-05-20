from __future__ import annotations

import calendar
from datetime import datetime
from typing import Callable, Optional

import customtkinter as ctk


class DatePickerCtk(ctk.CTkFrame):
    """Ant Design-style date/time picker for CustomTkinter.

    Shows a clickable entry + calendar button. Click opens a dropdown-style
    panel below the widget with a calendar grid, time selector (H:M:S),
    and confirm / now buttons.
    """

    _PICKER_WIDTH = 310
    _PICKER_HEIGHT = 380

    def __init__(
        self,
        master,
        width: int = 200,
        height: int = 32,
        on_select: Optional[Callable[[datetime], None]] = None,
        **kwargs,
    ):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._datetime: Optional[datetime] = None
        self._on_select = on_select
        self._dialog: Optional[ctk.CTkToplevel] = None

        self.grid_columnconfigure(0, weight=1)

        self._entry = ctk.CTkEntry(self, height=height, placeholder_text="YYYY-MM-DD HH:MM:SS")
        self._entry.grid(row=0, column=0, sticky="ew")

        self._btn = ctk.CTkButton(
            self, text="\U0001F4C5", width=36, height=height,
            fg_color="#0EA5E9", hover_color="#0284C7",
            command=self._open_picker,
        )
        self._btn.grid(row=0, column=1, padx=(4, 0))

    # ---- public API ----

    def get(self) -> str:
        return self._entry.get().strip()

    def set(self, text: str) -> None:
        self._entry.delete(0, "end")
        self._entry.insert(0, text)
        self._parse(text)

    def get_datetime(self) -> Optional[datetime]:
        return self._datetime

    # ---- internals ----

    def _parse(self, text: str) -> None:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                self._datetime = datetime.strptime(text, fmt)
                return
            except ValueError:
                continue
        self._datetime = None

    def _open_picker(self) -> None:
        if self._dialog is not None:
            try:
                self._dialog.destroy()
            except Exception:
                pass

        w, h = self._PICKER_WIDTH, self._PICKER_HEIGHT
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()

        bx = self.winfo_rootx()
        by = self.winfo_rooty()
        bw = self.winfo_width()

        # default: below button
        x = bx
        y = by + self.winfo_height() + 2

        # if off bottom → open above
        if y + h > sh:
            y = by - h - 2
        # if still off bottom or above top → clamp
        if y < 0:
            y = max(0, by - h - 2) if by > h else 4
        if y + h > sh:
            y = sh - h - 4
        # if off right → align right edge
        if x + w > sw:
            x = max(0, bx + bw - w)
        # if off left → clamp
        if x < 0:
            x = 4
        if x + w > sw:
            x = sw - w - 4

        self._dialog = ctk.CTkToplevel(self)
        self._dialog.title("")
        self._dialog.geometry(f"{w}x{h}+{x}+{y}")
        self._dialog.resizable(False, False)
        self._dialog.transient(self.winfo_toplevel())
        self._dialog.grab_set()
        self._dialog.focus_set()
        self._dialog.bind("<Escape>", lambda e: self._close())

        now = self._datetime or datetime.now()

        # state
        sel_year = now.year
        sel_month = now.month
        sel_day = now.day
        sel_hour = now.hour
        sel_minute = now.minute
        sel_second = now.second
        view_year = now.year
        view_month = now.month

        # ── header ──
        header = ctk.CTkFrame(self._dialog, fg_color="transparent", height=40)
        header.pack(fill="x", padx=8, pady=(8, 0))
        header.grid_columnconfigure(1, weight=1)

        prev_btn = ctk.CTkButton(
            header, text="\u25C0", width=32, height=28,
            fg_color="transparent", text_color=("#1E293B", "#F1F5F9"),
            hover_color="#E2E8F0", corner_radius=6,
        )
        prev_btn.grid(row=0, column=0)

        title_lbl = ctk.CTkLabel(
            header, text="", font=("Microsoft YaHei", 13, "bold"),
            anchor="center",
        )
        title_lbl.grid(row=0, column=1, sticky="ew")

        next_btn = ctk.CTkButton(
            header, text="\u25B6", width=32, height=28,
            fg_color="transparent", text_color=("#1E293B", "#F1F5F9"),
            hover_color="#E2E8F0", corner_radius=6,
        )
        next_btn.grid(row=0, column=2)

        def _update_title():
            title_lbl.configure(text=f"{view_year} 年 {view_month:02d} 月")

        def _prev():
            nonlocal view_year, view_month
            view_month -= 1
            if view_month < 1:
                view_month = 12
                view_year -= 1
            _rebuild_days()
            _update_title()

        def _next():
            nonlocal view_year, view_month
            view_month += 1
            if view_month > 12:
                view_month = 1
                view_year += 1
            _rebuild_days()
            _update_title()

        prev_btn.configure(command=_prev)
        next_btn.configure(command=_next)

        # ── weekday labels ──
        week_header = ctk.CTkFrame(self._dialog, fg_color="transparent", height=24)
        week_header.pack(fill="x", padx=8, pady=(4, 0))
        weekdays = ["一", "二", "三", "四", "五", "六", "日"]
        for i, name in enumerate(weekdays):
            ctk.CTkLabel(
                week_header, text=name, width=36, anchor="center",
                font=("Microsoft YaHei", 11), text_color="#94A3B8",
            ).grid(row=0, column=i, padx=1)

        # ── day grid ──
        days_container = ctk.CTkFrame(self._dialog, fg_color="transparent", height=200)
        days_container.pack(fill="x", padx=8)
        days_container.grid_propagate(False)

        day_buttons: list[ctk.CTkButton] = []

        def _rebuild_days():
            for btn in day_buttons:
                btn.destroy()
            day_buttons.clear()

            _, last_day = calendar.monthrange(view_year, view_month)
            first_weekday = calendar.monthrange(view_year, view_month)[0]
            first_weekday = (first_weekday - 1) % 7  # Mon=0

            for r in range(6):
                for c in range(7):
                    day_num = r * 7 + c - first_weekday + 1
                    if day_num < 1 or day_num > last_day:
                        btn = ctk.CTkButton(
                            days_container, text="", width=36, height=30,
                            fg_color="transparent", hover_color="#E2E8F0",
                            corner_radius=6, state="disabled",
                        )
                    else:
                        is_today = (
                            day_num == datetime.now().day
                            and view_year == datetime.now().year
                            and view_month == datetime.now().month
                        )
                        is_selected = (
                            day_num == sel_day
                            and view_year == sel_year
                            and view_month == sel_month
                        )
                        if is_selected:
                            bg = "#3B82F6"
                            fg = "#FFFFFF"
                            hv = "#2563EB"
                        elif is_today:
                            bg = "#EFF6FF"
                            fg = "#3B82F6"
                            hv = "#DBEAFE"
                        else:
                            bg = "transparent"
                            fg = ("#1E293B", "#F1F5F9")
                            hv = "#E2E8F0"

                        btn = ctk.CTkButton(
                            days_container, text=str(day_num), width=36, height=30,
                            fg_color=bg, text_color=fg,
                            hover_color=hv, corner_radius=6,
                            command=lambda d=day_num: _pick_day(d),
                        )
                    btn.grid(row=r, column=c, padx=1, pady=1)
                    day_buttons.append(btn)

        def _pick_day(day: int):
            nonlocal sel_day
            sel_day = day
            _rebuild_days()

        _rebuild_days()
        _update_title()

        # ── time selector ──
        time_frame = ctk.CTkFrame(self._dialog, fg_color="transparent", height=36)
        time_frame.pack(fill="x", padx=12, pady=(8, 0))

        def _make_spinner(container, label_text: str, initial: int, max_val: int):
            sub = ctk.CTkFrame(container, fg_color="transparent")
            sub.pack(side="left", padx=6)
            ctk.CTkLabel(sub, text=label_text, font=("Microsoft YaHei", 11), text_color="#94A3B8").pack(side="left", padx=(0, 2))

            val = ctk.StringVar(value=f"{initial:02d}")
            e = ctk.CTkEntry(sub, textvariable=val, width=40, height=28, justify="center")
            e.pack(side="left")

            def _up():
                v = (int(val.get() or 0) + 1) % (max_val + 1)
                val.set(f"{v:02d}")

            def _down():
                v = (int(val.get() or 0) - 1) % (max_val + 1)
                val.set(f"{v:02d}")

            btn_frame = ctk.CTkFrame(sub, fg_color="transparent")
            btn_frame.pack(side="left", padx=(1, 0))
            ctk.CTkButton(
                btn_frame, text="\u25B2", width=18, height=12,
                fg_color="transparent", text_color=("#64748B", "#94A3B8"),
                hover_color="#E2E8F0", corner_radius=2, command=_up,
            ).pack()
            ctk.CTkButton(
                btn_frame, text="\u25BC", width=18, height=12,
                fg_color="transparent", text_color=("#64748B", "#94A3B8"),
                hover_color="#E2E8F0", corner_radius=2, command=_down,
            ).pack()
            return val

        h_var = _make_spinner(time_frame, "时", sel_hour, 23)
        m_var = _make_spinner(time_frame, "分", sel_minute, 59)
        s_var = _make_spinner(time_frame, "秒", sel_second, 59)

        # ── buttons ──
        btn_row = ctk.CTkFrame(self._dialog, fg_color="transparent", height=40)
        btn_row.pack(fill="x", padx=12, pady=(10, 8))

        def _now():
            n = datetime.now()
            h_var.set(f"{n.hour:02d}")
            m_var.set(f"{n.minute:02d}")
            s_var.set(f"{n.second:02d}")
            nonlocal sel_year, sel_month, sel_day, view_year, view_month
            sel_year = n.year
            sel_month = n.month
            sel_day = n.day
            view_year = n.year
            view_month = n.month
            _rebuild_days()
            _update_title()

        def _confirm():
            try:
                dt = datetime(
                    sel_year, sel_month, sel_day,
                    int(h_var.get()), int(m_var.get()), int(s_var.get()),
                )
                self._datetime = dt
                self._entry.delete(0, "end")
                self._entry.insert(0, dt.strftime("%Y-%m-%d %H:%M:%S"))
                if self._on_select:
                    self._on_select(dt)
            except ValueError:
                pass
            self._close()

        ctk.CTkButton(
            btn_row, text="\u23F1 现在", width=80, height=32,
            fg_color="#64748B", hover_color="#475569", command=_now,
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            btn_row, text="\u2714 确定", width=80, height=32,
            fg_color="#3B82F6", hover_color="#2563EB", command=_confirm,
        ).pack(side="right", padx=4)

    def _close(self) -> None:
        if self._dialog:
            try:
                self._dialog.destroy()
            except Exception:
                pass
            self._dialog = None
