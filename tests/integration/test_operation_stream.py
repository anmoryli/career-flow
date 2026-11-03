"""Progress events behind the analysis panel: bus semantics and SSE frames.

The stream is not polled by the browser, so these tests are the only place the
publish/subscribe contract and the wire format are checked together.
"""

import json
from uuid import uuid4

import pytest

from app.extensions import db
from app.models import AIOperation
from app.services import diagnosis, operation_events
from tests.integration.test_career import client_for, make_operation

pytestmark = pytest.mark.integration


def buffered(operation_id, client):
    """Read the replay buffer as-is; no subscriber loop, no blocking."""
    raw_items = client.lrange(operation_events.buffer_key(operation_id), 0, -1)
    return [json.loads(raw) for raw in raw_items]


def drain(operation_id, client, limit=12):
    """Read buffered events without ever blocking on a silent channel."""
    records = []
    for record in operation_events.subscribe(operation_id, client=client, block_seconds=0.2):
        if record is None:
            continue
        records.append(record)
        if len(records) >= limit or record["event"] in operation_events.TERMINAL_EVENTS:
            break
    return records


def test_late_subscriber_replays_the_whole_run(mysql_app, context):
    uid, _, _, diagnostic_id = context
    with mysql_app.app_context():
        item = make_operation(uid, diagnostic_id)
        db.session.commit()
        client = mysql_app.extensions["redis"]
        operation_events.publish(item.id, "stage", {"message": "正在核对"}, client=client)
        operation_events.publish(item.id, "delta", {"text": "结论"}, client=client)
        operation_events.publish(item.id, "done", {"operation_id": item.id}, client=client)
        records = drain(item.id, client)

    assert [record["event"] for record in records] == ["stage", "delta", "done"]
    assert [record["seq"] for record in records] == [1, 2, 3]
    assert records[1]["data"] == {"text": "结论"}


def test_publish_survives_a_broken_redis(mysql_app, context):
    """A dead event bus must never fail an analysis a user already paid for."""
    uid, _, _, diagnostic_id = context
    with mysql_app.app_context():
        item = make_operation(uid, diagnostic_id)
        db.session.commit()

        class Broken:
            def __getattr__(self, name):
                raise ConnectionError("redis down")

        published = operation_events.publish(
            item.id, "stage", {"message": "x"}, client=Broken()
        )
        assert published is False


def test_stream_endpoint_emits_sse_frames(mysql_app, context):
    uid, _, _, diagnostic_id = context
    with mysql_app.app_context():
        item = make_operation(uid, diagnostic_id)
        db.session.commit()
        operation_id = item.id
        client = mysql_app.extensions["redis"]
        operation_events.publish(operation_id, "stage", {"message": "正在核对"}, client=client)
        operation_events.publish(operation_id, "delta", {"text": "结论"}, client=client)
        operation_events.publish(
            operation_id, "done", {"operation_id": operation_id}, client=client
        )

    http, _ = client_for(mysql_app, uid)
    response = http.get(f"/api/operations/{operation_id}/stream")
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/event-stream")
    assert response.headers["Cache-Control"].startswith("no-cache")
    body = response.get_data(as_text=True)
    assert body.startswith("retry: 3000")
    assert "event: stage" in body
    assert 'data: {"message": "正在核对"}' in body
    assert "event: delta" in body
    assert "event: done" in body
    # A terminal event closes the response instead of holding the socket open.
    assert body.rstrip().endswith('data: {"operation_id": ' + str(operation_id) + "}")


def test_stream_and_panel_reject_other_users(mysql_app, context, user_factory):
    uid, _, _, diagnostic_id = context
    with mysql_app.app_context():
        item = make_operation(uid, diagnostic_id)
        db.session.commit()
        operation_id = item.id
    stranger_uid, _ = user_factory()
    stranger, _ = client_for(mysql_app, stranger_uid)
    assert stranger.get(f"/api/operations/{operation_id}/stream").status_code == 404
    assert stranger.get(f"/api/operations/{operation_id}/panel").status_code == 404
    assert stranger.get(f"/api/diagnostics/{diagnostic_id}/chat").status_code == 404


