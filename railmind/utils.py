import re
import json
import time
import functools
import asyncio
from typing import Callable, Tuple, Dict, Any

from railmind.operators.logger import get_logger
from railmind.api.enum.think_model import THINK_MODELS

BLUE = "\033[94m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"

def is_think_model(model_name: str) -> bool:
    return any(model_name.lower() == m.value for m in THINK_MODELS)

def parse_think_content(content: str) -> Tuple[str, Dict[str, Any]]:
    think_match = re.search(r"<think>\s*(.*?)\s*</think>", content, re.DOTALL)
    think_text = think_match.group(1).strip() if think_match else ""
    context_part = content.split("</think>")[-1].strip()
    return think_text, context_part

def log_execution_time(
    func_name: str = None,
    logger_name: str = None,
    log_state: bool = True
):
    """
    装饰器：记录函数执行前后状态与耗时，并带彩色日志输出。
    
    参数：
        func_name: 日志显示名称（默认=函数名）
        logger_name: logger 名称（默认=函数名）
        log_state: 是否打印执行结束后的 state（默认 True）
    """

    def decorator(func: Callable):
        log = get_logger(logger_name or func_name or func.__name__)
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            display_name = func_name or func.__name__
            log.info(f"{BLUE}[{display_name}] Starting...{RESET}")

            start_time = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                elapsed = time.perf_counter() - start_time
                log.info(f"{RED}[{display_name}] End --> Time: {elapsed:.4f}s{RESET}")
                if log_state:
                    state = kwargs.get("state", None)
                    if state is None and len(args) >= 2:
                        state = args[1]

                    log.info(f"{YELLOW}[{display_name}] Current State:\n{state}{RESET}")

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            display_name = func_name or func.__name__
            log.info(f"{BLUE}[{display_name}] Starting...{RESET}")
            start_time = time.perf_counter()

            try:
                return func(*args, **kwargs)
            finally:
                elapsed = time.perf_counter() - start_time
                log.info(f"{RED}[{display_name}] End --> Time: {elapsed:.4f}s{RESET}")

                if log_state:
                    state = kwargs.get("state", None)
                    if state is None and len(args) >= 2:
                        state = args[1]

                    log.info(f"{YELLOW}[{display_name}] Current State:\n{state}{RESET}")

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator