"""Operation progress events: Redis pub/sub with a short replay buffer.

The worker publishes from a job subprocess; browsers read the same events
through a Server-Sent Events endpoint in a web process. Redis is the only
shared bus, so any number of web processes can serve one stream and a page
reload simply re-attaches.

Each event carries a monotonically increasing sequence number. A subscriber
replays the buffer first — the browser usually connects after the worker has
already published its opening stage — then follows live messages and drops
anything at or below the highest sequence it has already delivered, so the
replay/live seam never duplicates an event.

Redis is strictly best-effort here: MySQL holds the authoritative operation
state. A publish failure must never fail the task, and a subscriber timeout
only costs a heartbeat.
"""

import json

# Buffered events are only interesting while the panel is open; the operation
# row itself expires much later.
BUFFER_TTL = 900
BUFFER_MAX = 240
_HEARTBEAT_SECONDS = 15
# Ending the stream is the client's cue to reload authoritative state. The
# failure event is named "failed", not "error": EventSource reserves "error"
# for transport problems, so a custom "error" event is indistinguishable from
# a dropped connection in the browser.
TERMINAL_EVENTS = frozenset({"done", "failed"})


def channel(operation_id):
    return f"careerflow:operation-event:{operation_id}"


def buffer_key(operation_id):
    return f"careerflow:operation-buffer:{operation_id}"


def sequence_key(operation_id):
    return f"careerflow:operation-seq:{operation_id}"


def publish(operation_id, event, data=None, client=None):
    """Append one event to the replay buffer and fan it out to subscribers.

    Never raises: a broken Redis must not take down a paid analysis task.
    """
    try:
        client = client or _client()
        sequence = int(client.incr(sequence_key(operation_id)))
        payload = json.dumps(
            {"seq": sequence, "event": event, "data": data or {}},
            ensure_ascii=False,
        )
        pipe = client.pipeline()
        pipe.rpush(buffer_key(operation_id), payload)
        pipe.ltrim(buffer_key(operation_id), -BUFFER_MAX, -1)
        pipe.expire(buffer_key(operation_id), BUFFER_TTL)
        pipe.expire(sequence_key(operation_id), BUFFER_TTL)
        pipe.publish(channel(operation_id), payload)
        pipe.execute()
        return True
    except Exception:
        from flask import current_app

        try:
            current_app.logger.warning("operation_event_publish_failed event=%s", event)
        except Exception:
            pass
        return False


def subscribe(operation_id, client=None, block_seconds=_HEARTBEAT_SECONDS):
    """Yield events for one operation, and None for every heartbeat slot.

    Stops after a terminal event. The caller owns the client lifetime when it
    passes one in; otherwise a dedicated streaming connection is created and
    closed here, because the shared app client has a 2 second socket timeout
    that would cut every blocking read short.
    """
    owned = client is None
    connection = client or streaming_client()
    pubsub = None
    try:
        delivered = 0
        for raw in connection.lrange(buffer_key(operation_id), 0, -1):
            record = _decode(raw)
            if record is None or record["seq"] <= delivered:
                continue
            delivered = record["seq"]
            yield record
            if record["event"] in TERMINAL_EVENTS:
                return
        pubsub = connection.pubsub(ignore_subscribe_messages=True)
        pubsub.subscribe(channel(operation_id))
        while True:
            message = pubsub.get_message(timeout=block_seconds)
            if message is None:
                yield None
                continue
            record = _decode(message.get("data"))
            if record is None or record["seq"] <= delivered:
                continue
            delivered = record["seq"]
            yield record
            if record["event"] in TERMINAL_EVENTS:
                return
    finally:
        if pubsub is not None:
            try:
                pubsub.close()
            except Exception:
                pass
        if owned:
            try:
                connection.close()
            except Exception:
                pass


def streaming_client():
    """A connection tuned for long blocking reads, unlike the shared client."""
    from flask import current_app
    from redis import Redis

    return Redis.from_url(
        current_app.config["REDIS_URL"],
        socket_connect_timeout=2,
        # Blocking pub/sub reads must outlive the request socket timeout.
        socket_timeout=None,
        health_check_interval=0,
        decode_responses=True,
    )


def _decode(raw):
    if raw is None:
        return None
    try:
        record = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(record, dict) or "seq" not in record or "event" not in record:
        return None
    record.setdefault("data", {})
    return record


def _client():
    from flask import current_app

    return current_app.extensions["redis"]
