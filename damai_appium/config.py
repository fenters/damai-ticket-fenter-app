"""Configuration helpers for the Damai Appium ticket runner."""

from __future__ import annotations

from dataclasses import dataclass, field, fields as dataclass_fields
import json
from pathlib import Path
import re
from typing import Any, Dict, Iterable, List, Optional, Union

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    ValidationInfo,
    field_validator,
)


_COMMENT_PATTERN = re.compile(r"//.*?$|/\*.*?\*/", re.DOTALL | re.MULTILINE)
_DEFAULT_CONFIG_FILENAMES = ("config.jsonc", "config.json")


def _normalise_server_url(url: str) -> str:
    url = url.strip()
    if not url:
        return url
    if not url.startswith(("http://", "https://")):
        return f"http://{url}"
    return url


def _clean_users(users: Iterable[Any]) -> List[str]:
    cleaned: List[str] = []
    for user in users or []:
        if user is None:
            continue

        if isinstance(user, str):
            user_str = user.strip()
        else:
            user_str = str(user).strip()

        if not user_str:
            continue

        cleaned.append(user_str)
    return cleaned


class ConfigValidationError(ValueError):
    """Raised when configuration validation fails."""

    def __init__(self, errors: List[str], *, message: str = "配置校验失败") -> None:
        self.errors = errors
        self.message = message
        detail = "\n".join(f"- {item}" for item in errors) if errors else ""
        full = message if not detail else f"{message}:\n{detail}"
        super().__init__(full)


def _format_validation_errors(exc: ValidationError) -> List[str]:
    formatted: List[str] = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error.get("loc", ()))
        message = error.get("msg", "未知错误")
        formatted.append(f"{location or 'root'}: {message}")
    return formatted


