"""Bounded diagnosis transport and safe provider exception inspection."""

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
