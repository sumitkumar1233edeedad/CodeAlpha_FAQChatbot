import io
from unittest.mock import MagicMock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from base.document_processing import chunk_text, extract_text
from base.models import Document


class ExtractTextTests(SimpleTestCase):
    def test_txt(self):
        doc = Document(file=SimpleUploadedFile("notes.txt", b"Hello from a text file."))
        self.assertEqual(extract_text(doc), "Hello from a text file.")

    def test_pdf(self):
        doc = Document(file=SimpleUploadedFile("notes.pdf", b"%PDF-1.4 fake bytes"))
        fake_page_1 = MagicMock()
        fake_page_1.extract_text.return_value = "Page one text."
        fake_page_2 = MagicMock()
        fake_page_2.extract_text.return_value = "Page two text."
        with patch("base.document_processing.PdfReader") as mock_reader_cls:
            mock_reader_cls.return_value.pages = [fake_page_1, fake_page_2]
            result = extract_text(doc)
        self.assertEqual(result, "Page one text.\n\nPage two text.")

    def test_docx(self):
        from docx import Document as DocxDocument

        buffer = io.BytesIO()
        docx_doc = DocxDocument()
        docx_doc.add_paragraph("First paragraph.")
        docx_doc.add_paragraph("Second paragraph.")
        docx_doc.save(buffer)

        doc = Document(file=SimpleUploadedFile("notes.docx", buffer.getvalue()))
        result = extract_text(doc)
        self.assertEqual(result, "First paragraph.\n\nSecond paragraph.")

    def test_unsupported_extension_raises(self):
        doc = Document(file=SimpleUploadedFile("notes.xyz", b"whatever"))
        with self.assertRaises(ValueError):
            extract_text(doc)


class ChunkTextTests(SimpleTestCase):
    def test_splits_on_paragraph_breaks(self):
        text = "First paragraph here.\n\nSecond paragraph here too."
        self.assertEqual(
            chunk_text(text),
            ["First paragraph here.", "Second paragraph here too."],
        )

    def test_drops_short_chunks(self):
        text = (
            "This is a long enough paragraph to keep.\n\n"
            "short\n\n"
            "Another long enough paragraph to keep."
        )
        result = chunk_text(text)
        self.assertEqual(len(result), 2)
        self.assertNotIn("short", result)

    def test_no_paragraph_breaks_returns_single_chunk(self):
        text = "Just one long paragraph with no breaks in it at all here."
        self.assertEqual(chunk_text(text), [text])
