import time
import tkinter as tk
from typing import Callable, Optional


class CountdownTimer:
    """
    独立的倒计时组件，仅负责倒计时与显示时间。
    
    特性：
    - 基于系统时间计算剩余时间，确保时间准确性
    - 稳定显示每个秒数，避免数字跳过
    - 提供简单的接口控制倒计时的开始、停止和重置
    - 支持自定义时间格式和回调函数
    """
    
    def __init__(self, root: tk.Tk, time_var: tk.StringVar, update_interval: int = 100):
        """
        初始化倒计时组件
        
        Args:
            root: Tkinter根窗口对象
            time_var: 用于显示时间的StringVar对象
            update_interval: 更新间隔（毫秒），默认100ms确保精度
        """
        self.root = root
        self.time_var = time_var
        self.update_interval = update_interval
        
        # 倒计时状态
        self._target_epoch: float = 0.0  # 目标结束时间戳
        self._running: bool = False  # 是否正在运行
        self._current_displayed: int = -1  # 当前显示的秒数
        self._timer_id: Optional[str] = None  # 定时器ID
        
        # 回调函数
        self._on_finish: Optional[Callable] = None  # 倒计时结束回调
        self._on_update: Optional[Callable[[int], None]] = None  # 每秒更新回调
    
    def start(self, duration: int, on_finish: Optional[Callable] = None, on_update: Optional[Callable[[int], None]] = None):
        """
        开始倒计时
        
        Args:
            duration: 倒计时时长（秒）
            on_finish: 倒计时结束时的回调函数
            on_update: 每秒更新时的回调函数
        """
        # 停止当前正在运行的倒计时
        self.stop()
        
        # 设置目标结束时间和回调
        self._target_epoch = time.time() + duration
        self._running = True
        self._current_displayed = -1
        self._on_finish = on_finish
        self._on_update = on_update
        
        # 开始倒计时循环
        self._tick()
    
    def stop(self):
        """停止倒计时"""
        self._running = False
        if self._timer_id:
            try:
                self.root.after_cancel(self._timer_id)
            except Exception:
                pass
            self._timer_id = None
    
    def reset(self):
        """重置倒计时"""
        self.stop()
        self._current_displayed = -1
        self.time_var.set("未开始")
    
    def get_remaining_seconds(self) -> int:
        """获取当前剩余秒数"""
        if not self._running:
            return 0
        remaining = max(int(self._target_epoch - time.time()), 0)
        return remaining
    
    def _tick(self):
        """倒计时心跳函数"""
        if not self._running:
            return
        
        # 计算剩余时间
        now = time.time()
        remaining = max(int(self._target_epoch - now), 0)
        
        # 更新显示（仅当剩余时间变化时）
        if remaining != self._current_displayed:
            # 格式化显示时间
            self.time_var.set(f"倒计时：{remaining} 秒")
            
            # 记录当前显示的秒数
            self._current_displayed = remaining
            
            # 调用更新回调
            if self._on_update:
                self._on_update(remaining)
        
        # 检查是否结束
        if remaining <= 0:
            self._running = False
            if self._on_finish:
                self._on_finish()
            return
        
        # 继续下一次更新
        self._timer_id = self.root.after(self.update_interval, self._tick)