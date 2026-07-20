from django.core.files.uploadedfile import SimpleUploadedFile

from base.models import Document
from base.tests.helpers import TempMediaTestCase


class DocumentModelTests(TempMediaTestCase):
    def test_status_field_defaults_to_pending(self):
        self.assertEqual(Document._meta.get_field("status").default, "pending")

    def test_str_returns_title_when_present(self):
        document = Document.objects.create(
            title="Test Doc",
            file=SimpleUploadedFile("test.txt", b"some file content"),
        )
        self.assertEqual(str(document), "Test Doc")

    def test_str_falls_back_to_filename_when_no_title(self):
        document = Document.objects.create(
            file=SimpleUploadedFile("test.txt", b"some file content"),
        )
        self.assertIn("test", str(document))
