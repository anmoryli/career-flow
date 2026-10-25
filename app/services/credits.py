"""Serialized credit ledger writes. The account row is the aggregate lock."""

from sqlalchemy import func, select

from app.extensions import db
from app.models import CreditAccount, CreditEntry, User
from app.services.errors import BusinessError

SPEND_ORDER = ("member", "experience", "purchased")


def owner_lock(user_id):
    db.session.scalar(select(User).where(User.id == user_id).with_for_update())


def account(user_id):
    item = db.session.scalar(
        select(CreditAccount)
        .where(CreditAccount.user_id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if item is None:
        item = CreditAccount(user_id=user_id, available=0, frozen=0)
        db.session.add(item)
        db.session.flush()
    return item


def category_balances(user_id):
    rows = db.session.execute(
        select(
            CreditEntry.category,
            func.coalesce(func.sum(CreditEntry.available_delta), 0),
            func.coalesce(func.sum(CreditEntry.frozen_delta), 0),
        )
        .where(CreditEntry.user_id == user_id)
        .group_by(CreditEntry.category)
    ).all()
    return {category: (available, frozen) for category, available, frozen in rows}


def grant(user_id, amount, category, *, order_id=None, cycle_id=None):
    balance = account(user_id)
    balance.available += amount
    db.session.add(
        CreditEntry(
            user_id=user_id,
            kind="grant",
            category=category,
            available_delta=amount,
            frozen_delta=0,
            source_order_id=order_id,
            source_cycle_id=cycle_id,
        )
    )


def freeze(user_id, operation_id, amount):
    balance = account(user_id)
    if balance.available < amount:
        raise BusinessError("可用积分不足，尚未扣费。", 409)
    remaining = amount
    categories = category_balances(user_id)
    for category in SPEND_ORDER:
        taken = min(remaining, categories.get(category, (0, 0))[0])
        if taken:
            db.session.add(
                CreditEntry(
                    user_id=user_id,
                    operation_id=operation_id,
                    kind="freeze",
                    category=category,
                    available_delta=-taken,
                    frozen_delta=taken,
                )
            )
            remaining -= taken
    if remaining:
        raise BusinessError("积分账本与余额不一致，请联系管理员。", 409)
    balance.available -= amount
    balance.frozen += amount


def _reservations(operation_id):
    entries = db.session.scalars(
        select(CreditEntry)
        .where(CreditEntry.operation_id == operation_id, CreditEntry.kind == "freeze")
    ).all()
    return sorted(entries, key=lambda entry: SPEND_ORDER.index(entry.category))


def release(user_id, operation_id, amount):
    reservations = _reservations(operation_id)
    if sum(entry.frozen_delta for entry in reservations) != amount:
        raise RuntimeError("Frozen credit ledger does not match the operation")
    balance = account(user_id)
    for entry in reservations:
        db.session.add(
            CreditEntry(
                user_id=user_id,
                operation_id=operation_id,
                kind="release",
                category=entry.category,
                available_delta=entry.frozen_delta,
                frozen_delta=-entry.frozen_delta,
            )
        )
    balance.available += amount
    balance.frozen -= amount


def settle(user_id, operation_id, amount, charged):
    reservations = _reservations(operation_id)
    if sum(entry.frozen_delta for entry in reservations) != amount:
        raise RuntimeError("Frozen credit ledger does not match the operation")
    remaining = charged
    for entry in reservations:
        used = min(remaining, entry.frozen_delta)
        db.session.add(
            CreditEntry(
                user_id=user_id,
                operation_id=operation_id,
                kind="settle",
                category=entry.category,
                available_delta=entry.frozen_delta - used,
                frozen_delta=-entry.frozen_delta,
            )
        )
        remaining -= used
    if remaining:
        raise RuntimeError("Charged credits exceed the frozen amount")
    balance = account(user_id)
    balance.available += amount - charged
    balance.frozen -= amount
