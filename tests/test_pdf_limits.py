import io
import shutil

import pytest
from PIL import Image, ImageDraw, ImageFont

from app.services.pdf_import import PDFInputError, parse_pdf
from tests.integration.test_career_paths import minimal_pdf


def test_real_twenty_one_page_pdf_rejected():
    with pytest.raises(PDFInputError, match="20"):
        parse_pdf(minimal_pdf(page_count=21))


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
        assert args[:3] == ["tesseract", "stdin", "stdout"]
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


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract is not installed")
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
