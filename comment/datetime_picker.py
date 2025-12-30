"""
按照antd 的 日期时间选择器写一个一样的日期时间选择器
"""

import datetime
import tkinter as tk
from tkinter import ttk
from tkcalendar import Calendar

class DateTimePicker:
    def __init__(self, parent, on_select=None, gui=None):
        self.parent = parent
        self.on_select = on_select
        self.gui = gui  # 接收主GUI实例，以便使用其样式
        self.selected_datetime = None
        
        # 防抖相关变量
        self._debounce_timer = None
        self._debounce_delay = 500  # 防抖延迟时间，单位毫秒
        
        # 使用主GUI的样式或默认样式
        if gui and hasattr(gui, 'default_font'):
            self.default_font = gui.default_font
            self.button_font = gui.button_font
        else:
            self.default_font = ("微软雅黑", 12)
            self.button_font = ("微软雅黑", 11)
        
        # 使用主GUI的颜色或默认颜色
        if gui and hasattr(gui, 'colors'):
            self.colors = gui.colors
        else:
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
                "background": "#f0f2f5",
                "card_bg": "#ffffff",
                "text_primary": "#262626",
                "text_secondary": "#666666",
                "border": "#e8e8e8",
                "border_light": "#f0f0f0",
                "shadow": "#00000014",
            }
        
        # 创建主容器
        self.main_frame = ttk.Frame(parent)
        self.main_frame.pack(fill=tk.X, padx=2, pady=2)
        
        # 创建输入框和日历按钮
        self.input_frame = ttk.Frame(self.main_frame)
        self.input_frame.pack(fill=tk.X, pady=(0, 5))
        
        self.datetime_var = tk.StringVar()
        self.datetime_entry = ttk.Entry(self.input_frame, textvariable=self.datetime_var, font=self.default_font)
        self.datetime_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        # 监听输入框变化事件
        self.datetime_var.trace_add("write", self._on_input_change)
        
        self.calendar_btn = ttk.Button(self.input_frame, text="📅", command=self.show_picker_dialog, 
                                      style="Primary.TButton" if hasattr(gui, '_init_styles') else "")
        self.calendar_btn.pack(side=tk.RIGHT)
        
        # 初始化显示
        self.update_display()
    
    def show_picker_dialog(self):
        """显示日期时间选择弹窗"""
        # 创建弹窗
        self.picker_window = tk.Toplevel(self.parent)
        self.picker_window.title("选择日期时间")
        self.picker_window.geometry("500x350")
        self.picker_window.resizable(False, False)
        
        # 设置弹窗居中
        self.picker_window.transient(self.parent)
        self.picker_window.grab_set()
        
        # 确保弹窗获得焦点，防止滚动事件传递给主窗口
        self.picker_window.focus_set()
        
        # 绑定鼠标滚轮事件，防止事件冒泡到主窗口
        self.picker_window.bind("<MouseWheel>", lambda e: "break")
        self.picker_window.bind("<Button-4>", lambda e: "break")  # Linux 滚轮上
        self.picker_window.bind("<Button-5>", lambda e: "break")  # Linux 滚轮下
        
        # 创建日历和时间选择面板
        self.picker_frame = ttk.Frame(self.picker_window, style="Card.TFrame" if hasattr(self.gui, '_init_styles') else "")
        self.picker_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 日历部分
        self.calendar_frame = ttk.Frame(self.picker_frame)
        self.calendar_frame.pack(side=tk.LEFT, padx=5)
        
        # 获取当前日期，如果已有选择则使用选择的日期
        current_date = datetime.datetime.now()
        if self.selected_datetime:
            current_date = self.selected_datetime
        
        self.cal = Calendar(self.calendar_frame, selectmode='day', year=current_date.year, 
                           month=current_date.month, day=current_date.day,
                           font=self.default_font, locale='zh_CN', showweeknumbers=False)
        self.cal.pack(pady=5)
        
        # 为日历控件绑定鼠标滚轮事件，防止事件冒泡
        self.cal.bind("<MouseWheel>", lambda e: "break")
        self.cal.bind("<Button-4>", lambda e: "break")
        self.cal.bind("<Button-5>", lambda e: "break")
        
        # 时间选择部分
        self.time_frame = ttk.Frame(self.picker_frame)
        self.time_frame.pack(side=tk.LEFT, padx=5)
        
        # 为时间选择框架绑定鼠标滚轮事件
        self.time_frame.bind("<MouseWheel>", lambda e: "break")
        self.time_frame.bind("<Button-4>", lambda e: "break")
        self.time_frame.bind("<Button-5>", lambda e: "break")
        
        # 小时选择
        self.hour_label = ttk.Label(self.time_frame, text="时", font=self.default_font)
        self.hour_label.pack()
        self.hour_combobox = ttk.Combobox(self.time_frame, values=[f"{i:02d}" for i in range(24)], width=5, 
                                         font=self.default_font)
        self.hour_combobox.set(f"{current_date.hour:02d}")
        self.hour_combobox.pack(pady=2)
        
        # 分钟选择
        self.minute_label = ttk.Label(self.time_frame, text="分", font=self.default_font)
        self.minute_label.pack()
        self.minute_combobox = ttk.Combobox(self.time_frame, values=[f"{i:02d}" for i in range(60)], width=5, 
                                           font=self.default_font)
        self.minute_combobox.set(f"{current_date.minute:02d}")
        self.minute_combobox.pack(pady=2)
        
        # 秒选择
        self.second_label = ttk.Label(self.time_frame, text="秒", font=self.default_font)
        self.second_label.pack()
        self.second_combobox = ttk.Combobox(self.time_frame, values=[f"{i:02d}" for i in range(60)], width=5, 
                                           font=self.default_font)
        self.second_combobox.set(f"{current_date.second:02d}")
        self.second_combobox.pack(pady=2)
        
        # 为所有下拉框绑定鼠标滚轮事件
        for combobox in [self.hour_combobox, self.minute_combobox, self.second_combobox]:
            combobox.bind("<MouseWheel>", lambda e: "break")
            combobox.bind("<Button-4>", lambda e: "break")
            combobox.bind("<Button-5>", lambda e: "break")
        
        # 操作按钮
        self.button_frame = ttk.Frame(self.picker_window)
        self.button_frame.pack(fill=tk.X, pady=(0, 10), padx=10)
        
        # 为按钮框架绑定鼠标滚轮事件
        self.button_frame.bind("<MouseWheel>", lambda e: "break")
        self.button_frame.bind("<Button-4>", lambda e: "break")
        self.button_frame.bind("<Button-5>", lambda e: "break")
        
        self.now_btn = ttk.Button(self.button_frame, text="此刻", command=self.select_now_in_dialog, 
                                 style="Secondary.TButton" if hasattr(self.gui, '_init_styles') else "")
        self.now_btn.pack(side=tk.LEFT, padx=5)
        
        self.ok_btn = ttk.Button(self.button_frame, text="确定", command=self.confirm_selection_in_dialog, 
                                style="Primary.TButton" if hasattr(self.gui, '_init_styles') else "")
        self.ok_btn.pack(side=tk.RIGHT, padx=5)
    
    def select_now_in_dialog(self):
        """在弹窗中选择当前时间"""
        now = datetime.datetime.now()
        self.cal.selection_set(now)
        self.hour_combobox.set(f"{now.hour:02d}")
        self.minute_combobox.set(f"{now.minute:02d}")
        self.second_combobox.set(f"{now.second:02d}")
    
    def confirm_selection_in_dialog(self):
        """在弹窗中确认选择"""
        # 获取选择的日期
        selected_date = self.cal.selection_get()
        
        # 获取选择的时间
        hour = int(self.hour_combobox.get())
        minute = int(self.minute_combobox.get())
        second = int(self.second_combobox.get())
        
        # 组合成完整的datetime
        self.selected_datetime = datetime.datetime(selected_date.year, selected_date.month, selected_date.day, 
                                                 hour, minute, second)
        
        # 更新显示
        self.update_display(self.selected_datetime)
        
        # 触发回调函数
        if self.on_select:
            self.on_select(self.selected_datetime)
        
        # 关闭弹窗
        self.picker_window.destroy()
    
    def update_display(self, dt=None):
        if dt:
            self.selected_datetime = dt
            self.datetime_var.set(dt.strftime("%Y-%m-%d %H:%M:%S"))
        else:
            self.selected_datetime = None
            self.datetime_var.set("")
    
    def _on_input_change(self, *args):
        """处理输入框变化事件，尝试解析用户输入的时间字符串"""
        # 取消之前的防抖定时器
        if self._debounce_timer:
            self.parent.after_cancel(self._debounce_timer)
            self._debounce_timer = None
            
        # 设置新的防抖定时器
        self._debounce_timer = self.parent.after(self._debounce_delay, self._parse_input)
    
    def _parse_input(self):
        """实际解析输入的时间字符串（防抖后执行）"""
        input_str = self.datetime_var.get().strip()
        if not input_str:
            self.selected_datetime = None
            return
        
        # 尝试解析不同格式的时间字符串
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d %H:%M"
        ]
        
        for fmt in formats:
            try:
                dt = datetime.datetime.strptime(input_str, fmt)
                self.selected_datetime = dt
                # 更新显示为标准格式
                self.datetime_var.set(dt.strftime("%Y-%m-%d %H:%M:%S"))
                return
            except ValueError:
                continue
        
        # 如果所有格式都解析失败，保持原输入但将selected_datetime设为None
        self.selected_datetime = None
    
    def get_selected_datetime(self):
        return self.selected_datetime
    
    def get_datetime(self):
        """兼容旧版本的方法名"""
        return self.selected_datetime
