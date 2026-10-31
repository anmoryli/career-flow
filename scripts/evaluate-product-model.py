"""Synthetic-only product evaluation. Offline by default; no user/task data is read.

Live mode requires --budget-cny (0 < budget <= 5). The current supported live
preflight accepts only the configured SiliconFlow Qwen free model, rechecks the
vendor's current public price on every run and aborts if it is no longer free.
No fallback, SDK retry, operation creation or paid provider is permitted.
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
    parser.add_argument("--budget-cny", type=Decimal)
    parser.add_argument("--output", default="output/product-model-evaluation.json")
    args = parser.parse_args()
    if args.live and (args.budget_cny is None or not 0 < args.budget_cny <= 5):
        parser.error("Live authorization requires 0 < --budget-cny <= 5")
    from app.career_schemas import ResumeDocument
    from app.services.diagnosis_references import REFERENCE_INSTRUCTIONS, build_references

    cases = json.loads((ROOT / "tests/fixtures/product_eval.json").read_text(encoding="utf8"))
    report = {
        "mode": "live" if args.live else "offline_contract_only",
        "at": datetime.now(UTC).isoformat(),
        "synthetic_only": True,
        "budget_cny": str(args.budget_cny) if args.live else None,
        "prompt_sha256": hashlib.sha256(REFERENCE_INSTRUCTIONS.encode()).hexdigest(),
        "cases": [],
        "estimated_cost_cny": "0" if args.live else None,
    }
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
        from app.services.model_provider import generate

        app = create_app()
        with app.app_context():
            model = runtime_model()
            if model["model_id"] != "Qwen/Qwen2.5-7B-Instruct":
                raise ValueError(
                    "Only the explicitly authorized configured Qwen model is supported"
                )
            profile = runtime_model_profile(model["revision_id"], model["model_id"])
            from urllib.parse import urlsplit

            if urlsplit(profile["base_url"]).hostname != "api.siliconflow.cn":
                raise ValueError("Unsupported provider: budget cannot be verified")
            report["pricing_preflight"] = vendor_price(httpx.get)
            prompt = runtime_diagnosis_prompt()
            report["model_revision"] = model["revision_id"]
            report["prompt_config_version"] = prompt.get("version")
            report["configured_prompt_sha256"] = hashlib.sha256(
                prompt["instructions"].encode()
            ).hexdigest()
    for case in cases:
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
                row.update(passed=False, error_type=type(error).__name__)
            row["latency_seconds"] = round(time.monotonic() - start, 3)
        else:
            row["contract_valid"] = bool(refs["evidence"] and refs["requirements"])
        report["cases"].append(row)
        target = ROOT / args.output
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
        print(
            json.dumps({k: v for k, v in row.items() if k != "result"}, ensure_ascii=True),
            flush=True,
        )
    if args.live:
        return int(any(not row["passed"] for row in report["cases"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
