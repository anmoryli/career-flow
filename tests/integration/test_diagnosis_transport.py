from datetime import timedelta

import pytest

from app.extensions import db
from app.models import AIOperation, utcnow
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
