from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock, local
from uuid import uuid4

import pytest
from flask import request
from sqlalchemy import func, select

from app.extensions import db
from app.models import AIOperation, CreditEntry
from app.services import diagnosis
from tests.integration.test_career import client_for, make_operation, valid_output

pytestmark = pytest.mark.integration


def test_concurrent_http_create_with_preexisting_auth_snapshot(mysql_app, context):
    clients = [client_for(mysql_app, context[0]) for _ in range(2)]
    barrier = Barrier(2)

    def synchronize():
        if request.path == "/api/resumes":
            barrier.wait(timeout=10)

    mysql_app.before_request_funcs[None].append(synchronize)
    payload = {
        "request_key": str(uuid4()),
        "title": "并发同请求",
        "document": {"summary": "相同填写"},
    }
    try:

        def post(pair):
            client, headers = pair
            response = client.post("/api/resumes", json=payload, headers=headers)
            return response.status_code, response.json

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(post, clients))
        assert [item[0] for item in results] == [201, 201]
        assert results[0][1]["id"] == results[1][1]["id"]
    finally:
        mysql_app.before_request_funcs[None].remove(synchronize)


def test_two_confirmations_for_same_diagnostic_only_freeze_once(mysql_app, context, monkeypatch):
    uid, _, _, did = context
    with mysql_app.app_context():
        ids = [make_operation(uid, did).id for _ in range(2)]
    clients = [client_for(mysql_app, uid) for _ in range(2)]
    barrier = Barrier(2)

    def synchronize():
        if request.path.endswith("/confirm"):
            barrier.wait(timeout=10)

    mysql_app.before_request_funcs[None].append(synchronize)
    monkeypatch.setattr("app.web.diagnosis.Queue.enqueue", lambda *a, **k: None)
    try:

        def post(index):
            client, headers = clients[index]
            return client.post(
                f"/api/operations/{ids[index]}/confirm", json={}, headers=headers
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(post, range(2))) == [200, 409]
        with mysql_app.app_context():
            entries = db.session.scalars(
                select(CreditEntry).where(CreditEntry.operation_id.in_(ids))
            ).all()
            assert entries == []
            for oid in ids:
                diagnosis.cancel(uid, oid)
    finally:
        mysql_app.before_request_funcs[None].remove(synchronize)


def test_concurrent_workers_cannot_duplicate_provider_or_settlement(
    mysql_app, context, monkeypatch
):
    uid, _, _, did = context
    with mysql_app.app_context():
        oid = make_operation(uid, did).id
        diagnosis.confirm(uid, oid)
    barrier = Barrier(2)
    thread = local()
    original_lock = diagnosis.owner_lock
    calls = []
    call_lock = Lock()

    def synchronized_lock(user_id):
        if not getattr(thread, "entered", False):
            thread.entered = True
            barrier.wait(timeout=10)
        original_lock(user_id)

    def provider(snapshot):
        with call_lock:
            calls.append(1)
        return valid_output(snapshot), 1000

    monkeypatch.setattr(diagnosis, "owner_lock", synchronized_lock)
    mysql_app.extensions["diagnosis_provider"] = provider

    def run(_):
        with mysql_app.app_context():
            diagnosis.run_operation(oid)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run, range(2)))
    assert len(calls) == 1
    with mysql_app.app_context():
        assert db.session.get(AIOperation, oid).state == "succeeded"
        assert (
            db.session.scalar(
                select(func.count())
                .select_from(CreditEntry)
                .where(CreditEntry.operation_id == oid)
            )
            == 0
        )
