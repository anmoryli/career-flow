"""Present exact source passages without treating lexical retrieval as a model finding."""

import re

from app.services.diagnosis_references import build_references, editable_targets


def evidence_rows(operation):
    refs = build_references(operation.input_snapshot)
    targets = list(editable_targets(operation.input_snapshot["document"]).values())
    rows = []
    for finding in (operation.result or {}).get("findings", []):
        evidence = finding.get("evidence", "")
        terms = set(re.findall(r"[a-zA-Z][a-zA-Z0-9+#.]*", finding["requirement"].lower()))
        chinese = re.findall(r"[\u4e00-\u9fff]+", finding["requirement"])
        terms.update(part[i : i + 2] for part in chinese for i in range(len(part) - 1))
        terms -= {"工作", "经验", "要求", "能力", "相关", "以上", "具备", "负责", "进行", "具有"}
        candidates = [item for item in refs["evidence"].values() if item["source"] == "resume"]
        ranked = sorted(
            candidates,
            key=lambda item: sum(len(term) for term in terms if term in item["text"].lower()),
            reverse=True,
        )
        related = (
            ranked[0]["text"]
            if ranked and any(term in ranked[0]["text"].lower() for term in terms)
            else ""
        )
        passage = evidence or related
        target = next(
            (
                item["path"]
                for item in targets
                if passage and (passage in item["original"] or item["original"] in passage)
            ),
            "",
        )
        rows.append(
            finding | {"passage": passage, "related": not bool(evidence), "target_path": target}
        )
    return rows


def resume_passages(operation):
    return [
        item["text"]
        for item in build_references(operation.input_snapshot)["evidence"].values()
        if item["source"] == "resume"
    ]
