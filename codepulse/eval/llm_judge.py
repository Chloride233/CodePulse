"""LLM judge 调用工具 — 重试、降级、日志。"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)


def call_llm_with_retry(
    model: str,
    messages: list[dict[str, str]],
    *,
    max_retries: int = 3,
    base_delay: float = 1.0,
    **kwargs: object,
) -> str | None:
    """调用 LiteLLM completion，带指数退避重试。

    Args:
        model: LiteLLM 模型标识。
        messages: 对话消息列表。
        max_retries: 最大重试次数（默认 3）。
        base_delay: 初始退避延迟秒数（默认 1s）。
        kwargs: 传给 litellm.completion 的额外参数。

    Returns:
        响应文本，全部失败时返回 None。
    """
    import litellm

    for attempt in range(max_retries + 1):
        try:
            response = litellm.completion(
                model=model,
                messages=messages,
                **kwargs,
            )
            content = response.choices[0].message.content or ""
            if content:
                return content
            logger.warning("LLM 返回空内容 (attempt %d)", attempt)
        except Exception:
            if attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    "LLM 调用失败 (attempt %d/%d)，%.1fs 后重试",
                    attempt + 1, max_retries + 1, delay,
                    exc_info=True,
                )
                time.sleep(delay)
            else:
                logger.exception("LLM 调用全部失败 (%d 次)", max_retries + 1)
    return None
