"""Versioned administrator configuration. Secrets never enter JSON responses or audit."""

import base64
import hashlib
import ipaddress
import json
import socket
from urllib.parse import urlsplit

import httpx
from cryptography.fernet import Fernet, InvalidToken
from flask import current_app, g
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.admin_schemas import (
    DiagnosisPromptSettings,
    MailSettings,
    ModelRouteSettings,
    ModelSettings,
)
from app.extensions import db
from app.models import ActiveConfig, AdminAudit, ConfigRevision, User, utcnow
from app.services.errors import BusinessError

SCHEMAS = {
    "mail": MailSettings,
    "model": ModelSettings,
    "prompt_diagnosis": DiagnosisPromptSettings,
    "model_routes": ModelRouteSettings,
}


def _cipher():
    secret = current_app.config.get("ADMIN_CONFIG_KEY", "")
    if len(secret) < 32 or secret.startswith("replace-"):
        raise BusinessError("管理员配置加密密钥尚未配置。", 503)
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(key)


def _seal(value):
    return _cipher().encrypt(value.encode()).decode() if value else ""


def _unseal(value):
    if not value:
        return ""
    try:
        return _cipher().decrypt(value.encode()).decode()
    except InvalidToken:
        raise BusinessError("管理员配置密钥不匹配，请检查服务配置。", 503) from None


def audit(actor_id, action, target, before=None, after=None):
    db.session.add(
        AdminAudit(
            actor_id=actor_id,
            action=action,
            target=target,
            before=before,
            after=after,
            request_id=getattr(g, "request_id", ""),
        )
    )


def _lock_administration():
    # Every publisher locks the same row, even when there are multiple administrators.
    db.session.scalar(
        select(User.id).where(User.is_admin.is_(True)).order_by(User.id).limit(1).with_for_update()
    )


def active_revision(category):
    pointer = db.session.get(ActiveConfig, category)
    return db.session.get(ConfigRevision, pointer.revision_id) if pointer else None


def revision_summary(item):
    return {
        "id": item.id,
        "category": item.category,
        "version": item.version,
        "label": item.label,
        "settings": item.settings,
        "secret_configured": bool(item.encrypted_secret),
        "state": item.state,
        "created_at": item.created_at.isoformat(),
        "published_at": item.published_at.isoformat() if item.published_at else None,
    }


def history(category):
    if category not in SCHEMAS:
        raise BusinessError("未知配置类别。", 404)
    active = active_revision(category)
    revisions = db.session.scalars(
        select(ConfigRevision)
        .where(ConfigRevision.category == category)
        .order_by(ConfigRevision.version.desc())
        .limit(30)
    ).all()
    return {
        "active_id": active.id if active else None,
        "revisions": [revision_summary(r) for r in revisions],
    }


def create_draft(actor_id, category, data):
    if category not in SCHEMAS:
        raise BusinessError("未知配置类别。", 404)
    _lock_administration()
    settings = SCHEMAS[category].model_validate(data.settings).model_dump(mode="json")
    previous = active_revision(category)
    if category in {"prompt_diagnosis", "model_routes", "commerce"} and data.secret:
        raise BusinessError("此配置不接受密钥。", 422)
    if previous and not data.secret and category in {"mail", "model"}:
        identity_fields = ("host", "username") if category == "mail" else ("provider", "base_url")
        if any(settings[field] != previous.settings[field] for field in identity_fields):
            raise BusinessError("服务地址或账号改变时，请重新填写密钥。", 422)
    encrypted = (
        _seal(data.secret) if data.secret else (previous.encrypted_secret if previous else "")
    )
    if settings["enabled"] and category == "model" and not encrypted:
        raise BusinessError("启用模型前必须配置服务端密钥。", 422)
    if settings["enabled"] and category == "mail" and settings["username"] and not encrypted:
        raise BusinessError("启用邮箱认证前必须配置授权码。", 422)
    version = (
        db.session.scalar(
            select(func.max(ConfigRevision.version)).where(ConfigRevision.category == category)
        )
        or 0
    ) + 1
    item = ConfigRevision(
        category=category,
        version=version,
        label=data.label,
        settings=settings,
        encrypted_secret=encrypted,
        state="draft",
        author_id=actor_id,
    )
    db.session.add(item)
    audit(actor_id, "config_draft", category, after={"version": version, "settings": settings})
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise BusinessError("配置版本冲突，请刷新后重试。", 409) from None
    return item


def publish(actor_id, category, revision_id, confirm):
    if not confirm:
        raise BusinessError("请确认发布配置。", 422)
    _lock_administration()
    item = db.session.scalar(
        select(ConfigRevision)
        .where(ConfigRevision.id == revision_id, ConfigRevision.category == category)
        .with_for_update()
    )
    if item is None or category not in SCHEMAS:
        raise BusinessError("配置版本不存在。", 404)
    if item.state != "draft":
        raise BusinessError("只能发布草稿。", 409)
    SCHEMAS[category].model_validate(item.settings)
    if item.settings["enabled"] and category == "model" and not item.encrypted_secret:
        raise BusinessError("模型密钥缺失。", 422)
    if (
        item.settings["enabled"]
        and category == "mail"
        and item.settings["username"]
        and not item.encrypted_secret
    ):
        raise BusinessError("邮箱授权码缺失。", 422)
    if item.encrypted_secret:
        _unseal(item.encrypted_secret)
    pointer = db.session.get(ActiveConfig, category, with_for_update=True)
    before = pointer.revision_id if pointer else None
    if pointer:
        pointer.revision_id = item.id
    else:
        db.session.add(ActiveConfig(category=category, revision_id=item.id))
    item.state = "published"
    item.published_at = utcnow()
    audit(actor_id, "config_publish", category, {"revision_id": before}, {"revision_id": item.id})
    db.session.commit()
    return item


