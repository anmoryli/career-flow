"""Bounded diagnosis transport and safe provider exception inspection."""

from urllib.parse import urlsplit

DIAGNOSIS_ATTEMPT_SECONDS = 90
DIAGNOSIS_READ_SECONDS = 45
DIAGNOSIS_FINALIZE_SECONDS = 30
# One orchestrated run (planner + section analysts + writer).
ORCHESTRATOR_SECONDS = 480


def diagnosis_job_seconds(snapshot):
    from app.services.model_fallback import candidates

    return len(candidates(snapshot)) * 2 * DIAGNOSIS_ATTEMPT_SECONDS + DIAGNOSIS_FINALIZE_SECONDS


def provider_error(error):
    """Unwrap SDK errors without exposing messages, payloads, or credentials."""
    # langchain-openai re-raises provider faults as joint classes
    # (OpenAITimeoutError etc.); unwrap them down to the raw SDK/transport
    # error so status codes and timeout names stay inspectable.
    unwrappable = {
        "ModelAPIError",
        "APIConnectionError",
        "APITimeoutError",
        "OpenAIAPIError",
        "OpenAIConnectionError",
        "OpenAITimeoutError",
    }
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        if type(error).__name__ not in unwrappable:
            return error
        cause = error.__cause__
        if cause is None or id(cause) in seen:
            return error
        error = cause
    return error


AI_PROVIDER_BILLING_MESSAGE = "AI 服务暂不可用，请联系管理员处理；你的会员权益不受影响。"


def public_ai_error(message):
    """Keep operator billing details out of member-facing current and historical errors."""
    if message in {
        "模型服务账户余额不足或未开通此模型，请检查服务商账户。",
        "模型服务余额不足，请稍后重试。",
    }:
        return AI_PROVIDER_BILLING_MESSAGE
    return message or ""


def stream_usage_settings(base_url):
    """Token usage for streamed responses.

    Streaming requests only report usage when the client asks for it, and
    SiliconFlow additionally reports cumulative counters inside every chunk
    when `stream_options.continuous_usage_stats` is set. The SiliconFlow entry
    carries the whole `stream_options` object because the OpenAI SDK merges
    `extra_body` over typed parameters at the top level.
    """
    if urlsplit(base_url).hostname in {"api.siliconflow.cn", "api.siliconflow.com"}:
        return {
            "extra_body": {
                "stream_options": {"include_usage": True, "continuous_usage_stats": True}
            }
        }
    return {"stream_usage": True}
