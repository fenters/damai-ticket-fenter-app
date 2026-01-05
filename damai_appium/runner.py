"""Appium-based ticket grabbing runner for the Damai mobile app."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from enum import Enum
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple, Union

from appium import webdriver
from appium.options.common.base import AppiumOptions
from appium.webdriver.common.appiumby import AppiumBy

from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

from .config import AppTicketConfig


Logger = Callable[[str, str, Dict[str, Any]], None]
StopSignal = Callable[[], bool]
DriverFactory = Callable[[str, Dict[str, Any]], Any]


class LogLevel(str, Enum):
    STEP = "step"
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


class RunnerPhase(str, Enum):
    INIT = "init"
    CONNECTING = "connecting"
    APPLYING_SETTINGS = "applying_settings"
    SELECTING_CITY = "selecting_city"
    SEARCHING_EVENT = "searching_event"
    TAPPING_PURCHASE = "tapping_purchase"
    SELECTING_DATE = "selecting_date"
    SELECTING_SESSION = "selecting_session"
    SELECTING_PRICE = "selecting_price"
    SELECTING_QUANTITY = "selecting_quantity"
    CONFIRMING_PURCHASE = "confirming_purchase"
    SELECTING_USERS = "selecting_users"
    SUBMITTING_ORDER = "submitting_order"
    COMPLETED = "completed"
    STOPPED = "stopped"
    FAILED = "failed"


class TicketRunnerError(RuntimeError):
    """Base exception for ticket runner failures."""


class TicketRunnerStopped(TicketRunnerError):
    """Raised when the runner is stopped externally."""


class FailureReason(str, Enum):
    USER_STOP = "user_stop"
    APPIUM_CONNECTION = "appium_connection_failed"
    FLOW_FAILURE = "flow_failure"
    UNEXPECTED = "unexpected_error"
    MAX_RETRIES = "max_retries_reached"


@dataclass
class TicketRunLogEntry:
    timestamp: float
    level: LogLevel
    message: str
    phase: RunnerPhase
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        iso_time = datetime.fromtimestamp(self.timestamp).isoformat(timespec="milliseconds")
        return {
            "timestamp": self.timestamp,
            "timestamp_iso": iso_time,
            "level": self.level.value,
            "message": self.message,
            "phase": self.phase.value,
            "context": self.context,
        }


@dataclass
class TicketRunMetrics:
    start_time: float
    end_time: float
    attempts: int
    success: bool
    final_phase: RunnerPhase
    failure_reason: Optional[str]
    failure_code: Optional[FailureReason]

    def to_dict(self) -> Dict[str, Any]:
        duration = max(self.end_time - self.start_time, 0.0)
        return {
            "start_time": self.start_time,
            "start_time_iso": datetime.fromtimestamp(self.start_time).isoformat(timespec="milliseconds"),
            "end_time": self.end_time,
            "end_time_iso": datetime.fromtimestamp(self.end_time).isoformat(timespec="milliseconds"),
            "duration_seconds": round(duration, 3),
            "attempts": self.attempts,
            "retries": max(self.attempts - 1, 0),
            "success": self.success,
            "final_phase": self.final_phase.value,
            "failure_reason": self.failure_reason,
            "failure_code": self.failure_code.value if self.failure_code else None,
        }


@dataclass
class TicketRunReport:
    metrics: TicketRunMetrics
    logs: List[TicketRunLogEntry]
    phase_history: List[RunnerPhase]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metrics": self.metrics.to_dict(),
            "phase_history": [phase.value for phase in self.phase_history],
            "logs": [entry.to_dict() for entry in self.logs],
        }

    def dump_json(self, path: Union[str, Path], *, indent: int = 2) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8") as fp:
            json.dump(self.to_dict(), fp, ensure_ascii=False, indent=indent)
        return target


def _default_logger(level: str, message: str, context: Optional[Dict[str, Any]] = None) -> None:
    context = context or {}
    extra = " ".join(f"{key}={value}" for key, value in context.items())
    if extra:
        print(f"[{level.upper()}] {message} | {extra}")
    else:
        print(f"[{level.upper()}] {message}")


@dataclass
class DamaiAppTicketRunner:
    """Encapsulates the Damai Appium ticket grabbing workflow."""

    config: AppTicketConfig
    logger: Logger = _default_logger
    stop_signal: StopSignal = lambda: False
    driver_factory: Optional[DriverFactory] = None
    current_phase: RunnerPhase = field(init=False)
    phase_history: List[RunnerPhase] = field(init=False)
    last_report: Optional[TicketRunReport] = field(init=False, default=None)

    _log_entries: List[TicketRunLogEntry] = field(init=False, default_factory=list)
    _run_start_time: float = field(init=False, default=0.0)

    def __post_init__(self) -> None:
        if self.logger is None:
            self.logger = _default_logger
        if self.stop_signal is None:
            self.stop_signal = lambda: False
        self._driver = None
        self._wait: Optional[WebDriverWait] = None
        self.current_phase = RunnerPhase.INIT
        self.phase_history = [RunnerPhase.INIT]
        self._log_entries = []
        self._run_start_time = 0.0
        self.last_report = None

    def preheat(self) -> None:
        """执行预热操作：连接Appium、选择城市、搜索目标。"""
        self.current_phase = RunnerPhase.INIT
        self.phase_history = [RunnerPhase.INIT]
        self._log_entries = []
        
        self._log(LogLevel.INFO, "开始预热操作")
        
        # 创建driver
        self._transition_to(RunnerPhase.CONNECTING)
        self._log(LogLevel.STEP, "连接Appium server")
        self._driver = self._create_driver()
        self._wait = WebDriverWait(self._driver, self.config.wait_timeout)
        
        # 应用设置
        self._transition_to(RunnerPhase.APPLYING_SETTINGS)
        self._log(LogLevel.STEP, "应用Appium设置")
        self._apply_driver_settings()
        
        # 选择城市
        if self.config.city:
            self._transition_to(RunnerPhase.SELECTING_CITY)
            self._log(LogLevel.STEP, f"选择城市: {self.config.city}")
            if not self._select_city(self.config.city):
                self._log(LogLevel.WARNING, f"未找到城市 {self.config.city}")
        
        # 搜索目标
        if self.config.keyword:
            self._transition_to(RunnerPhase.SEARCHING_EVENT)
            self._log(LogLevel.STEP, f"搜索演出: {self.config.keyword}")
            if not self._search_event(self.config.keyword, click_result=False):
                raise TicketRunnerError("未能完成演出搜索")
        
        self._log(LogLevel.SUCCESS, "预热操作完成")

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------
    def _transition_to(self, phase: RunnerPhase) -> None:
        if phase == self.current_phase:
            return
        self.current_phase = phase
        self.phase_history.append(phase)

    def _mark_failure(self) -> None:
        if self.current_phase != RunnerPhase.FAILED:
            self._transition_to(RunnerPhase.FAILED)

    def _mark_stopped(self) -> None:
        if self.current_phase != RunnerPhase.STOPPED:
            self._transition_to(RunnerPhase.STOPPED)

    def _ensure_driver(self):
        if self._driver is None:
            raise TicketRunnerError("Appium driver 尚未初始化")
        return self._driver

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def run(self, max_retries: int = 1, start_time: Optional[float] = None) -> bool:
        """Run the ticket grabbing flow with optional retries and scheduled start time."""
        self.current_phase = RunnerPhase.INIT
        self.phase_history = [RunnerPhase.INIT]
        self._log_entries = []
        self.last_report = None
        self._run_start_time = time.time()

        # 如果设置了开始时间，等待到指定时间
        if start_time and start_time > time.time():
            wait_time = start_time - time.time()
            self._log(LogLevel.INFO, f"等待到指定时间开始抢票，剩余时间: {int(wait_time)}秒")
            while wait_time > 0:
                if self._should_stop():
                    self._mark_stopped()
                    return False
                # 每100ms检查一次是否需要停止
                time.sleep(min(0.1, wait_time))
                wait_time = start_time - time.time()
            self._log(LogLevel.INFO, "到达指定时间，开始抢票")

        attempts = 0
        success = False
        failure_code: Optional[FailureReason] = None
        failure_message: Optional[str] = None

        max_retries = max(1, max_retries)

        while attempts < max_retries and not self._should_stop():
            attempts += 1
            self._log(
                LogLevel.INFO,
                f"第 {attempts} 次尝试",
                {"attempt": attempts, "max_retries": max_retries},
            )
            try:
                # 如果driver已经存在（预热过），则跳过预热步骤
                skip_preheat = self._driver is not None
                if self._execute_once(skip_preheat=skip_preheat):
                    success = True
                    self._log(LogLevel.SUCCESS, "抢票流程执行完成", {"attempt": attempts})
                    break
            except TicketRunnerStopped as exc:
                self._mark_stopped()
                failure_code = FailureReason.USER_STOP
                failure_message = str(exc).strip() or "用户已停止流程"
                self._log(LogLevel.WARNING, failure_message, {"attempt": attempts})
                break
            except TicketRunnerError as exc:
                self._mark_failure()
                failure_code, failure_message = self._diagnose_failure(exc)
                self._log(LogLevel.ERROR, failure_message, {"attempt": attempts})
            except Exception as exc:  # noqa: BLE001
                self._mark_failure()
                failure_code = FailureReason.UNEXPECTED
                failure_message = f"未预期的异常: {exc}"
                self._log(LogLevel.ERROR, failure_message, {"attempt": attempts})

            if not success and attempts < max_retries and not self._should_stop():
                # 回到首页 - 如果driver不存在则尝试重新创建
                if self._driver is None:
                    try:
                        self._log(LogLevel.INFO, "Driver已被清理，尝试重新创建driver")
                        self._driver = self._create_driver()
                        self._wait = WebDriverWait(self._driver, self.config.wait_timeout)
                        self._apply_driver_settings()
                    except Exception as e:
                        self._log(LogLevel.ERROR, f"重新创建driver失败: {e}")
                        # 即使创建失败也继续重试，下次循环会再尝试
                
                if self._driver is not None:
                    try:
                        self._navigate_to_homepage()
                    except Exception as e:
                        self._log(LogLevel.ERROR, f"返回首页失败: {e}")
                
                self._log(LogLevel.INFO, "准备重试", {"attempt": attempts + 1})
                time.sleep(max(self.config.retry_delay, 0))

        end_time = time.time()

        if not success:
            if failure_code is None:
                if self.current_phase == RunnerPhase.STOPPED or self._should_stop():
                    failure_code = FailureReason.USER_STOP
                    failure_message = failure_message or "流程被请求停止"
                else:
                    failure_code = FailureReason.MAX_RETRIES
                    failure_message = failure_message or "达到最大重试次数仍未成功"

        duration = max(end_time - self._run_start_time, 0.0)
        stats_context = {
            "attempts": attempts,
            "retries": max(attempts - 1, 0),
            "duration": round(duration, 3),
            "success": success,
        }
        if failure_code:
            stats_context["failure_code"] = failure_code.value
        self._log(LogLevel.INFO, "执行统计", stats_context)

        metrics = TicketRunMetrics(
            start_time=self._run_start_time,
            end_time=end_time,
            attempts=attempts,
            success=success,
            final_phase=self.current_phase,
            failure_reason=failure_message,
            failure_code=failure_code,
        )

        self.last_report = TicketRunReport(
            metrics=metrics,
            logs=list(self._log_entries),
            phase_history=list(self.phase_history),
        )

        return success

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _execute_once(self, skip_preheat: bool = False) -> bool:
        try:
            self._ensure_not_stopped()
            
            if not skip_preheat:
                # 创建driver (skipped if preheated)
                self._transition_to(RunnerPhase.CONNECTING)
                self._log(LogLevel.STEP, "连接 Appium server")
                try:
                    self._driver = self._create_driver()
                except Exception as exc:  # noqa: BLE001
                    raise TicketRunnerError(f"连接 Appium server 失败: {exc}") from exc
                
                # 初始化wait和应用设置 (skipped if preheated)
                driver = self._ensure_driver()
                self._wait = WebDriverWait(driver, self.config.wait_timeout)
                self._transition_to(RunnerPhase.APPLYING_SETTINGS)
                self._apply_driver_settings()
            else:
                # 使用预热好的driver，跳过连接和设置步骤
                self._ensure_driver()
                self._log(LogLevel.INFO, "使用预热好的driver，跳过连接和设置步骤")

            self._log(LogLevel.STEP, "开始执行抢票流程")
            result = self._perform_ticket_flow(skip_preheat)
            return result
        finally:
            if not skip_preheat:
                # 如果是预热的driver，不清理，由外部管理
                self._cleanup_driver()

    def _create_driver(self):
        caps = self.config.desired_capabilities
        if self.driver_factory is not None:
            driver = self.driver_factory(self.config.endpoint, caps)
        else:
            options = AppiumOptions()
            options.load_capabilities(caps)
            driver = webdriver.Remote(self.config.endpoint, options=options)  # type: ignore[attr-defined]
        return driver

    def _apply_driver_settings(self) -> None:
        if not self._driver:
            return
        try:
            self._driver.update_settings(
                {
                    "waitForIdleTimeout": 0,
                    "actionAcknowledgmentTimeout": 0,
                    "keyInjectionDelay": 0,
                    "waitForSelectorTimeout": 300,
                    "ignoreUnimportantViews": False,
                    "allowInvisibleElements": True,
                    "enableNotificationListener": False,
                }
            )
        except Exception as exc:  # noqa: BLE001
            self._log(LogLevel.WARNING, f"更新驱动设置失败: {exc}")

    def _perform_ticket_flow(self, skip_preheat: bool = False) -> bool:
        try:
            self._ensure_not_stopped()
            
            if not skip_preheat:
                # 选择城市 (skipped if preheated)
                if self.config.city:
                    self._transition_to(RunnerPhase.SELECTING_CITY)
                    self._log(LogLevel.STEP, f"选择城市: {self.config.city}")
                    if not self._select_city(self.config.city):
                        self._log(LogLevel.WARNING, f"未找到城市 {self.config.city}")

                # 搜索目标 (skipped if preheated)
                self._ensure_not_stopped()
                if self.config.keyword:
                    self._transition_to(RunnerPhase.SEARCHING_EVENT)
                    self._log(LogLevel.STEP, f"搜索演出: {self.config.keyword}")
                    if not self._search_event(self.config.keyword):
                        raise TicketRunnerError("未能完成演出搜索")
            else:
                # 预热情况下，只需要点击搜索结果
                self._ensure_not_stopped()
                if self.config.keyword:
                    self._transition_to(RunnerPhase.SEARCHING_EVENT)
                    self._log(LogLevel.STEP, f"使用预热搜索结果: {self.config.keyword}")
                    if not self._search_event(self.config.keyword, skip_search=True):
                        raise TicketRunnerError("未能点击搜索结果")

            # 如果需要选择观演人
            self._ensure_not_stopped()
            self._transition_to(RunnerPhase.TAPPING_PURCHASE)
            self._select_theme_dialog()

            self._ensure_not_stopped()
            self._transition_to(RunnerPhase.TAPPING_PURCHASE)
            self._log(LogLevel.STEP, "尝试点击预约/购买按钮")
            if not self._tap_purchase_button():
                raise TicketRunnerError("未能找到预约/购买入口")

            self._ensure_not_stopped()
            self._transition_to(RunnerPhase.SELECTING_DATE)
            self._log(LogLevel.STEP, "选择日期")
            if not self._select_date():
                self._log(LogLevel.STEP, "不需要选择日期")

            self._ensure_not_stopped()
            self._transition_to(RunnerPhase.SELECTING_SESSION)
            self._log(LogLevel.STEP, "选择场次")
            if not self._select_session():
                raise TicketRunnerError("未能选择场次")

            self._ensure_not_stopped()
            self._transition_to(RunnerPhase.SELECTING_PRICE)
            self._log(LogLevel.STEP, "选择票价")
            if not self._select_price():
                raise TicketRunnerError("未能选择票价")


            self._ensure_not_stopped()
            # 无论是否有用户配置，都执行数量选择
            self._transition_to(RunnerPhase.SELECTING_QUANTITY)
            self._log(LogLevel.STEP, "选择数量")
            self._select_quantity()
            

            # 去预约/购买
            self._ensure_not_stopped()
            self._transition_to(RunnerPhase.CONFIRMING_PURCHASE)
            self._log(LogLevel.STEP, "确认购买")
            (success, text) = self._confirm_purchase()
            if not success:
                raise TicketRunnerError(f"未能进入确认页面,{text}")
            

            # self._ensure_not_stopped()
            # self._transition_to(RunnerPhase.SUBMITTING_ORDER)
            # self._log(LogLevel.STEP, "提交订单")
            # self._submit_order()

            self._transition_to(RunnerPhase.COMPLETED)
            return True
        except TicketRunnerStopped:
            self._mark_stopped()
            raise
        except TicketRunnerError:
            self._mark_failure()
            raise
        except Exception as exc:  # noqa: BLE001
            self._mark_failure()
            phase = self.current_phase.value if isinstance(self.current_phase, RunnerPhase) else str(self.current_phase)
            raise TicketRunnerError(f"执行阶段 {phase} 出现异常: {exc}") from exc

    # ------------------------------------------------------------------
    # Appium interaction primitives
    # ------------------------------------------------------------------
    def _navigate_to_homepage(self) -> None:
        """Navigate back to the Damai homepage using multiple fallback strategies."""
        self._ensure_not_stopped()
 
        driver = self._ensure_driver()
    
        # 使用返回按钮回到首页
        try:
            self._log(LogLevel.INFO, "尝试使用返回按钮回到首页")
            # 连续点击返回按钮最多5次
            for _ in range(5):
                self._ensure_not_stopped()
                driver.press_keycode(4)  # Android返回按钮
                time.sleep(0.5)
                
                # 检查是否已经回到首页
                try:
                    WebDriverWait(driver, 1.0).until(
                        EC.visibility_of_element_located((By.ID, "cn.damai:id/homepage_header_search"))
                    )
                    self._log(LogLevel.SUCCESS, "通过返回按钮成功回到首页")
                    return
                except:
                    continue
        except Exception as e:
            self._log(LogLevel.WARNING, f"返回按钮策略失败: {e}")

    def _smart_wait_and_click(
        self,
        selector: Sequence[Any],
        backups: Sequence[Sequence[Any]] = (),
        timeout: float = 1.5,
    ) -> bool:
        driver = self._ensure_driver()
        selectors: List[Sequence[Any]] = [selector, *backups]
        for i, (by, value) in enumerate(selectors):
            self._ensure_not_stopped()
            try:
              
                # 等待元素出现并可见
                element = WebDriverWait(driver, timeout).until(
                    EC.visibility_of_element_located((by, value))
                )

                # 尝试点击元素
                try:
                    # 首先尝试直接点击
                    element.click()
                    return True
                except Exception as e:
                   
                    # 如果直接点击失败，尝试使用 mobile: clickGesture
                    rect = element.rect
                    x = rect["x"] + rect["width"] // 2
                    y = rect["y"] + rect["height"] // 2
                    
             
                    driver.execute_script(
                        "mobile: clickGesture",
                        {
                            "x": x,
                            "y": y,
                            "duration": 50,
                        },
                    )
                   
                    return True
                    
            except TimeoutException:
               
                continue
            except Exception as e:
                continue
        
        return False

    def _ultra_fast_click(self, by: Any, value: Any, timeout: float = 1.5) -> bool:
        driver = self._ensure_driver()
        try:
            element = WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((by, value))
            )
            rect = element.rect
            driver.execute_script(
                "mobile: clickGesture",
                {
                    "x": rect["x"] + rect["width"] // 2,
                    "y": rect["y"] + rect["height"] // 2,
                    "duration": 50,
                },
            )
            return True
        except TimeoutException:
            return False

    def _ultra_batch_click(
        self, selectors: Iterable[Sequence[Any]], timeout: float = 2.0
    ) -> None:
        driver = self._ensure_driver()
        coordinates: List[Dict[str, Any]] = []
        for by, value in selectors:
            self._ensure_not_stopped()
            try:
                element = WebDriverWait(driver, timeout).until(
                    EC.presence_of_element_located((by, value))
                )
                rect = element.rect
                coordinates.append(
                    {
                        "x": rect["x"] + rect["width"] // 2,
                        "y": rect["y"] + rect["height"] // 2,
                        "label": value,
                    }
                )
            except TimeoutException:
                self._log(LogLevel.WARNING, f"未找到元素: {value}")
            except Exception as exc:  # noqa: BLE001
                self._log(LogLevel.WARNING, f"查找元素失败 {value}: {exc}")

        for item in coordinates:
            self._ensure_not_stopped()
            driver.execute_script(
                "mobile: clickGesture",
                {
                    "x": item["x"],
                    "y": item["y"],
                    "duration": 30,
                },
            )
            time.sleep(0.01)

    # ------------------------------------------------------------------
    # Flow steps

    def _select_city(self, city: str) -> bool:
        driver = self._ensure_driver()
        
        # 第一步：找到并点击城市选择入口
        city_entry_selectors = [
            # 用户提供的XPath选择器
            (By.XPATH, "//android.widget.TextView[@resource-id='cn.damai:id/home_city']"),
        ]
        
        entered_city_selection = False
        for by, value in city_entry_selectors:
            try:
                city_entry = WebDriverWait(driver, 3.0).until(
                    EC.visibility_of_element_located((by, value))
                )
                current_city = city_entry.text.strip()
                if city == current_city:
                    return True
                # 点击城市选择入口，进入城市选择页面
                city_entry.click()
                # 等待城市选择页面加载
                time.sleep(1.0)
                entered_city_selection = True
                break
                
            except TimeoutException:
                continue
            except Exception as e:
                continue
        
        if not entered_city_selection:
            return False

        # 定义获取可见城市列表的函数，每次调用都会重新查找容器
        def get_visible_cities():
            current_container = None
            try:
                user_container_xpath = "//androidx.recyclerview.widget.RecyclerView[@resource-id='cn.damai:id/city_search_list']"
                current_container = WebDriverWait(driver, 2.0).until(
                    EC.presence_of_element_located((By.XPATH, user_container_xpath))
                )
                # 使用.//在当前容器内搜索，而不是//在整个文档中搜索
                city_elements = current_container.find_elements(By.XPATH, f".//android.widget.TextView[@resource-id='cn.damai:id/select_city_list_item' and @text='{city}']")
                return city_elements[0] if city_elements else None
            except Exception as e:
                return None
        
        try:
            search_box = WebDriverWait(driver, 3.0).until(
                EC.visibility_of_element_located((By.XPATH, "//android.widget.EditText[@resource-id='cn.damai:id/search_edit_text']"))
            )
            search_box.click()

            search_box.send_keys(city)
            time.sleep(0.5)
            # 按回车键执行搜索

            # 等待搜索结果加载完成
            time.sleep(1.0)
            
            # 使用修复后的get_visible_cities函数获取搜索结果
            city_element = get_visible_cities()  # 复用现有函数获取可见城市
           
            if city_element:
                city_element.click()
             
                return True
            else:
                return False
        except Exception as e:

            return False


    def _search_event(self, keyword: str, click_result: bool = True, skip_search: bool = False) -> bool:
        driver = self._ensure_driver()

        if not skip_search:
            try:
                # 1. 点击搜索框
                search_input_btn = WebDriverWait(driver, 2.0).until(
                        EC.visibility_of_element_located((By.ID, "cn.damai:id/homepage_header_search"))
                    )
                search_input_btn.click()
                # 2. 输入搜索关键词
                search_input = WebDriverWait(driver, 2.0).until(
                    EC.visibility_of_element_located((By.ID, "cn.damai:id/header_search_v2_input"))
                )
                time.sleep(0.5)
                search_input.click()
                search_input.clear()
                # 输入关键词
                search_input.send_keys(keyword)

                self._log(LogLevel.INFO, f"已输入搜索关键词: {keyword}")
                    
            except TimeoutException as e:
                self._log(LogLevel.ERROR, f"输入搜索关键词失败: {e}")
                return False

        # 只有在非预热情况下才执行搜索操作
        if not skip_search:
            try:
                # 3. 点击搜索后的结果
                search_results = WebDriverWait(driver, 1.0).until(
                            EC.visibility_of_all_elements_located((By.XPATH, '//android.widget.TextView[@resource-id="cn.damai:id/tv_word"]'))
                        )

                if len(search_results) > 0:
                    search_results[0].click()
                else:
                    driver.press_keycode(66)  # 按下回车
            except Exception as e:
                    driver.press_keycode(66)  # 按下回车


        # 如果不需要点击搜索结果，直接返回
        if not click_result:
            self._log(LogLevel.INFO, "已执行搜索，不点击搜索结果")
            return True
            
        # 等待详情页面加载
        time.sleep(0.5)
        # 4. 点击第一个搜索结果
        try:
            first_result = WebDriverWait(driver, 3.0).until(
                EC.visibility_of_element_located((By.XPATH, '(//android.widget.LinearLayout[@resource-id="cn.damai:id/ll_search_item"])[1]'))
            )
            first_result.click()
            # 等待详情页面加载
            time.sleep(0.5)
            return True
            
        except TimeoutException as e:
            return False

   
    def _tap_purchase_button(self) -> bool:
        driver = self._ensure_driver()
        selectors = (By.ID, "cn.damai:id/trade_project_detail_purchase_status_bar_container_fl")
        # 尝试点击元素
        try:
            element = WebDriverWait(driver, 1.5).until(
                    EC.visibility_of_element_located(selectors)
                )
            element.click()
            return True
        except Exception as e:
            return False


    def _select_theme_dialog(self) -> bool:
        driver = self._ensure_driver()
        
        # Try to find and click the confirm button if it exists
        confirm_selector = (By.ID, "cn.damai:id/damai_theme_dialog_confirm_btn")
        if self._smart_wait_and_click(confirm_selector, timeout=1.0):

            # Wait for the performer selection page to load
            time.sleep(1.0)
            
            try:
                # Find all view elements at the specified path
                base_xpath = "//android.widget.FrameLayout[@resource-id='cn.damai:id/web_container']/android.webkit.WebView/android.webkit.WebView/android.view.View/android.view.View/android.view.View"
                all_views = WebDriverWait(driver, 3.0).until(
                    EC.presence_of_all_elements_located((By.XPATH, base_xpath))
                )
                
                if len(all_views) >= 3:  # Need at least 3 views to have [2] and not be last
                    # Select views from index 2 to second last
                    for i in range(2, len(all_views) - 1):
                        self._ensure_not_stopped()
                        view_xpath = f"{base_xpath}[{i+1}]"  # XPath is 1-indexed
                        self._log(LogLevel.INFO, f"选择观演人 {i-1}", {"xpath": view_xpath})
                        
                        # Click the view element
                        view_element = driver.find_element(By.XPATH, view_xpath)
                        view_element.click()
                        time.sleep(0.5)  # Short delay between clicks
                    # Click the confirm button
                    confirm_button_selector = (By.XPATH, "//android.widget.Button[@text='确定']")
                    self._smart_wait_and_click(confirm_button_selector)
                #需要实现一下返回上一页（按一下返回）
                driver.press_keycode(4)

            except Exception as e:
                self._log(LogLevel.ERROR, f"观演人选择失败: {e}")

    def _select_date(self) -> bool:
        """Select the target date on the date selection page.
        
        Step 6 of the user's flow: Select the corresponding date.
        """
        driver = self._ensure_driver()
        
        # Wait for date selection page to load
        try:
            date_moons = WebDriverWait(driver, 1.0).until(
                EC.presence_of_element_located((By.ID, "cn.damai:id/hrv_canlendar"))
            )
        except TimeoutException:
            return False

        target_month = None
        target_day = None
        if hasattr(self.config, "date") and self.config.date:
            date_obj = datetime.strptime(self.config.date, "%Y-%m-%d %H:%M:%S")
            # Extract month and day as separate values
            target_month = date_obj.month  # Integer: 1-12
            target_day = date_obj.day      # Integer: 1-31
        
        if date_moons:
            try:
                # 使用模糊匹配查找月份元素 - 添加resource-id约束提高准确性
                month_text = f"{target_month}月"
                month_xpath = f"//android.widget.TextView[@resource-id='cn.damai:id/tv_date' and contains(@text, '{month_text}')]"
                
                # 等待并点击匹配到的月份元素
                month_element = WebDriverWait(driver, 3.0).until(
                    EC.element_to_be_clickable((By.XPATH, month_xpath))
                )
                month_element.click()

                # 选择日期
                try:
                    self._log(LogLevel.INFO, f"尝试选择日期: {target_day}", {"target_day": target_day})
                    
                    # 使用精确匹配查找日期元素 - 使用正确的resource-id
                    day_xpath = f"//android.widget.TextView[@resource-id='cn.damai:id/tv_day' and @text='{target_day}']"
                    
                    # 等待并点击匹配到的日期元素
                    day_element = WebDriverWait(driver, 3.0).until(
                        EC.element_to_be_clickable((By.XPATH, day_xpath))
                    )
                    day_element.click()
                    self._log(LogLevel.SUCCESS, f"成功选择日期: {target_day}")
                except Exception as e:
                    self._log(LogLevel.ERROR, f"日期选择失败: 没有这个日期")
                    return False
                    
            except Exception as e:
                self._log(LogLevel.ERROR, f"月份选择失败: 没有这个月份")
                return False

        return True

    def _select_session(self) -> None:
        # 如果没有session_index，跳过场次选择
        if self.config.session_index is None:
            return False

        driver = self._ensure_driver()

        try:
            container = WebDriverWait(driver, 1.0).until(
                    EC.visibility_of_element_located((By.ID, "cn.damai:id/project_detail_perform_flowlayout"))
                )
        except TimeoutException:
            self._log(LogLevel.WARNING, "未找到场次容器，跳过场次选择")
            return False
        # 使用多个选择器尝试场次选择
        selectors = [
            f'.//android.widget.LinearLayout[{self.config.session_index}]',
            f'.//android.view.ViewGroup[{self.config.session_index}]',
            f'.//android.view.ViewGroup'
        ]
        
        session_elem = None
        for selector in selectors:
            try:
                session_elem = container.find_element(By.XPATH, selector)
                break
            except Exception:
                continue
        
        if session_elem:
            session_elem.click()
        else:
            self._log(LogLevel.ERROR, f"未找到场次选择")
            return False
        
        return True

    def _select_price(self) -> None:
         # 如果没有session_index，跳过场次选择
        if self.config.price_index is None:
            return False

        driver = self._ensure_driver()

        try:
            container = WebDriverWait(driver, 2.0).until(
                    EC.visibility_of_element_located((By.ID, "cn.damai:id/project_detail_perform_price_flowlayout"))
                )
        except TimeoutException:
            self._log(LogLevel.WARNING, "未找到票价容器，跳过票价选择")
            return False
        # 使用多个选择器尝试票价选择
        selectors = [
            f'.//android.widget.FrameLayout[{self.config.price_index}]',
            f'.//android.widget.FrameLayout',
        ]
        
        price_elem = None
        for selector in selectors:
            try:
                price_elem = container.find_element(By.XPATH, selector)
                break
            except Exception:
                continue
        
        if price_elem:
            price_elem.click()
        else:
            self._log(LogLevel.ERROR, f"所有选择器都无法找到票价元素")
            return False

        return True

    def _select_quantity(self) -> bool:
        driver = self._ensure_driver()
        try:
            quantity = int(getattr(self.config, 'ticket_quantity', 1))

            # 找到显示当前数量的元素
            tv_num = WebDriverWait(driver, 1.0).until(
                EC.presence_of_element_located((By.ID, "cn.damai:id/tv_num"))
            )
            
            # 从文本中提取当前数量 (格式: "xx张")
            current_quantity_text = tv_num.text.strip()
            current_quantity = int(current_quantity_text.replace("张", ""))

            # 找到加号和减号按钮
            plus_button = WebDriverWait(driver, 1.0).until(
                EC.element_to_be_clickable((By.ID, "cn.damai:id/img_jia"))
            )
            minus_button = WebDriverWait(driver, 1.0).until(
                EC.element_to_be_clickable((By.ID, "cn.damai:id/img_jian"))
            )
            
            # 计算需要调整的数量
            delta = quantity - current_quantity
            
            # 根据delta值决定点击加号还是减号
            if delta > 0:
                # 需要增加数量，点击加号按钮
                for _ in range(delta):
                    plus_button.click()
                    time.sleep(0.3)  # 等待每次点击生效
            elif delta < 0:
                # 需要减少数量，点击减号按钮
                for _ in range(-delta):
                    minus_button.click()
                    time.sleep(0.3)  # 等待每次点击生效
            # 如果delta == 0，不需要任何操作
            
            return True
        except TimeoutException:
            return False
        except Exception as e:
            return False

    def _confirm_purchase(self) -> Tuple[bool, str]:
        driver = self._ensure_driver()
        try:
            buy_button = WebDriverWait(driver, 3.0).until(
                EC.element_to_be_clickable((By.ID, "cn.damai:id/btn_buy_view"))
            )
            text = buy_button.text
            buy_button.click()
            return (True,text)
        except TimeoutException:
            return (False,"")
        except Exception as e:
            return (False,"")

    def _submit_order(self) -> None:
        self._ensure_driver()
        if self.config.if_commit_order:
            self._smart_wait_and_click(
                (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("立即提交")'),
                [
                    (By.XPATH, '//android.widget.TextView[@text="立即提交"]'),
                    (
                        AppiumBy.ANDROID_UIAUTOMATOR,
                        'new UiSelector().textMatches(".*提交.*|.*确认.*")',
                    ),
                    (By.XPATH, '//*[contains(@text,"提交")]'),
                ],
            )

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------
    def _cleanup_driver(self) -> None:
        if self._driver is not None:
            try:
                self._driver.quit()
            except Exception:  # noqa: BLE001
                pass
            finally:
                self._driver = None
                self._wait = None

    def _ensure_not_stopped(self) -> None:
        if self._should_stop():
            raise TicketRunnerStopped("流程被请求停止")

    def _should_stop(self) -> bool:
        try:
            return bool(self.stop_signal())
        except Exception:  # noqa: BLE001
            return False

    def _diagnose_failure(self, exc: Exception) -> Tuple[FailureReason, str]:
        message = str(exc).strip() or exc.__class__.__name__
        if isinstance(exc, TicketRunnerStopped):
            return FailureReason.USER_STOP, message or "用户已停止流程"
        if isinstance(exc, TicketRunnerError):
            if "连接 Appium server" in message:
                return FailureReason.APPIUM_CONNECTION, message
            return FailureReason.FLOW_FAILURE, message
        return FailureReason.UNEXPECTED, f"未预期的异常: {message}"

    def _log(self, level: LogLevel, message: str, context: Optional[Dict[str, Any]] = None) -> None:
        if context is None:
            context = {}
        phase = self.current_phase
        context_copy = dict(context)
        context_copy.setdefault("phase", phase.value if isinstance(phase, RunnerPhase) else str(phase))
        entry = TicketRunLogEntry(
            timestamp=time.time(),
            level=level,
            message=message,
            phase=phase,
            context=context_copy,
        )
        self._log_entries.append(entry)
        try:
            self.logger(level.value, message, context_copy)
        except TypeError:
            try:
                self.logger(level.value, message)  # type: ignore[misc]
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001
            pass

    def get_last_report(self) -> Optional[TicketRunReport]:
        return self.last_report

    def export_last_report(self, path: Union[str, Path], *, indent: int = 2) -> Optional[Path]:
        if self.last_report is None:
            return None
        return self.last_report.dump_json(path, indent=indent)