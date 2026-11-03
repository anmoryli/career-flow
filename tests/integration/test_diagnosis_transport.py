from datetime import timedelta

import pytest
from sqlalchemy import select

from app.extensions import db
from app.models import AIOperation, ModelCallUsage, utcnow
from app.services import diagnosis
from tests.integration import test_career
from tests.integration.test_career import make_operation, valid_output
from tests.test_model_runtime import wrapped_timeout

pytestmark = pytest.mark.integration
context = test_career.context


def test_wrapped_timeout_retries_primary_then_succeeds_on_backup(mysql_app, context, caplog):
    uid, _, _, did = context
    calls = []

    def provider(snapshot):
        calls.append(snapshot["model"])
        if snapshot["model"] == "primary":
            raise wrapped_timeout()
        return valid_output(snapshot), 300

    mysql_app.extensions["diagnosis_provider"] = provider
    with mysql_app.app_context():
        op = make_operation(uid, did)
        oid = op.id
        diagnosis.confirm(uid, oid)
        op.input_snapshot = op.input_snapshot | {
            "model": "primary",
            "model_candidates": ["primary", "backup", "last"],
        }
        db.session.commit()
        diagnosis.run_operation(oid)
        op = db.session.get(AIOperation, oid)
        assert op.state == "succeeded" and op.attempts == 3
        assert op.tokens == 300 and op.charged == 0
        assert calls == ["primary", "primary", "backup"]
        assert "cause=ReadTimeout" in caplog.text
        assert "elapsed_seconds=" in caplog.text
        assert "must-not-leak-secret" not in caplog.text


def test_all_wrapped_timeouts_finish_with_clear_failure(mysql_app, context):
    uid, _, _, did = context

    def provider(snapshot):
        raise wrapped_timeout()

    mysql_app.extensions["diagnosis_provider"] = provider
    with mysql_app.app_context():
        op = make_operation(uid, did)
        diagnosis.confirm(uid, op.id)
        op.input_snapshot = op.input_snapshot | {
            "model": "primary",
            "model_candidates": ["primary", "backup", "last"],
        }
        db.session.commit()
        diagnosis.run_operation(op.id)
        assert op.state == "failed" and op.attempts == 6
        assert op.charged == 0
        assert "连接模型服务超时" in op.error
        assert "must-not-leak-secret" not in op.error


def test_recovery_respects_configured_fallback_time_budget(mysql_app, context):
    uid, _, _, did = context
    with mysql_app.app_context():
        op = make_operation(uid, did)
        diagnosis.confirm(uid, op.id)
        op.state = "running"
        op.started_at = utcnow() - timedelta(minutes=6)
        op.input_snapshot = op.input_snapshot | {
            "model": "primary",
            "model_candidates": ["primary", "backup", "last"],
        }
        db.session.commit()
        diagnosis.recover_stale_tasks()
        assert op.state == "running"
        op.started_at = utcnow() - timedelta(minutes=11)
        db.session.commit()
        diagnosis.recover_stale_tasks()
        assert op.state == "failed" and op.charged == 0


def test_agent_orchestrator_success_records_graph_calls(mysql_app, context, monkeypatch):
    uid, _, _, did = context
    mysql_app.config["DIAGNOSIS_AGENT_ENABLED"] = True
    agent_calls = [
        {"total": 400, "input": 320, "output": 80, "outcome": "returned"},
        {"total": None, "input": None, "output": None, "outcome": "provider_error"},
        {"total": 100, "input": 60, "output": 40, "outcome": "returned"},
    ]

    def fake_agent(snapshot):
        return valid_output(snapshot), agent_calls, 500

    monkeypatch.setattr(
        "app.services.agent_orchestrator.run_diagnosis_agent", fake_agent
    )
    with mysql_app.app_context():
        op = make_operation(uid, did)
        diagnosis.confirm(uid, op.id)
        # The shared context fixture installs a diagnosis_provider for quote/
        # confirm; the orchestrator branch requires provider-free testing.
        mysql_app.extensions.pop("diagnosis_provider", None)
        db.session.commit()
        diagnosis.run_operation(op.id)
        op = db.session.get(AIOperation, op.id)
        assert op.state == "succeeded" and op.tokens == 500 and op.attempts == 3
        assert op.charged == 0
        calls = db.session.scalars(
            select(ModelCallUsage)
            .where(ModelCallUsage.operation_id == op.id)
            .order_by(ModelCallUsage.attempt)
        ).all()
        assert [call.attempt for call in calls] == [1, 2, 3]
        assert calls[1].outcome == "provider_error" and calls[1].total_tokens is None


def test_agent_orchestrator_failure_degrades_to_single_shot(
    mysql_app, context, monkeypatch
):
    uid, _, _, did = context
    mysql_app.config["DIAGNOSIS_AGENT_ENABLED"] = True

    def broken_agent(snapshot):
        raise RuntimeError("编排失败")

    def fake_generate(snapshot):
        return valid_output(snapshot), 300

    monkeypatch.setattr(
        "app.services.agent_orchestrator.run_diagnosis_agent", broken_agent
    )
    monkeypatch.setattr("app.services.model_provider.generate", fake_generate)
    with mysql_app.app_context():
        op = make_operation(uid, did)
        diagnosis.confirm(uid, op.id)
        # Same as above: remove the fixture provider so the orchestrator
        # branch is exercised and the degrade path reaches fake_generate.
        mysql_app.extensions.pop("diagnosis_provider", None)
        db.session.commit()
        diagnosis.run_operation(op.id)
        op = db.session.get(AIOperation, op.id)
        assert op.state == "succeeded" and op.tokens == 300 and op.attempts == 3
        calls = db.session.scalars(
            select(ModelCallUsage)
            .where(ModelCallUsage.operation_id == op.id)
            .order_by(ModelCallUsage.attempt)
        ).all()
        assert [call.outcome for call in calls] == [
            "provider_error",
            "provider_error",
            "returned",
        ]