def rollback(actor_id, category, revision_id, confirm):
    if not confirm:
        raise BusinessError("请确认回滚配置。", 422)
    _lock_administration()
    source = db.session.scalar(
        select(ConfigRevision).where(
            ConfigRevision.id == revision_id,
            ConfigRevision.category == category,
            ConfigRevision.state == "published",
        )
    )
    if source is None or category not in SCHEMAS:
        raise BusinessError("可回滚版本不存在。", 404)
    pointer = db.session.get(ActiveConfig, category, with_for_update=True)
    before = pointer.revision_id if pointer else None
    version = (
        db.session.scalar(
            select(func.max(ConfigRevision.version)).where(ConfigRevision.category == category)
        )
        or 0
    ) + 1
    item = ConfigRevision(
        category=category,
        version=version,
        label=f"回滚至第 {source.version} 版",
        settings=source.settings,
        encrypted_secret=source.encrypted_secret,
        state="published",
        author_id=actor_id,
        published_at=utcnow(),
    )
    db.session.add(item)
    db.session.flush()
    if pointer:
        pointer.revision_id = item.id
    else:
        db.session.add(ActiveConfig(category=category, revision_id=item.id))
    audit(actor_id, "config_rollback", category, {"revision_id": before}, {"revision_id": item.id})
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise BusinessError("配置版本冲突，请刷新后重试。", 409) from None
    return item


def runtime_mail():
    item = active_revision("mail")
    if not item:
        config = current_app.config
        return {
            "host": config["MAIL_SERVER"],
            "port": config["MAIL_PORT"],
            "username": config["MAIL_USERNAME"],
            "sender": config["MAIL_DEFAULT_SENDER"],
            "use_tls": config["MAIL_USE_TLS"],
            "use_ssl": False,
            "enabled": True,
            "secret": config["MAIL_PASSWORD"],
            "revision_id": None,
        }
    return item.settings | {"secret": _unseal(item.encrypted_secret), "revision_id": item.id}


def runtime_model(revision_id=None, *, use_environment=False):
    if use_environment:
        item = None
    elif revision_id:
        item = db.session.get(ConfigRevision, revision_id)
    else:
        item = active_revision("model")
    if item:
        if item.category != "model" or item.state != "published":
            raise BusinessError("模型配置版本不可用。", 503)
        settings = item.settings | {
            "fallback_model_ids": item.settings.get("fallback_model_ids", []),
            "secret": _unseal(item.encrypted_secret),
            "revision_id": item.id,
        }
        return settings
    config = current_app.config
    return {
        "provider": "environment",
        "model_id": config["AI_MODEL"],
        "fallback_model_ids": config.get("AI_FALLBACK_MODEL_IDS", []),
        "base_url": config["AI_BASE_URL"],
        "enabled": config["AI_ENABLED"],
        "secret": config["AI_API_KEY"],
        "revision_id": None,
    }


def runtime_diagnosis_prompt():
    item = active_revision("prompt_diagnosis")
    if item and item.settings["enabled"]:
        return {
            "instructions": item.settings["instructions"],
            "revision_id": item.id,
            "version": item.version,
        }
    return {"instructions": "", "revision_id": None, "version": 1}


def runtime_model_route(purpose: str, default_model_id: str, fallback_model_ids=()):
    item = active_revision("model_routes")
    primary = (
        item.settings["routes"].get(purpose, default_model_id)
        if item and item.settings["enabled"]
        else default_model_id
    )
    candidates = []
    for model_id in (primary, default_model_id, *fallback_model_ids):
        if model_id and model_id not in candidates:
            candidates.append(model_id)
    return {
        "model_id": primary,
        "model_ids": candidates,
        "revision_id": item.id if item and item.settings["enabled"] else None,
    }


def available_models():
    """Read the active OpenAI-compatible catalog, never an arbitrary caller URL."""
    config = runtime_model()
    if not config["secret"]:
        raise BusinessError("请先在服务配置中保存模型密钥。", 503)
    endpoint = ModelSettings.model_validate(
        {key: config[key] for key in ModelSettings.model_fields if key in config}
    ).base_url
    hostname = urlsplit(endpoint).hostname
    try:
        addresses = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    except OSError:
        raise BusinessError("模型服务地址无法解析，请检查地址。", 502) from None
    if not addresses or any(
        not ipaddress.ip_address(address[4][0]).is_global for address in addresses
    ):
        raise BusinessError("模型服务地址不能指向内部网络。", 422)
    try:
        with httpx.Client(timeout=5, follow_redirects=False, trust_env=False) as client:
            with client.stream(
                "GET",
                endpoint + "/models",
                headers={"Authorization": "Bearer " + config["secret"]},
            ) as response:
                if response.status_code != 200:
                    raise BusinessError("服务商未返回模型列表，请手动填写模型 ID。", 502)
                chunks = bytearray()
                for chunk in response.iter_bytes():
                    chunks.extend(chunk)
                    if len(chunks) > 512_000:
                        raise BusinessError("模型列表过大，请手动填写模型 ID。", 502)
    except (httpx.HTTPError, OSError):
        raise BusinessError("读取模型列表失败，请手动填写模型 ID。", 502) from None
    try:
        payload = json.loads(chunks)
        items = payload["data"]
        if not isinstance(items, list):
            raise ValueError
        models = sorted(
            {
                item["id"]
                for item in items[:500]
                if isinstance(item, dict)
                and isinstance(item.get("id"), str)
                and 0 < len(item["id"]) <= 120
            }
        )
    except (ValueError, KeyError, TypeError):
        raise BusinessError("服务商模型列表格式无法识别，请手动填写模型 ID。", 502) from None
    return {"models": models[:100], "source": "active_provider"}
