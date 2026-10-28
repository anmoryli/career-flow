import base64
import io
import os

import pytest
from PIL import Image, ImageDraw, ImageFont

from app.services.pdf_import import (
    PDFInputError,
    _extract_resume_photo,
    _resume_document_from_text,
    parse_pdf,
    tesseract_executable,
)
from tests.integration.test_career_paths import minimal_pdf


def text_pdf_with_embedded_photo():
    image = io.BytesIO()
    Image.new("RGB", (184, 224), "#668877").save(image, format="JPEG")
    jpeg = image.getvalue()
    content = (
        b"BT /F1 12 Tf 45 750 Td (candidate@example.com 13800138000) Tj ET "
        b"q 73 0 0 89 45 640 cm /Im0 Do Q"
    )
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> /XObject << /Im0 5 0 R >> >> /Contents 6 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /XObject /Subtype /Image /Width 184 /Height 224 /ColorSpace /DeviceRGB "
        b"/BitsPerComponent 8 /Filter /DCTDecode /Length " + str(len(jpeg)).encode()
        + b" >>\nstream\n" + jpeg + b"\nendstream",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
    ]
    result = b"%PDF-1.4\n"
    offsets = [0]
    for index, body in enumerate(objects, 1):
        offsets.append(len(result))
        result += f"{index} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(result)
    result += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    result += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
    return (
        result
        + f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    )


def test_real_twenty_one_page_pdf_rejected():
    with pytest.raises(PDFInputError, match="20"):
        parse_pdf(minimal_pdf(page_count=21))


def test_structured_resume_fields_are_extracted_from_pdf_text():
    text = """
姓名：李梦杰 个人主页：profile.example.com
毕业学校：西南民族大学 github账号：github.com/candidate
专业：软件工程 联系电话：19395205012
电子邮箱：candidate@example.com
教育经历 Education
2023.09 ~ 2 0 27.06 西南民族大学 软件工程 本科
● GPA 3.8，专业排名 1/100
科研和项目经历 Experience
调度系统研究 | 核心研发成员 | 2025.12 - 至今
• 设计多因素动态优先级调度策略
核心技术栈
• C++、LLM Inference、Redis
知识管理系统 | 项目负责人 | 2026.03-2026.05
• 搭建知识库存储与智能检索
核心技术栈
• Spring Boot、React、MySQL
技术能力 Skills
• 后端开发：Python、Java、MySQL
荣誉奖项 Honor
● 国家奖学金（2024 学年） ● 软件设计竞赛省级二等奖
"""
    document = _resume_document_from_text(text).model_dump()

    assert document["name"] == "李梦杰"
    assert document["email"] == "candidate@example.com"
    assert document["phone"] == "19395205012"
    assert document["website"] == "profile.example.com"
    assert document["github"] == "github.com/candidate"
    assert document["education"][0]["school"] == "西南民族大学"
    assert document["education"][0]["degree"] == "本科"
    assert len(document["projects"]) == 2
    assert all(project["description"] and project["tech"] for project in document["projects"])
    assert document["skills"][0]["items"] == ["Python", "Java", "MySQL"]
    assert len(document["certificates"]) == 2


def test_extracted_profile_links_omit_web_protocol():
    document = _resume_document_from_text(
        "姓名：Candidate 个人主页：https://profile.example.com "
        "GitHub账号：https://github.com/candidate\n"
    )
    assert document.website == "profile.example.com"
    assert document.github == "github.com/candidate"


def test_embedded_portrait_is_extracted_but_full_page_scan_is_not():
    portrait = io.BytesIO()
    Image.new("RGB", (184, 224), "#668877").save(portrait, format="JPEG")

    class Stream:
        def get_data(self):
            return portrait.getvalue()

    page = type("Page", (), {
        "width": 612,
        "height": 792,
        "images": [
            {"x0": 20, "x1": 550, "top": 200, "bottom": 222, "stream": Stream()},
            {"x0": 45, "x1": 118, "top": 49, "bottom": 138, "stream": Stream()},
            {"x0": 0, "x1": 612, "top": 0, "bottom": 792, "stream": Stream()},
        ],
    })()
    photo = _extract_resume_photo([page])

    assert photo.startswith("data:image/jpeg;base64,")
    raw = base64.b64decode(photo.partition(",")[2])
    with Image.open(io.BytesIO(raw)) as decoded:
        assert decoded.size == (184, 224)


