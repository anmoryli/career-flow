"""Inspect browser-produced fixtures; not an ATS pass-rate claim."""

from pathlib import Path

import pdfplumber

root = Path(__file__).resolve().parents[1]
for name in ["desktop", "tablet", "mobile"]:
    target = root / "output" / f"resume-{name}.pdf"
    with pdfplumber.open(target) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        assert "林测试" in text, f"Expected user name absent: {name}"
        assert "第三家公司" in text, f"Expected dynamic experience absent: {name}"
        assert "保存简历" not in text, f"Editor controls leaked into print: {name}"
        print(f"{name}: {len(pdf.pages)} A4 page(s), user content present, editor controls absent")
