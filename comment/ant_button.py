import tkinter as tk
from tkinter import ttk
from typing import Optional, Callable, Union

class AntButton(ttk.Button):
    """符合Ant Design风格的Button组件"""
    
    def __init__(self, 
                 master: Optional[tk.Widget] = None, 
                 text: str = "",
                 command: Optional[Callable] = None,
                 type: str = "default",  # primary, default, dashed, text, link
                 size: str = "middle",  # large, middle, small
                 shape: str = "round",  # round, circle, default
                 danger: bool = False,
                 loading: bool = False,
                 disabled: bool = False,
                 block: bool = False,
                 **kwargs):
        """
        初始化Ant Design风格按钮
        
        Args:
            master: 父组件
            text: 按钮文本
            command: 点击事件回调函数
            type: 按钮类型: primary, default, dashed, text, link
            size: 按钮尺寸: large, middle, small
            shape: 按钮形状: round, circle, default
            danger: 是否为危险按钮
            loading: 是否显示加载状态
            disabled: 是否禁用
            block: 是否为块级按钮
            **kwargs: 其他ttk.Button参数
        """
        self.type = type
        self.size = size
        self.shape = shape
        self.danger = danger
        self.loading = loading
        self.disabled = disabled
        self.block = block
        
        # 配置样式
        self._create_style()
        
        # 处理块级按钮
        if self.block:
            kwargs['width'] = kwargs.get('width', 200)  # 默认块级宽度
        
        # 使用TButton的默认样式，不需要创建新的Layout
        super().__init__(
            master=master,
            text=text,
            command=command,
            state=tk.DISABLED if disabled else tk.NORMAL,
            **kwargs
        )
        
        # 应用形状
        self._apply_shape()
    
    def _create_style(self) -> None:
        """创建按钮样式"""
        # 获取当前样式
        style = ttk.Style()
        
        # 定义颜色主题
        colors = {
            "primary": "#1890ff",
            "success": "#52c41a",
            "warning": "#faad14",
            "error": "#f5222d",
            "info": "#1890ff",
            "default": "#d9d9d9",
            "text": "#333333",
            "border": "#d9d9d9",
            "background": "#ffffff"
        }
        
        # 根据类型确定颜色
        if self.type == "primary":
            bg_color = colors["error"] if self.danger else colors["primary"]
            fg_color = "#ffffff"
            border_color = bg_color
        elif self.type == "default":
            bg_color = colors["background"]
            fg_color = colors["text"]
            border_color = colors["border"]
        elif self.type == "dashed":
            bg_color = colors["background"]
            fg_color = colors["primary"] if not self.danger else colors["error"]
            border_color = colors["primary"] if not self.danger else colors["error"]
        elif self.type == "text":
            bg_color = colors["background"]
            fg_color = colors["primary"] if not self.danger else colors["error"]
            border_color = colors["background"]
        elif self.type == "link":
            bg_color = colors["background"]
            fg_color = colors["primary"] if not self.danger else colors["error"]
            border_color = colors["background"]
        else:
            bg_color = colors["background"]
            fg_color = colors["text"]
            border_color = colors["border"]
        
        # 根据尺寸确定内边距
        if self.size == "large":
            padding = (16, 16)
            font_size = 14
        elif self.size == "small":
            padding = (8, 8)
            font_size = 12
        else:  # middle
            padding = (12, 12)
            font_size = 13
        
        # 配置TButton的基础样式，这将影响所有ttk.Button
        style.configure(
            "TButton",
            font=('Microsoft YaHei', font_size),
            foreground=fg_color,
            background=bg_color,
            bordercolor=border_color,
            padding=padding,
            relief=tk.FLAT if self.type in ["text", "link"] else tk.SOLID
        )
        
        # 配置悬停效果
        style.map(
            "TButton",
            foreground=[
                ('active', fg_color),
                ('disabled', colors["default"])
            ],
            background=[
                ('active', self._darken_color(bg_color, 10) if self.type not in ["text", "link"] else bg_color),
                ('disabled', colors["background"])
            ],
            bordercolor=[
                ('active', self._darken_color(border_color, 10) if self.type not in ["text", "link"] else border_color),
                ('disabled', colors["default"])
            ]
        )
    
    def _apply_shape(self):
        """应用按钮形状"""
        if self.shape == "circle":
            # 圆形按钮需要固定宽高
            self.config(width=30)  # ttk.Button只需要设置width，高度会自动调整
    
    def _darken_color(self, color: str, percent: int) -> str:
        """将颜色变暗"""
        if color.startswith('#'):
            color = color[1:]
        r = int(color[0:2], 16)
        g = int(color[2:4], 16)
        b = int(color[4:6], 16)
        
        r = max(0, int(r * (100 - percent) / 100))
        g = max(0, int(g * (100 - percent) / 100))
        b = max(0, int(b * (100 - percent) / 100))
        
        return f'#{r:02x}{g:02x}{b:02x}'
    
    def set_loading(self, loading: bool):
        """设置加载状态"""
        self.loading = loading
        if loading:
            self.config(text="加载中...", state=tk.DISABLED)
        else:
            self.config(state=tk.NORMAL)
    
    def set_disabled(self, disabled: bool):
        """设置禁用状态"""
        self.disabled = disabled
        self.config(state=tk.DISABLED if disabled else tk.NORMAL)
    
    def set_text(self, text: str):
        """设置按钮文本"""
        self.config(text=text)
    
    def set_type(self, type: str):
        """设置按钮类型"""
        self.type = type
        self._create_style()  # 重新创建样式
        self._apply_shape()
    
    def set_size(self, size: str):
        """设置按钮尺寸"""
        self.size = size
        self._create_style()  # 重新创建样式
        self._apply_shape()
    
    def set_danger(self, danger: bool):
        """设置是否为危险按钮"""
        self.danger = danger
        self._create_style()  # 重新创建样式