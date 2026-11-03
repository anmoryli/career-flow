"""Synthetic-only product evaluation. Offline by default; no user/task data is read.

Live mode requires --budget-cny (0 < budget <= 5). The current supported live
preflight accepts only the configured SiliconFlow Qwen free model, rechecks the
vendor's current public price on every run and aborts if it is no longer free.
No fallback, SDK retry, operation creation or paid provider is permitted.

--orchestrated runs the same cases through the deepagents diagnosis
orchestrator (planner + section analysts + writer) instead of the single-shot
call; the graded gates are identical.
"""

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def vendor_price(http_get):
    page = http_get("https://www.siliconflow.cn/pricing", follow_redirects=True, timeout=30)
    page.raise_for_status()
    chunks = re.findall(r'self\.__next_f\.push\(\[1,("(?:\\.|[^"\\])*")\]\)', page.text)
    stream = "".join(json.loads(chunk) for chunk in chunks)
    objects = {}
    for line in stream.splitlines():
        key, _, value = line.partition(":")
        try:
            objects[key] = json.loads(value)
        except (ValueError, TypeError):
            continue
    model = next(
        (
            v
            for v in objects.values()
            if isinstance(v, dict) and v.get("modelName") == "Qwen/Qwen2.5-7B-Instruct"
        ),
        None,
    )
    if not model or model.get("status") != "normal":
        raise ValueError("Vendor model is unavailable or price structure is unknown")
    pricing = objects.get(str(model.get("pricing", "")).removeprefix("$"), [])
    prices = [objects.get(str(key).removeprefix("$"), {}) for key in pricing]
    if (
        not prices
        or any(Decimal(str(item.get("price", "NaN"))) != 0 for item in prices)
        or Decimal(model.get("price", "NaN")) != 0
    ):
        raise ValueError("Current public price is not verified free; live run refused")
    return {
        "url": str(page.url),
        "model": model["modelName"],
        "price_cny": "0",
        "source_sha256": hashlib.sha256(page.content).hexdigest(),
    }


