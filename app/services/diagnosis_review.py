"""Resume-paragraph review, independent of how many suggestions the model returned."""

from app.resume_text import ready_to_insert
from app.services.diagnosis_references import editable_targets


def review_paragraphs(operation):
    snapshot = operation.input_snapshot
    targets = editable_targets(snapshot["document"])
    suggestions = {item["path"]: item for item in (operation.result or {}).get("suggestions", [])}
    document = snapshot["document"]
    rows = []
    for target in targets.values():
        path = target["path"]
        parts = path.split(".")
        if parts[0] == "summary":
            section, title = "个人简介", "个人简介"
        elif parts[0] == "experiences":
            entry = document["experiences"][int(parts[1])]
            section = "工作经历"
            title = f"{entry.get('company') or '工作经历'} · 第 {int(parts[3]) + 1} 条"
        elif parts[0] == "projects":
            entry = document["projects"][int(parts[1])]
            section, title = "项目经历", entry.get("name") or "项目描述"
        elif parts[0] == "education":
            entry = document["education"][int(parts[1])]
            section, title = "教育经历", entry.get("school") or "教育说明"
        else:
            entry = document["custom_sections"][int(parts[1])]
            section, title = "补充板块", entry.get("title") or "补充内容"
        suggestion = suggestions.get(path)
        rows.append(
            target
            | {
                "section": section,
                "title": title,
                "has_suggestion": suggestion is not None,
                "proposed": ready_to_insert(suggestion["proposed"])
                if suggestion
                else target["original"],
                "reason": suggestion["reason"] if suggestion else "",
                "limit": 600
                if path == "summary"
                else 160
                if path.startswith("education.")
                else 2000
                if path.startswith(("projects.", "custom_sections."))
                else 3000,
            }
        )
    return rows
