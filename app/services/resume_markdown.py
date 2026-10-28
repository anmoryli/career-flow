"""Small, safe Markdown subset for resume text. No links, raw HTML or code execution."""

import re
from urllib.parse import urlsplit

from markupsafe import Markup, escape

INLINE = re.compile(
    r"\[([^\]]+)\]\((https?://[^\s)]+)\)|`([^`]+)`|\*\*(.+?)\*\*|__(.+?)__|\*(.+?)\*|_(.+?)_"
)
UNORDERED_ITEM = re.compile(r"^\s*[-*+]\s+(.+)$")
ORDERED_ITEM = re.compile(r"^\s*\d+[.)]\s+(.+)$")
HEADING = re.compile(r"^(#{1,3})\s+(.+)$")


def inline_markdown(value: str) -> Markup:
    value = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", value or "")
    pieces = []
    position = 0
    for match in INLINE.finditer(value):
        pieces.append(str(escape(value[position : match.start()])))
        label, url, code, bold, bold_alt, italic, italic_alt = match.groups()
        if label is not None and urlsplit(url).scheme in {"http", "https"}:
            pieces.append(
                f'<a href="{escape(url)}" target="_blank" rel="noopener noreferrer">'
                f"{escape(label)}</a>"
            )
        elif code is not None:
            pieces.append(f"<code>{escape(code)}</code>")
        elif bold is not None or bold_alt is not None:
            pieces.append(f"<strong>{escape(bold or bold_alt)}</strong>")
        else:
            pieces.append(f"<em>{escape(italic or italic_alt)}</em>")
        position = match.end()
    pieces.append(str(escape(value[position:])))
    return Markup("".join(pieces))


def resume_markdown(value: str) -> Markup:
    lines = (value or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    parts = []
    paragraph = []
    list_type = None

    def close_paragraph():
        if paragraph:
            text = " ".join(part.strip() for part in paragraph)
            parts.append(f"<p>{inline_markdown(text)}</p>")
            paragraph.clear()

    def close_list():
        nonlocal list_type
        if list_type:
            parts.append(f"</{list_type}>")
            list_type = None

    for line in lines:
        heading = HEADING.fullmatch(line.strip())
        unordered = UNORDERED_ITEM.fullmatch(line)
        ordered = ORDERED_ITEM.fullmatch(line)
        if heading:
            close_paragraph()
            close_list()
            level = min(len(heading.group(1)) + 2, 5)
            parts.append(f"<h{level}>{inline_markdown(heading.group(2))}</h{level}>")
        elif unordered or ordered:
            close_paragraph()
            requested_type = "ul" if unordered else "ol"
            if list_type != requested_type:
                close_list()
                list_type = requested_type
                parts.append(f"<{list_type}>")
            item = unordered or ordered
            parts.append(f"<li>{inline_markdown(item.group(1))}</li>")
        elif line.strip():
            close_list()
            paragraph.append(line)
        else:
            close_paragraph()
            close_list()
    close_paragraph()
    close_list()
    return Markup("".join(parts))