def grade(case, output, snapshot):
    from app.resume_text import ready_to_insert
    from app.services.diagnosis import validate_output
    from app.services.diagnosis_references import build_references

    result = validate_output(output, snapshot)
    refs = build_references(snapshot)
    checked = {f["requirement"] for f in result["findings"]}
    checks = {
        "schema_and_exact_evidence": True,
        "all_requirements_checked": set(refs["requirements"].values()) <= checked,
        "related_original_located": not case["related_evidence"]
        or any(f["source"] == "resume" for f in result["findings"]),
        "single_question": result["question"].count("?") + result["question"].count("？") <= 1,
        "no_forbidden_new_claim": not any(
            term.lower() in suggestion["proposed"].lower()
            for term in case["forbidden"]
            for suggestion in result["suggestions"]
        ),
        "insertable_replacements": all(
            ready_to_insert(s["proposed"]) == s["proposed"] for s in result["suggestions"]
        ),
    }
    return checks, result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--orchestrated", action="store_true")
    parser.add_argument("--budget-cny", type=Decimal)
    parser.add_argument("--output", default="output/product-model-evaluation.json")
    # Free tiers enforce a tokens-per-minute budget; a full orchestrated run
    # can exhaust it, so live runs can pace the cases.
    parser.add_argument("--pace-seconds", type=float, default=0)
    # The free-model guard exists to make unapproved spend impossible. With an
    # explicit budget the configured production model may be used instead; the
    # run then meters every case and stops before the budget is exceeded.
    parser.add_argument("--allow-paid-model", action="store_true")
    args = parser.parse_args()
    if args.live and (args.budget_cny is None or not 0 < args.budget_cny <= 5):
        parser.error("Live authorization requires 0 < --budget-cny <= 5")
    from app.career_schemas import ResumeDocument
    from app.services.diagnosis_references import build_references

    cases = json.loads((ROOT / "tests/fixtures/product_eval.json").read_text(encoding="utf8"))
    report = {
        "mode": "live" if args.live else "offline_contract_only",
        "orchestrated": bool(args.orchestrated),
        "at": datetime.now(UTC).isoformat(),
        "synthetic_only": True,
        "budget_cny": str(args.budget_cny) if args.live else None,
        "cases": [],
        "estimated_cost_cny": "0" if args.live else None,
    }
    prompt = None
    unit_price = None
    spent = Decimal("0")
    if args.live:
        import httpx
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
        from app import create_app
        from app.services.admin_config import (
            runtime_diagnosis_prompt,
            runtime_model,
            runtime_model_profile,
        )

        app = create_app()
        with app.app_context():
            model = runtime_model()
            profile = runtime_model_profile(model["revision_id"], model["model_id"])
            from urllib.parse import urlsplit

            host = urlsplit(profile["base_url"]).hostname
            free_model = model["model_id"] == "Qwen/Qwen2.5-7B-Instruct"
            if free_model and host == "api.siliconflow.cn":
                report["pricing_preflight"] = vendor_price(httpx.get)
            elif args.allow_paid_model:
                from app.services.product import policy

                usage_policy, _ = policy()
                unit_price = usage_policy.model_prices.get(model["model_id"])
                if unit_price is None:
                    raise ValueError("该模型未配置单价，无法核算预算")
                report["pricing_preflight"] = {
                    "source": "product_policy",
                    "model": model["model_id"],
                    "input_per_million_cny": str(unit_price.input_per_million_cny),
                    "output_per_million_cny": str(unit_price.output_per_million_cny),
                }
            else:
                raise ValueError(
                    "Only the explicitly authorized configured Qwen model is supported; "
                    "pass --allow-paid-model with a budget to use the production model"
                )
            prompt = runtime_diagnosis_prompt()
            report["model_revision"] = model["revision_id"]
            report["prompt_config_version"] = prompt.get("version")
            report["configured_prompt_sha256"] = hashlib.sha256(
                prompt["instructions"].encode()
            ).hexdigest()
        if args.orchestrated:
            from app.services.agent_orchestrator import run_diagnosis_agent

            def run(snapshot):
                output, calls, tokens = run_diagnosis_agent(snapshot)
                return output, calls, tokens

    for index, case in enumerate(cases):
        if args.live and index and args.pace_seconds > 0:
            time.sleep(args.pace_seconds)
        document = ResumeDocument.model_validate(case["document"]).model_dump(mode="json")
        snapshot = {
            "document": document,
            "jd": case["jd"],
            "answers": [],
            "kind": "analysis",
            "rounds": 0,
            "access_tier": "member",
        }
        refs = build_references(snapshot)
        row = {
            "id": case["id"],
            "requirements": len(refs["requirements"]),
            "evidence_excerpts": len(refs["evidence"]),
            "targets": len(refs["targets"]),
        }
        if args.live:
            snapshot.update(
                model=model["model_id"],
                model_revision_id=model["revision_id"],
                prompt_instructions=prompt["instructions"],
            )
            start = time.monotonic()
            try:
                with app.app_context():
                    if args.orchestrated:
                        output, calls, total = run(snapshot)
                        checks, result = grade(case, output, snapshot)
                        row.update(
                            checks=checks,
                            passed=all(checks.values()),
                            result=result,
                            llm_calls=len(calls),
                            provider_errors=sum(
                                1 for call in calls if call["outcome"] != "returned"
                            ),
                            input_tokens=sum(call["input"] or 0 for call in calls),
                            output_tokens=sum(call["output"] or 0 for call in calls),
                            total_tokens=total,
                        )
                    else:
                        from app.services.model_provider import generate

                        output, usage = generate(snapshot)
                        checks, result = grade(case, output, snapshot)
                        row.update(
                            checks=checks,
                            passed=all(checks.values()),
                            result=result,
                            input_tokens=usage.input_tokens,
                            output_tokens=usage.output_tokens,
                        )
            except Exception as error:
                row.update(
                    passed=False,
                    error_type=type(error).__name__,
                    # Our own validators raise short, content-free messages;
                    # provider errors are reduced to the exception class above.
                    error_detail=(
                        str(error)[:200]
                        if type(error).__module__.startswith("app.")
                        else None
                    ),
                )
            row["latency_seconds"] = round(time.monotonic() - start, 3)
        else:
            row["contract_valid"] = bool(refs["evidence"] and refs["requirements"])
        report["cases"].append(row)
        if args.live and unit_price is not None and row.get("input_tokens") is not None:
            spent += (
                Decimal(row["input_tokens"]) * unit_price.input_per_million_cny
                + Decimal(row["output_tokens"] or 0) * unit_price.output_per_million_cny
            ) / Decimal(1000000)
            report["estimated_cost_cny"] = str(spent.quantize(Decimal("0.000001")))
        target = ROOT / args.output
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
        print(
            json.dumps({k: v for k, v in row.items() if k != "result"}, ensure_ascii=True),
            flush=True,
        )
        if args.live and spent > args.budget_cny:
            raise SystemExit("已超出本轮授权预算，按要求停止评测")
    if args.live:
        return int(any(not row["passed"] for row in report["cases"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
