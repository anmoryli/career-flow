import pytest
from pydantic_ai.exceptions import ModelHTTPError
from sqlalchemy import select

from app.extensions import db
from app.models import CreditAccount, CreditEntry, Membership
from app.services import diagnosis
from tests.integration import test_career
from tests.integration.test_career import client_for, make_operation

context = test_career.context
pytestmark = pytest.mark.integration


def test_member_can_analyze_without_points_and_provider_failure_preserves_membership(
    mysql_app, context
):
    uid, _, _, did = context

    def provider(snapshot):
        raise ModelHTTPError(402, "test-model", {"error": "insufficient_balance_error"})

    mysql_app.extensions["diagnosis_provider"] = provider
    with mysql_app.app_context():
        account = db.session.get(CreditAccount, uid)
        if account is None:
            account = CreditAccount(user_id=uid, available=0, frozen=0)
            db.session.add(account)
        db.session.commit()
        expiry = db.session.get(Membership, uid).expires_at
        operation = make_operation(uid, did)
        diagnosis.confirm(uid, operation.id)
        diagnosis.run_operation(operation.id)
        assert operation.state == "failed" and operation.attempts == 2
        assert "会员权益不受影响" in operation.error
        assert "余额" not in operation.error and "积分" not in operation.error
        assert operation.ceiling == operation.charged == 0
        assert account.available == account.frozen == 0
        assert db.session.get(Membership, uid).expires_at == expiry
        assert not db.session.scalars(
            select(CreditEntry).where(CreditEntry.operation_id == operation.id)
        ).all()


def test_historical_provider_billing_error_is_safe_on_pages_and_api(mysql_app, context):
    uid, _, job_id, did = context
    old_error = "模型服务账户余额不足或未开通此模型，请检查服务商账户。"
    with mysql_app.app_context():
        operation = make_operation(uid, did, kind="report")
        operation.state = "failed"
        operation.error = old_error
        db.session.commit()
        operation_id = operation.id
    client, _ = client_for(mysql_app, uid)
    response = client.get(f"/api/operations/{operation_id}")
    assert response.status_code == 200
    assert "会员权益不受影响" in response.json["error"]
    for path in (f"/jobs/{job_id}", "/workspace?view=reports"):
        page = client.get(path)
        assert page.status_code == 200
        assert old_error not in page.text
        assert "会员权益不受影响" in page.text
