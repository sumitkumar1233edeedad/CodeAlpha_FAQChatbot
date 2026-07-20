from django.core.files.uploadedfile import SimpleUploadedFile

from base import matcher
from base.models import Document, DocumentChunk
from base.tests.helpers import TempMediaTestCase

LONG_PARAGRAPH = "This paragraph is long enough on its own to survive the chunk-length filter easily."


class DocumentSignalTests(TempMediaTestCase):
    def test_uploading_txt_document_creates_chunks_and_updates_matcher(self):
        document = Document.objects.create(
            title="Shipping Policy",
            file=SimpleUploadedFile("shipping.txt", LONG_PARAGRAPH.encode("utf-8")),
        )
        document.refresh_from_db()

        self.assertEqual(document.status, "processed")
        self.assertEqual(document.error_message, "")
        self.assertEqual(DocumentChunk.objects.filter(document=document).count(), 1)

        result = matcher.get_best_answer(
            "Tell me about the paragraph that is long enough to survive filtering."
        )
        self.assertIn("Source: Shipping Policy", result["answer"])

    def test_deleting_document_removes_chunks_and_updates_matcher(self):
        document = Document.objects.create(
            title="Shipping Policy",
            file=SimpleUploadedFile("shipping.txt", LONG_PARAGRAPH.encode("utf-8")),
        )
        document_id = document.id

        document.delete()

        self.assertFalse(DocumentChunk.objects.filter(document_id=document_id).exists())
        result = matcher.get_best_answer(
            "Tell me about the paragraph that is long enough to survive filtering."
        )
        self.assertNotIn("Shipping Policy", result["answer"])

    def test_unsupported_file_type_marks_document_failed(self):
        document = Document.objects.create(
            title="Mystery File",
            file=SimpleUploadedFile("notes.xyz", b"whatever content"),
        )
        document.refresh_from_db()

        self.assertEqual(document.status, "failed")
        self.assertIn("Unsupported file type", document.error_message)
        self.assertEqual(DocumentChunk.objects.filter(document=document).count(), 0)

    def test_document_with_no_extractable_text_is_processed_with_note(self):
        document = Document.objects.create(
            title="Empty File",
            file=SimpleUploadedFile("empty.txt", b"   "),
        )
        document.refresh_from_db()

        self.assertEqual(document.status, "processed")
        self.assertIn("No text could be extracted", document.error_message)
        self.assertEqual(DocumentChunk.objects.filter(document=document).count(), 0)
