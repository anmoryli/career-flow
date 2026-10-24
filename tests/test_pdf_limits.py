import pytest

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
