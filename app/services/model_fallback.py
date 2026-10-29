"""Provider failover rules shared by diagnosis and resume AI operations."""


def candidates(snapshot):
    configured = snapshot.get("model_candidates") or [snapshot["model"]]
    ordered = []
    for model_id in [snapshot["model"], *configured]:
        if isinstance(model_id, str) and (model_id or not ordered) and model_id not in ordered:
            ordered.append(model_id)
    return ordered


def model_unavailable(error):
    """Fail over for unusable model output or provider errors, not account auth/billing."""
    from app.services.model_runtime import provider_error

    error = provider_error(error)
    status = getattr(error, "status_code", None)
    if status in {401, 402}:
        return False
    if isinstance(status, int):
        return status >= 400
    if isinstance(error, (TimeoutError, ConnectionError, OSError)):
        return True
    if isinstance(error, ValueError) or type(error).__name__ == "ValidationError":
        return True
    module = type(error).__module__
    return module.startswith(("httpx", "httpcore")) or type(error).__name__ in {
        "APIConnectionError",
        "APITimeoutError",
    }
