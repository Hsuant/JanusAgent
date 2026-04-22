"""通用工具函数。

提供工具库中常用的辅助功能。
"""

import asyncio
import logging
import time
from functools import wraps
from typing import Any, Callable, TypeVar

from tools.exceptions import TimeoutError

# 配置日志
logger = logging.getLogger(__name__)

# 泛型类型变量
F = TypeVar("F", bound=Callable[..., Any])


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,),
) -> Callable[[F], F]:
    """重试装饰器。

    在函数抛出指定异常时自动重试，支持指数退避。

    Args:
        max_attempts: 最大尝试次数。
        delay: 初始延迟时间（秒）。
        backoff: 延迟倍增因子。
        exceptions: 需要重试的异常类型元组。

    Returns:
        Callable: 装饰后的函数。
    """
    def decorator(func: F) -> F:
        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            current_delay = delay
            last_exception = None

            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        logger.debug(
                            "函数 %s 第 %d 次尝试失败: %s，%s 秒后重试",
                            func.__name__,
                            attempt + 1,
                            e,
                            current_delay,
                        )
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff

            raise last_exception  # type: ignore

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            current_delay = delay
            last_exception = None

            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        logger.debug(
                            "函数 %s 第 %d 次尝试失败: %s，%s 秒后重试",
                            func.__name__,
                            attempt + 1,
                            e,
                            current_delay,
                        )
                        time.sleep(current_delay)
                        current_delay *= backoff

            raise last_exception  # type: ignore

        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        return sync_wrapper  # type: ignore

    return decorator


def timeout(seconds: float) -> Callable[[F], F]:
    """超时装饰器。

    限制函数的执行时间，超时则抛出 TimeoutError。

    Args:
        seconds: 超时时间（秒）。

    Returns:
        Callable: 装饰后的函数。
    """
    def decorator(func: F) -> F:
        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=seconds,
                )
            except asyncio.TimeoutError:
                raise TimeoutError(
                    f"函数 {func.__name__} 执行超时（{seconds} 秒）"
                ) from None

        return async_wrapper  # type: ignore

    return decorator


def ensure_dir(path: str) -> None:
    """确保目录存在，不存在则创建。

    Args:
        path: 目录路径。
    """
    import os
    os.makedirs(path, exist_ok=True)


def truncate_string(text: str, max_length: int = 1000, suffix: str = "...") -> str:
    """截断字符串到指定长度。

    Args:
        text: 原始字符串。
        max_length: 最大长度。
        suffix: 截断后追加的后缀。

    Returns:
        str: 截断后的字符串。
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def sanitize_filename(filename: str) -> str:
    """清理文件名，移除非法字符。

    Args:
        filename: 原始文件名。

    Returns:
        str: 清理后的文件名。
    """
    import re
    # 替换非法字符为下划线
    illegal_chars = r'[<>:"/\\|?*]'
    return re.sub(illegal_chars, "_", filename)