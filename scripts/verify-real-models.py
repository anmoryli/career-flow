"""Run the real configured providers over one fixed, synthetic case.

This is an operator verification harness, not part of the product surface:
it never touches member data, always uses the same synthetic resume/JD, and
records outcomes under a dedicated probe account so results can be audited.

    python scripts/verify-real-models.py --models deepseek-flash,Qwen/Qwen2.5-7B-Instruct

Every call goes through the same service entry points the web app uses
(quote -> provider -> contract validation), so a green line here means the
real provider satisfies the shipped output contract for that purpose.
"""

import argparse
import json
import sys
import time
import traceback
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

from werkzeug.security import generate_password_hash  # noqa: E402

from app import create_app  # noqa: E402
from app.career_schemas import JobSave, ResumeSave  # noqa: E402
from app.diagnosis_schemas import QuoteInput  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import AuthIdentity, Membership, Resume, User, utcnow  # noqa: E402
from app.resume_ai_schemas import (  # noqa: E402
    ResumeAIOutput,
    ResumeAIQuote,
    ResumeComposeOutput,
    ResumeComposeQuote,
)
from app.services import career, diagnosis, resume_ai  # noqa: E402
from app.services.model_provider import (  # noqa: E402
    generate,
    generate_resume,
    generate_resume_document,
)

PROBE_EMAIL = "real-model-probe@careerflow.local"

RESUME = {
    "name": "陈嘉禾",
    "role": "产品经理",
    "email": "probe@careerflow.local",
    "city": "杭州",
    "summary": "5 年 B 端产品经验，负责供应链协同系统的需求分析与迭代规划。",
    "experiences": [
        {
            "company": "杭州云链科技",
            "role": "高级产品经理",
            "period": "2022.03 - 至今",
            "bullets": [
                "负责供应商协同平台的订单与对账模块，覆盖 320 家供应商。",
                "牵头把对账周期从 7 天压缩到 2 天，月度人工核销工时下降约 60%。",
            ],
        },
        {
            "company": "宁波智造软件",
            "role": "产品经理",
            "period": "2020.07 - 2022.02",
            "bullets": ["负责仓储管理系统的入库与盘点流程设计，支持 4 个仓库上线。"],
        },
    ],
    "projects": [
        {
            "name": "供应商对账自动化",
            "role": "产品负责人",
            "period": "2023.04 - 2023.11",
            "description": (
                "梳理 12 类对账差异场景，设计规则引擎与人工复核队列，"
                "上线后差异单量下降 45%."
            ),
        }
    ],
    "education": [
        {"school": "浙江工业大学", "degree": "本科 · 信息管理与信息系统", "period": "2016 - 2020"}
    ],
    "skills": [{"label": "产品", "items": ["需求分析", "流程设计", "数据埋点"]}],
}

JD = """岗位：供应链产品经理（B 端）
职责：
1. 负责供应商协同与对账产品的规划与迭代；
2. 梳理业务流程，输出需求文档与原型；
3. 与研发、运营协作推动上线，并用数据验证效果。
要求：
1. 3 年以上 B 端产品经验，熟悉供应链或财务对账场景；
2. 具备数据分析能力，能独立完成指标拆解；
3. 有跨部门项目推动经验，沟通表达清晰。
加分项：了解 SQL，做过 SaaS 商业化。"""

REPORT_ANSWERS = [
    {
        "question": "你在对账自动化项目里具体负责哪些决策？",
        "answer": "我负责差异场景的归类规则和复核队列设计，和财务一起定了 12 类差异的处理优先级。",
        "skipped": False,
    }
]


def probe_user():
    user = db.session.scalar(db.select(User).where(User.email == PROBE_EMAIL))
    if user is None:
        user = User(email=PROBE_EMAIL, display_name="真实模型验证账号")
        db.session.add(user)
        db.session.flush()
        db.session.add(
            AuthIdentity(user_id=user.id, password_hash=generate_password_hash(uuid4().hex))
        )
    membership = db.session.get(Membership, user.id)
    if membership is None:
        db.session.add(
            Membership(
                user_id=user.id,
                plan_code="membership_yearly",
                expires_at=utcnow().replace(year=utcnow().year + 5),
                next_grant_at=utcnow().replace(year=utcnow().year + 5),
            )
        )
    db.session.commit()
    return user.id


def new_resume(user_id):
    """Reuse one probe resume so repeated runs never hit the 10-resume cap."""
    existing = db.session.scalar(
        db.select(Resume).where(Resume.user_id == user_id).order_by(Resume.id).limit(1)
    )
    if existing is None:
        return career.save_resume(
            user_id, ResumeSave(request_key=uuid4(), title="真实模型验证简历", document=RESUME)
        )
    return career.save_resume(
        user_id,
        ResumeSave(
            request_key=uuid4(),
            revision=existing.revision,
            title="真实模型验证简历",
            document=RESUME,
        ),
        existing.id,
    )


def new_job(user_id, resume_id, revision):
    saved = career.save_job(
        user_id,
        JobSave(
            request_key=uuid4(),
            resume_id=resume_id,
            resume_revision=revision,
            title="供应链产品经理",
            description=JD,
        ),
    )
    return saved