class DeviceOverrideModel(BaseModel):
    """Optional per-device overrides used when running multi-device sessions."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True, str_strip_whitespace=True)

    server_url: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("server_url", "serverUrl"),
    )
    keyword: Optional[str] = None
    users: Optional[List[str]] = None
    city: Optional[str] = None
    date: Optional[str] = None
    price: Optional[str] = None
    price_index: Optional[int] = Field(
        default=None,
        ge=0,
        validation_alias=AliasChoices("price_index", "priceIndex"),
    )
    session_index: Optional[int] = Field(
        default=0,
        ge=0,
        validation_alias=AliasChoices("session_index", "sessionIndex"),
    )
    ticket_quantity: Optional[int] = Field(
        default=None,
        ge=1,
        le=6,
        validation_alias=AliasChoices("ticket_quantity", "ticketQuantity"),
    )
    if_commit_order: Optional[bool] = Field(
        default=None,
        validation_alias=AliasChoices("if_commit_order", "ifCommitOrder"),
    )
    device_caps: Dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("device_caps", "deviceCaps"),
    )
    wait_timeout: Optional[float] = Field(
        default=None,
        ge=0.0,
        validation_alias=AliasChoices("wait_timeout", "waitTimeout"),
    )
    retry_delay: Optional[float] = Field(
        default=None,
        ge=0.0,
        validation_alias=AliasChoices("retry_delay", "retryDelay"),
    )

    @field_validator("server_url", mode="before")
    @classmethod
    def _normalise_optional_server_url(cls, value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        return _normalise_server_url(text)

    @field_validator("keyword", "city", "date", "price", mode="before")
    @classmethod
    def _strip_optional_strings(cls, value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("users", mode="before")
    @classmethod
    def _normalise_optional_users(cls, value: Any) -> Optional[List[str]]:
        if value is None:
            return None
        if value == "":
            return []
        if isinstance(value, str):
            return _clean_users([value])
        if isinstance(value, Iterable):
            return _clean_users(value)
        raise ValueError("users 必须是字符串数组")

    @field_validator("price_index", "session_index", mode="before")
    @classmethod
    def _parse_optional_index(cls, value: Any) -> Optional[int]:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("索引必须是非负整数") from exc
        if parsed < 0:
            raise ValueError("索引必须是非负整数")
        return parsed

    @field_validator("ticket_quantity", mode="before")
    @classmethod
    def _parse_optional_ticket_quantity(cls, value: Any) -> Optional[int]:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("购票数量必须是1-6之间的整数") from exc
        if parsed < 1 or parsed > 6:
            raise ValueError("购票数量必须是1-6之间的整数")
        return parsed

    @field_validator("device_caps", mode="before")
    @classmethod
    def _ensure_device_caps(cls, value: Any) -> Dict[str, Any]:
        if value in (None, ""):
            return {}
        if isinstance(value, dict):
            return value
        raise ValueError("device_caps 必须是对象")

    @field_validator("wait_timeout", "retry_delay", mode="before")
    @classmethod
    def _parse_optional_float(cls, value: Any, info: ValidationInfo) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        try:
            parsed = float(value)
        except (TypeError, ValueError) as exc:
            field_label = info.field_name or "该字段"
            raise ValueError(f"{field_label} 必须是非负数值") from exc
        if parsed < 0:
            field_label = info.field_name or "该字段"
            raise ValueError(f"{field_label} 必须是非负数值")
        return parsed

class AppTicketConfigModel(BaseModel):
    """Schema definition for validating app ticket configuration payloads."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True, str_strip_whitespace=True)

    server_url: str = Field(
        ...,
        description="Appium server URL",
        validation_alias=AliasChoices("server_url", "serverUrl"),
    )
    keyword: Optional[str] = None
    users: List[str] = Field(default_factory=list)
    city: Optional[str] = None
    date: Optional[str] = None
    price: Optional[str] = None
    price_index: Optional[int] = Field(
        default=None,
        ge=0,
        validation_alias=AliasChoices("price_index", "priceIndex"),
    )
    session_index: Optional[int] = Field(
        default=0,
        ge=0,
        validation_alias=AliasChoices("session_index", "sessionIndex"),
    )
    ticket_quantity: Optional[int] = Field(
        default=None,
        ge=1,
        le=6,
        validation_alias=AliasChoices("ticket_quantity", "ticketQuantity"),
    )
    if_commit_order: bool = Field(
        default=True,
        validation_alias=AliasChoices("if_commit_order", "ifCommitOrder"),
    )
    device_caps: Dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("device_caps", "deviceCaps"),
    )
    wait_timeout: float = Field(
        default=2.0,
        ge=0.0,
        validation_alias=AliasChoices("wait_timeout", "waitTimeout"),
    )
    retry_delay: float = Field(
        default=2.0,
        ge=0.0,
        validation_alias=AliasChoices("retry_delay", "retryDelay"),
    )
    warmup_sec: Optional[int] = Field(
        default=120,
        ge=0,
        validation_alias=AliasChoices("warmup_sec", "warmupSec"),
    )
    devices: List[DeviceOverrideModel] = Field(default_factory=list)

    @field_validator("server_url", mode="before")
    @classmethod
    def _ensure_server_url(cls, value: Any) -> str:
        if value is None:
            raise ValueError("server_url 不能为空")
        text = str(value).strip()
        if not text:
            raise ValueError("server_url 不能为空")
        return text

    @field_validator("server_url", mode="after")
    @classmethod
    def _normalise_server_url(cls, value: str) -> str:
        normalised = _normalise_server_url(value)
        if not normalised:
            raise ValueError("server_url 不能为空")
        return normalised

    @field_validator("keyword", "city", "date", "price", mode="before")
    @classmethod
    def _strip_optional_strings(cls, value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("users", mode="before")
    @classmethod
    def _normalise_users(cls, value: Any) -> List[str]:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return _clean_users([value])
        if isinstance(value, Iterable):
            return _clean_users(value)
        raise ValueError("users 必须是字符串数组")

    @field_validator("price_index", "session_index", mode="before")
    @classmethod
    def _parse_index(cls, value: Any) -> Optional[int]:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("索引必须是非负整数") from exc
        if parsed < 0:
            raise ValueError("索引必须是非负整数")
        return parsed

    @field_validator("ticket_quantity", mode="before")
    @classmethod
    def _parse_ticket_quantity(cls, value: Any) -> Optional[int]:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("购票数量必须是1-6之间的整数") from exc
        if parsed < 1 or parsed > 6:
            raise ValueError("购票数量必须是1-6之间的整数")
        return parsed

    @field_validator("device_caps", mode="before")
    @classmethod
    def _ensure_device_caps(cls, value: Any) -> Dict[str, Any]:
        if value in (None, ""):
            return {}
        if isinstance(value, dict):
            return value
        raise ValueError("device_caps 必须是对象")

    @field_validator("if_commit_order", mode="before")
    @classmethod
    def _parse_if_commit_order(cls, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return True
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            lowered = value.strip().lower()
            if not lowered:
                return True
            if lowered in {"true", "1", "yes", "y", "是"}:
                return True
            if lowered in {"false", "0", "no", "n", "否"}:
                return False
        raise ValueError("if_commit_order 只能是布尔值")

    @field_validator("wait_timeout", "retry_delay", mode="before")
    @classmethod
    def _parse_positive_float(cls, value: Any, info: ValidationInfo) -> float:
        field_name: str = info.field_name or ""
        field = cls.model_fields.get(field_name)
        default_value = field.default if field and field.default is not None else 0.0
        if value is None:
            return default_value
        if isinstance(value, str) and not value.strip():
            return default_value
        try:
            parsed = float(value)
        except (TypeError, ValueError) as exc:
            field_label = info.field_name or "该字段"
            raise ValueError(f"{field_label} 必须是非负数值") from exc
        if parsed < 0:
            field_label = info.field_name or "该字段"
            raise ValueError(f"{field_label} 必须是非负数值")
        return parsed


@dataclass
class AdbDeviceInfo:
    """Represents a device entry reported by ``adb devices -l``."""

    serial: str
    status: str
    properties: Dict[str, str] = field(default_factory=dict)

    @property
    def is_ready(self) -> bool:
        """Whether the device is ready for automation (``device`` status)."""

        return self.status.lower() == "device"

    def describe(self) -> str:
        """Return a human friendly label combining serial and known properties."""

        extras: List[str] = []
        model = self.properties.get("model")
        if model:
            extras.append(model)

        device_name = self.properties.get("device")
        if device_name and device_name != model:
            extras.append(device_name)

        transport_id = self.properties.get("transport_id")
        if transport_id:
            extras.append(f"transport:{transport_id}")

        if extras:
            return f"{self.serial} ({', '.join(extras)})"
        return self.serial


def parse_adb_devices(raw_output: str) -> List[AdbDeviceInfo]:
    """Parse the output from ``adb devices -l`` into structured entries.

    Parameters
    ----------
    raw_output:
        The stdout text returned by executing ``adb devices`` or ``adb devices -l``.

    Returns
    -------
    List[AdbDeviceInfo]
        All device entries discovered in the output. Lines without a recognised
        device description are ignored.
    """

    devices: List[AdbDeviceInfo] = []
    if not raw_output:
        return devices

    for line in raw_output.splitlines():
        current = line.strip()
        if not current:
            continue
        if current.startswith("List of devices attached"):
            continue
        if current.startswith("*"):
            # 忽略 adb server 的提示信息
            continue

        parts = current.split()
        if not parts:
            continue

        serial = parts[0]
        status = parts[1] if len(parts) > 1 else "unknown"
        properties: Dict[str, str] = {}

        for token in parts[2:]:
            if ":" not in token:
                continue
            key, value = token.split(":", 1)
            if key and value:
                properties[key] = value

        devices.append(AdbDeviceInfo(serial=serial, status=status, properties=properties))

    return devices


@dataclass
class AppTicketConfig:
    """Runtime configuration for the Appium ticket grabbing flow."""

    server_url: str
    keyword: Optional[str] = None
    users: List[str] = field(default_factory=list)
    city: Optional[str] = None
    date: Optional[str] = None
    price: Optional[str] = None
    price_index: Optional[int] = None
    session_index: Optional[int] = None
    ticket_quantity: Optional[int] = None
    if_commit_order: bool = True
    device_caps: Dict[str, Any] = field(default_factory=dict)
    wait_timeout: float = 2.0
    retry_delay: float = 2.0
    warmup_sec: Optional[int] = 120

    def __post_init__(self) -> None:
        self.server_url = _normalise_server_url(self.server_url)
        self.users = _clean_users(self.users)
        if self.price_index is not None and self.price_index < 0:
            raise ValueError("price_index 不能为负数")

        if not self.server_url:
            raise ValueError("server_url 不能为空")

    @property
    def endpoint(self) -> str:
        """Return the Appium server endpoint (http/https)."""

        return self.server_url

    @property
    def desired_capabilities(self) -> Dict[str, Any]:
        """Build the desired capabilities for Appium based on config values."""

        caps: Dict[str, Any] = {
            "platformName": "Android",
            "deviceName": self.device_caps.get("deviceName", "AndroidDevice"),
            "appPackage": "cn.damai",
            "appActivity": ".launcher.splash.SplashMainActivity",
            "unicodeKeyboard": True,
            "resetKeyboard": True,
            "noReset": True,
            "newCommandTimeout": 6000,
            "automationName": self.device_caps.get("automationName", "UiAutomator2"),
            "ignoreHiddenApiPolicyError": True,
            "disableWindowAnimation": True,
        }

        # 使用用户自定义的 capability 覆盖默认值
        caps.update(self.device_caps)
        return caps

    @classmethod
    def from_mapping(cls, payload: Dict[str, Any]) -> "AppTicketConfig":
        """Create configuration from a raw mapping."""

        configs = cls.from_mapping_multi(payload)
        if not configs:
            raise ConfigValidationError(["未能解析到有效配置"], message="配置为空")
        return configs[0]

    @classmethod
    def from_mapping_multi(cls, payload: Dict[str, Any]) -> List["AppTicketConfig"]:
        """Create one or more configurations from a raw mapping with optional overrides."""

        try:
            model = AppTicketConfigModel.model_validate(payload or {})
        except ValidationError as exc:
            raise ConfigValidationError(_format_validation_errors(exc)) from exc

        base_dump = model.model_dump()
        device_overrides = base_dump.pop("devices", [])
        config_field_names = {item.name for item in dataclass_fields(cls)}

        def _build_config(data: Dict[str, Any]) -> "AppTicketConfig":
            filtered = {key: data[key] for key in config_field_names if key in data}
            return cls(**filtered)

        base_dump.pop("devices", None)
        base_config = _build_config(base_dump)
        configs: List[AppTicketConfig] = [base_config]

        for index, override in enumerate(device_overrides, start=1):
            override_payload = dict(base_dump)
            merged_caps = dict(base_dump.get("device_caps", {}))
            merged_caps.update(dict(override.get("device_caps", {}) or {}))
            override_payload["device_caps"] = merged_caps

            for key, value in override.items():
                if key == "device_caps":
                    continue
                if value is not None:
                    override_payload[key] = value

            try:
                validated = AppTicketConfigModel.model_validate(override_payload)
            except ValidationError as exc:
                message = f"第 {index} 个设备配置校验失败"
                raise ConfigValidationError(_format_validation_errors(exc), message=message) from exc

            override_dump = validated.model_dump()
            override_dump.pop("devices", None)
            configs.append(_build_config(override_dump))

        return configs

    @classmethod
    def load(cls, path: Optional[Union[Path, str]] = None) -> "AppTicketConfig":
        """Load configuration from JSON/JSONC file."""

        file_path = _resolve_config_path(path)
        raw_content = file_path.read_text(encoding="utf-8")
        
        # If it's a .json file, parse directly without stripping comments
        data = json.loads(raw_content)
            
        try:
            return cls.from_mapping(data)
        except ConfigValidationError as exc:
            message = f"{file_path.name} 配置校验失败"
            raise ConfigValidationError(exc.errors, message=message) from exc

    @classmethod
    def load_all(cls, path: Optional[Union[Path, str]] = None) -> List["AppTicketConfig"]:
        """Load all device configurations from JSON/JSONC file, including overrides."""

        file_path = _resolve_config_path(path)
        raw_content = file_path.read_text(encoding="utf-8")
        
        # If it's a .json file, parse directly without stripping comments
        data = json.loads(raw_content)
        try:
            configs = cls.from_mapping_multi(data)
        except ConfigValidationError as exc:
            message = f"{file_path.name} 配置校验失败"
            raise ConfigValidationError(exc.errors, message=message) from exc
        return configs


def _resolve_config_path(path: Optional[Union[Path, str]]) -> Path:
    if path is not None:
        resolved = Path(path)
        if not resolved.exists():
            raise FileNotFoundError(f"未找到配置文件: {resolved.as_posix()}")
        return resolved

    base_dir = Path(__file__).resolve().parent
    for name in _DEFAULT_CONFIG_FILENAMES:
        candidate = base_dir / name
        if candidate.exists():
            return candidate

    raise FileNotFoundError(
        "未找到任何配置文件，请在 damai_appium 目录下提供 config.jsonc 或 config.json"
    )