def test_mixed_text_and_embedded_photo_pdf_parses_both():
    text, document = parse_pdf(text_pdf_with_embedded_photo())

    assert "candidate@example.com" in text
    assert document["email"] == "candidate@example.com"
    assert document["phone"] == "13800138000"
    assert document["photo"].startswith("data:image/jpeg;base64,")


def test_extracted_text_budget_rejected(monkeypatch):
    class Page:
        def extract_text(self):
            return "x" * 30000

    class PDF:
        pages = [Page()] * 4

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr("pdfplumber.open", lambda *args: PDF())
    with pytest.raises(PDFInputError, match="文字过多"):
        parse_pdf(b"%PDF-resource-fixture")


def test_scanned_page_uses_bounded_ocr_and_extracts_contact(monkeypatch):
    class Page:
        width = 595
        height = 842

        def extract_text(self):
            return ""

        def to_image(self, *, resolution):
            assert resolution <= 180
            return type("Rendered", (), {"original": Image.new("RGB", (40, 40), "white")})()

    class PDF:
        pages = [Page()]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def recognize(args, **kwargs):
        assert args[0].lower().endswith("tesseract.exe") or args[0] == "tesseract"
        assert args[1:3] == ["stdin", "stdout"]
        assert kwargs["input"].startswith(b"\x89PNG")
        assert kwargs["timeout"] <= 20
        assert kwargs["env"]["OMP_THREAD_LIMIT"] == "1"
        return type("Result", (), {"returncode": 0, "stdout": b"candidate@example.com"})()

    monkeypatch.setattr("pdfplumber.open", lambda *args: PDF())
    monkeypatch.setattr("subprocess.run", recognize)
    text, document = parse_pdf(b"%PDF-scanned-fixture")
    assert text == "candidate@example.com"
    assert document["email"] == "candidate@example.com"


def test_scanned_page_reports_missing_ocr_engine(monkeypatch):
    class Page:
        width = 595
        height = 842

        def extract_text(self):
            return ""

        def to_image(self, *, resolution):
            return type("Rendered", (), {"original": Image.new("RGB", (40, 40), "white")})()

    class PDF:
        pages = [Page()]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def missing_engine(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr("pdfplumber.open", lambda *args: PDF())
    monkeypatch.setattr("subprocess.run", missing_engine)
    with pytest.raises(PDFInputError, match="OCR 服务未安装"):
        parse_pdf(b"%PDF-scanned-fixture")


@pytest.mark.skipif(tesseract_executable() is None, reason="Tesseract is not installed")
def test_real_scanned_pdf_ocr():
    image = Image.new("RGB", (1800, 650), "white")
    ImageDraw.Draw(image).text(
        (80, 180), "candidate@example.com", font=ImageFont.load_default(size=90), fill="black"
    )
    stream = io.BytesIO()
    image.save(stream, format="PDF", resolution=150)
    text, document = parse_pdf(stream.getvalue())
    assert "candidate@example.com" in text
    assert document["email"] == "candidate@example.com"


@pytest.mark.skipif(tesseract_executable() is None, reason="Tesseract is not installed")
def test_real_scanned_chinese_resume_ocr():
    font_paths = [
        r"C:\Windows\Fonts\msyh.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ]
    font_path = next((path for path in font_paths if os.path.exists(path)), None)
    if not font_path:
        pytest.skip("No Chinese test font is installed")

    image = Image.new("RGB", (1800, 1550), "white")
    font = ImageFont.truetype(font_path, 54)
    draw = ImageDraw.Draw(image)
    lines = [
        "姓名：李梦杰",
        "电话：13800138000 邮箱：limengjie@example.com",
        "教育经历",
        "2021.09 - 2025.06 西南民族大学 软件工程 本科",
        "项目经历",
        "DevMind 知识管理系统 | 项目负责人 | 2025.01 - 2025.08",
        "Python、Java、MySQL、Redis",
    ]
    for index, line in enumerate(lines):
        draw.text((80, 60 + index * 190), line, font=font, fill="black")

    stream = io.BytesIO()
    image.save(stream, format="PDF", resolution=150)
    text, document = parse_pdf(stream.getvalue())

    assert "李梦杰" in text
    assert document["name"] == "李梦杰"
    assert document["phone"] == "13800138000"
    assert document["email"] == "limengjie@example.com"
    assert document["education"], (
        f"ocr={text.encode('unicode_escape').decode()} "
        f"document={str(document).encode('unicode_escape').decode()}"
    )
    assert document["projects"]
    assert document["skills"]
