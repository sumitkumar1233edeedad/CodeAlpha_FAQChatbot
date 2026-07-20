from django.core.files.uploadedfile import SimpleUploadedFile

from base import matcher
from base.models import Document, DocumentChunk
from base.tests.helpers import TempMediaTestCase


class RebuildIndexTests(TempMediaTestCase):
    def test_faq_only_matching_still_works(self):
        matcher.rebuild_index()

        result = matcher.get_best_answer("Hello")

        self.assertIn("Hey there", result["answer"])
        self.assertEqual(result["matched_question"], "Hello")

    def test_document_chunk_is_matchable(self):
        document = Document.objects.create(
            title="Refund Policy",
            file=SimpleUploadedFile("refund.txt", b"placeholder"),
        )
        DocumentChunk.objects.create(
            document=document,
            order=0,
            text="Our refund window closes exactly fourteen days after purchase confirmation.",
        )

        matcher.rebuild_index()
        result = matcher.get_best_answer("How many days do I have for a refund window?")

        self.assertIn("fourteen days after purchase", result["answer"])
        self.assertIn("Source: Refund Policy", result["answer"])
        self.assertIsNone(result["matched_question"])
