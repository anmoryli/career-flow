"""Publish local-development service configuration through the admin service.

Only for the local development database. It reuses the shipped publish path
(version bump, audit entry, encrypted keys), so the result is exactly what an
administrator would produce in the settings screen.

    python scripts/local-test-config.py --mail
    python scripts/local-test-config.py \
        --model-primary deepseek-flash,Qwen/Qwen2.5-7B-Instruct,deepseek-v4-pro
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

from app import create_app  # noqa: E402
from app.admin_schemas import ConfigDraftInput  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import User  # noqa: E402
from app.services import admin_config  # noqa: E402

MAILPIT = {
    "host": "127.0.0.1",
    "port": 1026,
    "username": "",
    "sender": "CareerFlow <noreply@careerflow.local>",
    "use_tls": False,
    "use_ssl": False,
    "enabled": True,
}
# Mailpit accepts unauthenticated mail. The field is only required because the
# publish path insists on a fresh secret whenever the host changes.
MAILPIT_SECRET = "local-mailpit-no-auth"


def admin_id():
    user = db.session.scalar(db.select(User).where(User.is_admin.is_(True)).order_by(User.id))
    if user is None:
        raise SystemExit("没有管理员账号，无法发布配置")
    return user.id


def publish_mail():
    current = admin_config.active_revision("mail")
    if current and current.settings | {"secret": ""} == MAILPIT | {"secret": ""}:
        print(f"mail 已是本地 Mailpit 配置（v{current.version}），跳过")
        return
    item = admin_config.create_draft(
        admin_id(),
        "mail",
        ConfigDraftInput(label="本地 Mailpit", settings=MAILPIT, secret=MAILPIT_SECRET),
        activate=True,
    )
    print(f"mail 已发布 v{item.version}（id={item.id}）→ 127.0.0.1:1026，无认证")


def publish_model(order):
    current = admin_config.active_revision("model")
    profiles = admin_config._model_profiles(current.settings)
    keys = admin_config._model_keys(current)
    by_identity = {
        (item["provider"], item["base_url"]): key
        for item, key in zip(profiles, keys, strict=True)
    }

    reordered = []
    for model_id in order:
        source = next((item for item in profiles if item["model_id"] == model_id), None)
        if source is None:
            available = [p["model_id"] for p in profiles]
            raise SystemExit(f"已发布配置里没有模型 {model_id}，可选: {available}")
        reordered.append(source)
    if len(reordered) != 3:
        raise SystemExit("必须给出 3 个模型（主模型在前）")
    if [item["model_id"] for item in reordered] == [item["model_id"] for item in profiles]:
        print(f"model 已是该顺序（v{current.version}），跳过")
        return
    secrets = [by_identity.get((item["provider"], item["base_url"]), "") for item in reordered]
    settings = {"models": reordered, "tokens_per_credit": None, "enabled": True}
    item = admin_config.create_draft(
        admin_id(),
        "model",
        ConfigDraftInput(
            label="DeepSeek 优先（真实模型测试）", settings=settings, secret=json.dumps(secrets)
        ),
        activate=True,
    )
    backups = [p["model_id"] for p in reordered[1:]]
    primary = reordered[0]["model_id"]
    print(f"model 已发布 v{item.version}（id={item.id}）→ 主 {primary}，备 {backups}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mail", action="store_true")
    parser.add_argument("--model-primary", default="")
    args = parser.parse_args()
    if not args.mail and not args.model_primary:
        parser.error("至少指定 --mail 或 --model-primary")
    app = create_app()
    with app.app_context():
        if args.mail:
            publish_mail()
        if args.model_primary:
            publish_model([item for item in args.model_primary.split(",") if item])


if __name__ == "__main__":
    main()