def diagnose(user_id, model_id):
    resume = new_resume(user_id)
    job = new_job(user_id, resume["id"], resume["revision"])
    diagnostic = diagnosis.get_diagnostic(user_id, job["id"])
    operation = diagnosis.quote(
        user_id, diagnostic.id, QuoteInput(request_key=uuid4(), kind="analysis")
    )
    snapshot = dict(operation.input_snapshot) | {"model": model_id}
    started = time.monotonic()
    raw, usage = generate(snapshot)
    elapsed = time.monotonic() - started
    validated = diagnosis.validate_output(raw, snapshot)
    return {
        "elapsed": elapsed,
        "usage": int(usage),
        "summary_len": len(validated["summary"]),
        "dimensions": {item["name"]: item["score"] for item in validated["dimensions"]},
        "findings": len(validated["findings"]),
        "suggestions": len(validated["suggestions"]),
        "question": validated.get("question", "")[:120],
    }


def rewrite(user_id, model_id):
    resume = new_resume(user_id)
    operation = resume_ai.quote(
        user_id,
        resume["id"],
        ResumeAIQuote(
            request_key=uuid4(),
            revision=resume["revision"],
            mode="optimize",
            path="experiences.0.bullets.1",
            requirement="强调可量化的业务结果",
        ),
    )
    snapshot = dict(operation.input_snapshot) | {"model": model_id}
    started = time.monotonic()
    raw, usage = generate_resume(snapshot)
    elapsed = time.monotonic() - started
    validated = ResumeAIOutput.model_validate(raw)
    return {
        "elapsed": elapsed,
        "usage": int(usage),
        "proposed": validated.proposed[:160],
        "reason": validated.reason[:120],
    }


def compose(user_id, model_id):
    resume = new_resume(user_id)
    source = (
        "我叫陈嘉禾，做 B 端产品 5 年。2022 年 3 月到现在在杭州云链科技做高级产品经理，"
        "负责供应商协同平台的订单和对账模块，服务 320 家供应商，把对账周期从 7 天压到 2 天。"
        "之前 2020 年 7 月到 2022 年 2 月在宁波智造软件做产品经理，负责仓储系统的入库和盘点。"
        "本科是浙江工业大学信息管理与信息系统，2016 到 2020。"
    )
    operation = resume_ai.quote_compose(
        user_id,
        resume["id"],
        ResumeComposeQuote(request_key=uuid4(), revision=resume["revision"], source=source),
    )
    snapshot = dict(operation.input_snapshot) | {"model": model_id}
    started = time.monotonic()
    raw, usage = generate_resume_document(snapshot)
    elapsed = time.monotonic() - started
    validated = ResumeComposeOutput.model_validate(raw)
    document = validated.document.model_dump()
    return {
        "elapsed": elapsed,
        "usage": int(usage),
        "name": document["name"],
        "experiences": len(document["experiences"]),
        "bullets": sum(len(item["bullets"]) for item in document["experiences"]),
        "reason": validated.reason[:120],
    }


TASKS = {"diagnosis": diagnose, "rewrite": rewrite, "compose": compose}


def describe_error(error):
    from app.services.model_runtime import provider_error

    root = provider_error(error)
    return {
        "type": type(root).__name__,
        "status": getattr(root, "status_code", None),
        "message": str(root)[:200],
        "raised": f"{type(error).__name__}: {str(error)[:200]}",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", default="")
    parser.add_argument("--tasks", default=",".join(TASKS))
    parser.add_argument("--out", default="output/real-model/matrix.json")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        from app.services.admin_config import active_revision

        revision = active_revision("model")
        configured = [item["model_id"] for item in revision.settings["models"]]
        models = [item for item in args.models.split(",") if item] or configured
        unknown = [item for item in models if item not in configured]
        if unknown:
            raise SystemExit(f"模型不在已发布配置中: {unknown}")
        tasks = [item for item in args.tasks.split(",") if item]
        unknown_tasks = [item for item in tasks if item not in TASKS]
        if unknown_tasks:
            raise SystemExit(f"未知任务: {unknown_tasks}")

        user_id = probe_user()
        print(f"配置版本 {revision.id} (v{revision.version})，探针账号 id={user_id}")
        print(f"模型: {models}  任务: {tasks}\n")

        results = {"revision": revision.id, "version": revision.version, "runs": []}
        for model_id in models:
            for task in tasks:
                started = time.monotonic()
                record = {"model": model_id, "task": task}
                try:
                    record |= {"ok": True} | TASKS[task](user_id, model_id)
                    usage = record["usage"]
                    elapsed = record["elapsed"]
                    print(f"  OK   {model_id:<28} {task:<10} {elapsed:6.2f}s usage={usage}")
                except Exception as error:  # noqa: BLE001 - verification harness
                    record |= {"ok": False, "error": describe_error(error)}
                    record["elapsed"] = time.monotonic() - started
                    raised = record["error"]["raised"]
                    print(f"  FAIL {model_id:<28} {task:<10} {record['elapsed']:6.2f}s {raised}")
                    traceback.print_exc(limit=3)
                finally:
                    db.session.rollback()
                results["runs"].append(record)

        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        failed = [item for item in results["runs"] if not item["ok"]]
        print(f"\n完成 {len(results['runs'])} 项，失败 {len(failed)} 项 → {out}")
        return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
