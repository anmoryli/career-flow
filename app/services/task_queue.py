"""Redis Streams task queue: the only dispatch path for background jobs.

MySQL keeps the authoritative operation state; Redis only carries dispatch
messages. Every enqueue is idempotent per task id, and a message is
acknowledged only after its job process exits, so a crashed task is
re-delivered to the next worker and the state checks inside each job body
make redelivery safe.
"""

import os

STREAM = "careerflow:tasks"
GROUP = "workers"
DEDUP_TTL = 3600
RESULT_TTL = 600
# Kinds understood by the worker; each maps to a job body in app.jobs.
KINDS = {"diagnosis", "resume-ai", "pdf-import", "probe"}


def enqueue(kind, task_id, timeout_seconds):
    """Queue one task. Raises on Redis failure so callers can surface 503."""
    if kind not in KINDS:
        raise ValueError(f"unknown task kind: {kind}")
    client = _client()
    key = dedup_key(kind, task_id)
    # Re-enqueueing an already queued task would double-run it once the
    # first message is claimed; the dedup key keeps one live message per id.
    if not client.set(key, "1", nx=True, ex=DEDUP_TTL):
        return
    try:
        client.xadd(
            STREAM,
            {"kind": kind, "id": str(task_id), "timeout": str(int(timeout_seconds))},
        )
    except Exception:
        client.delete(key)
        raise


def claim(block_ms=5000, consumer="worker", redis_client=None):
    """Read pending-and-new messages for this consumer; returns (id, fields)."""
    client = redis_client or _client()
    ensure_group(client)
    kwargs = {"streams": {STREAM: ">"}, "count": 10, "block": block_ms} if block_ms else {
        "streams": {STREAM: ">"}, "count": 10
    }
    response = client.xreadgroup(GROUP, consumer, **kwargs)
    messages = []
    for _, entries in response or []:
        for message_id, fields in entries:
            messages.append(
                (
                    message_id.decode() if isinstance(message_id, bytes) else message_id,
                    {
                        (key.decode() if isinstance(key, bytes) else key): (
                            value.decode() if isinstance(value, bytes) else value
                        )
                        for key, value in fields.items()
                    },
                )
            )
    return messages


def ack(message_id, redis_client=None):
    client = redis_client or _client()
    client.xack(STREAM, GROUP, message_id)


def reclaim_stale(min_idle_ms=60000, consumer="recovery", redis_client=None):
    """Re-claim messages whose worker died before acknowledging."""
    client = redis_client or _client()
    ensure_group(client)
    _, messages, _ = client.xautoclaim(STREAM, GROUP, consumer, min_idle_ms)
    return messages


def report(kind, task_id, payload, redis_client=None):
    """Store a small job result for verification tooling (short TTL)."""
    import json

    client = redis_client or _client()
    client.set(result_key(kind, task_id), json.dumps(payload), ex=RESULT_TTL)


def result(kind, task_id, redis_client=None):
    import json

    client = redis_client or _client()
    value = client.get(result_key(kind, task_id))
    return json.loads(value) if value else None


def dedup_key(kind, task_id):
    return f"careerflow:task:{kind}:{task_id}"


def result_key(kind, task_id):
    return f"careerflow:task-result:{kind}:{task_id}"


def ensure_group(client):
    try:
        client.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except Exception as error:
        if "BUSYGROUP" not in str(error):
            raise


def _client():
    from flask import current_app

    return current_app.extensions["redis"]


def redis_url():
    return os.getenv("REDIS_URL", "redis://127.0.0.1:6390/0")
