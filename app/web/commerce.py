"""User-confirmed local mock checkout. No live payment provider is called."""

from uuid import UUID

from flask import Blueprint, flash, g, redirect, url_for
from pydantic import BaseModel, ConfigDict, Field

from app.services import commerce
from app.web.routes import input_data, login_required

commerce_web = Blueprint("commerce", __name__)


class OrderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_key: UUID
    plan_code: str = Field(min_length=1, max_length=32)


class PaymentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome: str = Field(pattern="^(success|failure)$")


def billing_page():
    return redirect(url_for("web.workspace", view="billing"), code=303)


@commerce_web.post("/commerce/orders")
@login_required
def order():
    data = OrderInput.model_validate(input_data())
    commerce.create_order(g.user.id, data.request_key, data.plan_code)
    flash("订单已创建，请确认模拟支付结果。", "success")
    return billing_page()


@commerce_web.post("/commerce/orders/<int:order_id>/mock-payment")
@login_required
def mock_payment(order_id):
    data = PaymentInput.model_validate(input_data())
    item = commerce.settle_mock(g.user.id, order_id, data.outcome)
    message = "模拟支付成功，权益已到账。" if item.state == "paid" else "模拟支付失败，订单未扣款。"
    flash(message, "success")
    return billing_page()
