import os
import threading
from typing import Any, Type, TypeVar, Optional, cast

DEFAULT_API_URL = "https://prompt-pilot.cn-beijing.volces.com"

T = TypeVar("T", bound="Config")


class Config:
    _instance: Optional["Config"] = None
    _lock = threading.Lock()

    api_key: Optional[str]
    verbose: bool
    api_url: str
    ssl_verify: bool
    initialized: bool
    local_debug: bool = False

    def __new__(cls: Type[T], *args: Any, **kwargs: Any) -> T:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    # 不在这里调用__init__
                    cls._instance = instance
        return cast(T, cls._instance)

    def __init__(
        self,
        api_key: Optional[str] = None,
        verbose: Optional[bool] = None,
        api_url: Optional[str] = None,
        disable_ssl_verify: Optional[bool] = None,
        sample_rate: Optional[float] = None,
        workspace_id: Optional[str] = None,
    ) -> None:
        # 避免重复初始化
        if hasattr(self, "initialized") and self.initialized:
            return

        self.api_key = api_key or os.environ.get("AGENTPILOT_API_KEY")
        self.verbose = verbose if verbose is not None else os.getenv("AGENTPILOT_VERBOSE") is not None
        self.api_url = api_url or os.getenv("AGENTPILOT_API_URL") or DEFAULT_API_URL
        self.ssl_verify = not (
            disable_ssl_verify
            if disable_ssl_verify is not None
            else (True if os.environ.get("DISABLE_SSL_VERIFY", "false").lower() == "true" else False)
        )
        if self.api_url.startswith("http://localhost"):
            self.local_debug = True
        self.sample_rate = sample_rate if sample_rate is not None else os.getenv("AGENTPILOT_SAMPLE_RATE")
        self.workspace_id = workspace_id if workspace_id is not None else os.getenv("AGENTPILOT_WORKSPACE_ID")
        self.initialized = True

    def __repr__(self) -> str:
        return (
            f"Config(api_key={self.api_key!r}, verbose={self.verbose!r}, "
            f"api_url={self.api_url!r}, ssl_verify={self.ssl_verify!r})"
        )


config = Config()


def get_config() -> Config:
    return config


def set_config(
    api_key: Optional[str] = None,
    verbose: Optional[bool] = None,
    api_url: Optional[str] = None,
    disable_ssl_verify: Optional[bool] = None,
) -> None:
    config.api_key = api_key or config.api_key
    config.verbose = verbose if verbose is not None else config.verbose
    config.api_url = api_url or config.api_url
    if disable_ssl_verify is not None:
        config.ssl_verify = not disable_ssl_verify