def test_completed_run_streams_a_recap_and_persists_it(mysql_app, context, monkeypatch):
    uid, _, _, diagnostic_id = context
    pieces = ["匹配度 60 分，", "最强项是技能匹配。"]

    def fake_summary(snapshot, result, on_delta):
        for piece in pieces:
            on_delta(piece)
        return 120

    monkeypatch.setattr(
        "app.services.model_provider.summarize_diagnosis", fake_summary
    )
    with mysql_app.app_context():
        item = make_operation(uid, diagnostic_id)
        diagnosis.confirm(uid, item.id)
        diagnosis.run_operation(item.id)
        stored = db.session.get(AIOperation, item.id)
        assert stored.state == "succeeded"
        # The recap is persisted so a reload rebuilds the conversation.
        assert stored.note == "".join(pieces)
        assert stored.tokens == 1100 + 120
        records = drain(item.id, mysql_app.extensions["redis"])

    assert [record["event"] for record in records] == [
        "stage",
        "result",
        "delta",
        "delta",
        "done",
    ]
    streamed = "".join(record["data"]["text"] for record in records if record["event"] == "delta")
    assert streamed == "".join(pieces)


def test_failed_run_announces_a_terminal_failure(mysql_app, context, monkeypatch):
    uid, _, _, diagnostic_id = context

    def broken(snapshot):
        raise TimeoutError("provider timeout")

    with mysql_app.app_context():
        monkeypatch.setitem(mysql_app.extensions, "diagnosis_provider", broken)
        item = make_operation(uid, diagnostic_id)
        diagnosis.confirm(uid, item.id)
        diagnosis.run_operation(item.id)
        stored = db.session.get(AIOperation, item.id)
        assert stored.state == "failed"
        records = drain(item.id, mysql_app.extensions["redis"])

    assert records[0]["event"] == "stage"
    assert records[-1]["event"] == "failed"
    assert "超时" in records[-1]["data"]["message"]


def test_recap_failure_keeps_the_analysis(mysql_app, context, monkeypatch):
    """The recap is a bonus: losing it must not cost the finished analysis."""
    uid, _, _, diagnostic_id = context

    def broken_summary(snapshot, result, on_delta):
        on_delta("半句话")
        raise RuntimeError("summary provider down")

    monkeypatch.setattr(
        "app.services.model_provider.summarize_diagnosis", broken_summary
    )
    with mysql_app.app_context():
        item = make_operation(uid, diagnostic_id)
        diagnosis.confirm(uid, item.id)
        diagnosis.run_operation(item.id)
        stored = db.session.get(AIOperation, item.id)
        assert stored.state == "succeeded"
        assert stored.note == ""
        assert stored.tokens == 1100
        records = drain(item.id, mysql_app.extensions["redis"])

    events = [record["event"] for record in records]
    assert "delta_reset" in events
    assert events[-1] == "done"


def test_metering_failure_keeps_the_recap_and_finishes(mysql_app, context, monkeypatch):
    """A lock conflict on the ledger must not swallow the recap or `done`."""
    uid, _, _, diagnostic_id = context

    def fake_summary(snapshot, result, on_delta):
        on_delta("匹配度 60 分。")
        return 120

    def broken_metering(item, calls, revision):
        raise RuntimeError("deadlock found")

    monkeypatch.setattr("app.services.model_provider.summarize_diagnosis", fake_summary)
    monkeypatch.setattr("app.services.product.store_call_usage", broken_metering)
    with mysql_app.app_context():
        item = make_operation(uid, diagnostic_id)
        diagnosis.confirm(uid, item.id)
        diagnosis.run_operation(item.id)
        stored = db.session.get(AIOperation, item.id)
        assert stored.state == "succeeded"
        assert stored.note == "匹配度 60 分。"
        records = drain(item.id, mysql_app.extensions["redis"])

    assert [record["event"] for record in records][-2:] == ["delta", "done"]


def test_confirming_an_analysis_announces_the_wait(mysql_app, context):
    """The queue notice is published first so the panel never steps backwards."""
    uid, _, _, diagnostic_id = context
    http, csrf = client_for(mysql_app, uid)
    response = http.post(
        f"/api/diagnostics/{diagnostic_id}/start",
        json={"kind": "analysis", "request_key": str(uuid4())},
        headers=csrf,
    )
    assert response.status_code == 200
    operation_id = response.get_json()["id"]
    with mysql_app.app_context():
        records = buffered(operation_id, mysql_app.extensions["redis"])
        diagnosis.cancel(uid, operation_id)

    assert records[0]["event"] == "stage"
    assert "排队" in records[0]["data"]["message"]
