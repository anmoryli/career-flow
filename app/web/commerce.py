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


def billing_page():
    return redirect(url_for("web.workspace", view="billing"), code=303)


@commerce_web.post("/commerce/orders")
@login_required
def order():
    data = OrderInput.model_validate(input_data())
    item = commerce.create_order(g.user.id, data.request_key, data.plan_code)
    if commerce.mock_enabled():
        commerce.settle_mock(g.user.id, item.id, "success")
        flash("会员已开通。", "success")
    else:
        flash("当前支付方式暂不可用。", "error")
    return billing_page()
