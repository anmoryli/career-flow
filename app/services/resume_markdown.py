"""Small, safe Markdown subset for resume text. No links, raw HTML or code execution."""

import re

from markupsafe import Markup, escape

INLINE = re.compile(r"\*\*(.+?)\*\*|\*(.+?)\*", re.DOTALL)
LIST = re.compile(r"^\s*[-*]\s+(.+)$")


def inline_markdown(value: str) -> Markup:
    value = re.sub(r"^\s*[-*]\s+", "", value or "")
    pieces = []
    position = 0
    for match in INLINE.finditer(value):
        pieces.append(str(escape(value[position : match.start()])))
        tag = "strong" if match.group(1) is not None else "em"
        pieces.append(f"<{tag}>{escape(match.group(1) or match.group(2))}</{tag}>")
        position = match.end()
    pieces.append(str(escape(value[position:])))
    return Markup("".join(pieces))


def resume_markdown(value: str) -> Markup:
    lines = (value or "").splitlines()
    parts = []
    in_list = False
    for line in lines:
        item = LIST.fullmatch(line)
        if item:
            if not in_list:
                parts.append("<ul>")
                in_list = True
            parts.append(f"<li>{inline_markdown(item.group(1))}</li>")
        else:
            if in_list:
                parts.append("</ul>")
                in_list = False
            parts.append(f"<p>{inline_markdown(line) if line else '<br>'}</p>")
    if in_list:
        parts.append("</ul>")
    return Markup("".join(parts))
