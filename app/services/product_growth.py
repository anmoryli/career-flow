"""Explicit, revocable sharing and referral attribution without private resume text."""

import hashlib
import hmac
import re
import secrets
from datetime import timedelta
from uuid import uuid4

from flask import current_app
from sqlalchemy import select

from app.extensions import db
from app.models import AIOperation, ReferralAttribution, ReferralCode, ReportShare, utcnow
from app.services.career import owned
from app.services.commerce import lock_user
from app.services.errors import BusinessError
from app.services.product import record_event


def redact(value):
    value = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[联系方式已隐藏]", str(value))
    return re.sub(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)", "[联系方式已隐藏]", value)[:240]


def share_snapshot(operation, fields):
    if operation.state != "succeeded" or not operation.diagnostic_id:
        raise BusinessError("请先完成岗位匹配分析。", 409)
    result = operation.result or {}
    if not isinstance(result.get("overall_score"), (int, float)) or not result.get("dimensions"):
        raise BusinessError("分析结果不完整，暂不能分享。", 409)
    snapshot = {
        "fields": sorted(set(fields)),
        "notice": "仅展示经本人选择公开的匹配复盘，不是录用或ATS通过保证。",
    }
    if "scores" in fields:
        snapshot["overall_score"] = result.get("overall_score")
        snapshot["dimensions"] = [
            {"name": item["name"], "score": item["score"]} for item in result.get("dimensions", [])
        ]
    missing = [
        item
        for item in result.get("findings", [])
        if item.get("category") == "missing" or item.get("source") == "none"
    ]
    if "gap_counts" in fields:
        snapshot["gap_count"] = len(missing)
    if "requirements" in fields:
        private = operation.input_snapshot.get("document", {})
        identities = [
            private.get(key, "") for key in ("name", "email", "phone", "website", "address")
        ]
        names = [value for value in identities if isinstance(value, str) and value.strip()]
        snapshot["requirements"] = []
        for item in missing:
            text = redact(item.get("requirement", ""))
            for name in names:
                if name:
                    text = text.replace(name, "[姓名已隐藏]")
            snapshot["requirements"].append(text)
    return snapshot


def signature(value):
    return hmac.new(
        current_app.config["SECRET_KEY"].encode(),
        ("product-share:" + value).encode(),
        hashlib.sha256,
    ).hexdigest()


def preview_signature(user_id, operation_id, data, snapshot):
    import json

    return signature(
        json.dumps(
            [user_id, operation_id, str(data.request_key), data.days, snapshot],
            sort_keys=True,
            ensure_ascii=False,
        )
    )


def create_share(user_id, operation_id, data, preview):
    lock_user(user_id)
    operation = owned(AIOperation, user_id, operation_id)
    snapshot = share_snapshot(operation, data.fields)
    if not hmac.compare_digest(
        preview or "", preview_signature(user_id, operation_id, data, snapshot)
    ):
        raise BusinessError("公开范围已变化，请先更新预览，再确认创建链接。", 409)
    existing = db.session.scalar(
        select(ReportShare).where(
            ReportShare.user_id == user_id, ReportShare.request_key == str(data.request_key)
        )
    )
    if existing:
        if (
            existing.operation_id != operation_id
            or existing.snapshot != snapshot
            or abs((existing.expires_at - existing.created_at).total_seconds() - data.days * 86400)
            > 2
        ):
            raise BusinessError("同一请求不能改变公开内容。", 409)
        db.session.commit()
        return existing
    identifier = str(uuid4())
    token = signature(identifier)
    item = ReportShare(
        id=identifier,
        user_id=user_id,
        operation_id=operation_id,
        request_key=str(data.request_key),
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        snapshot=snapshot,
        created_at=(created := utcnow()),
        expires_at=created + timedelta(days=data.days),
    )
    db.session.add(item)
    record_event(
        user_id,
        "share_created",
        f"share:{identifier}",
        share_id=identifier,
        operation_id=operation_id,
    )
    db.session.commit()
    return item


def read_share(identifier, token):
    item = db.session.get(ReportShare, identifier)
    if (
        item is None
        or item.revoked_at
        or item.expires_at <= utcnow()
        or not hmac.compare_digest(item.token_hash, hashlib.sha256(token.encode()).hexdigest())
    ):
        raise BusinessError("此分享不存在、已过期或已撤销。", 404)
    return item


def revoke_share(user_id, identifier):
    lock_user(user_id)
    item = db.session.scalar(
        select(ReportShare)
        .where(ReportShare.id == identifier, ReportShare.user_id == user_id)
        .with_for_update()
    )
    if item is None:
        raise BusinessError("分享不存在。", 404)
    if not item.revoked_at:
        item.revoked_at = utcnow()
        record_event(user_id, "share_revoked", f"revoke:{item.id}", share_id=item.id)
    db.session.commit()
    return item


def invite_code(user_id):
    lock_user(user_id)
    item = db.session.get(ReferralCode, user_id)
    if item is None:
        item = ReferralCode(user_id=user_id, code=secrets.token_urlsafe(20))
        db.session.add(item)
    db.session.commit()
    return item


def attribute_registration(user_id, code):
    if not code:
        return
    inviter = db.session.scalar(select(ReferralCode).where(ReferralCode.code == code))
    if (
        inviter is None
        or inviter.user_id == user_id
        or db.session.get(ReferralAttribution, user_id)
    ):
        return
    db.session.add(ReferralAttribution(new_user_id=user_id, inviter_id=inviter.user_id))
    record_event(user_id, "invitation_registered", f"invited:{user_id}", inviter_id=inviter.user_id)
