"""Bounded diagnosis transport and safe provider exception inspection."""

from urllib.parse import urlsplit

DIAGNOSIS_ATTEMPT_SECONDS = 90
DIAGNOSIS_READ_SECONDS = 45
DIAGNOSIS_FINALIZE_SECONDS = 30


def diagnosis_job_seconds(snapshot):
    from app.services.model_fallback import candidates

    return len(candidates(snapshot)) * 2 * DIAGNOSIS_ATTEMPT_SECONDS + DIAGNOSIS_FINALIZE_SECONDS


def provider_error(error):
    """Unwrap SDK errors without exposing messages, payloads, or credentials."""
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        if type(error).__name__ not in {"ModelAPIError", "APIConnectionError", "APITimeoutError"}:
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
    """SiliconFlow reports cumulative counters in every streamed chunk."""
    if urlsplit(base_url).hostname in {"api.siliconflow.cn", "api.siliconflow.com"}:
        return {"openai_continuous_usage_stats": True}
    return {}
