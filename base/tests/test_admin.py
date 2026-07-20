from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from base.models import Document, DocumentChunk
from base.tests.helpers import TempMediaTestCase

LONG_PARAGRAPH = "This refund policy paragraph is long enough to survive the chunk-length filter."


class DocumentAdminTests(TempMediaTestCase):
    def setUp(self):
        User = get_user_model()
        self.admin_user = User.objects.create_superuser(
            username="admintest", email="admin@example.com", password="testpass123"
        )
        self.client.force_login(self.admin_user)

    def test_upload_document_via_admin_creates_chunks(self):
        upload = SimpleUploadedFile("policy.txt", LONG_PARAGRAPH.encode("utf-8"))
        response = self.client.post(
            reverse("admin:base_document_add"),
            {
                "title": "Refund Policy",
                "file": upload,
                "chunks-TOTAL_FORMS": "0",
                "chunks-INITIAL_FORMS": "0",
                "chunks-MIN_NUM_FORMS": "0",
                "chunks-MAX_NUM_FORMS": "1000",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        document = Document.objects.get(title="Refund Policy")
        self.assertEqual(document.status, "processed")
        self.assertTrue(DocumentChunk.objects.filter(document=document).exists())

    def test_change_page_shows_chunks_inline(self):
        upload = SimpleUploadedFile("policy.txt", LONG_PARAGRAPH.encode("utf-8"))
        self.client.post(
            reverse("admin:base_document_add"),
            {
                "title": "Refund Policy",
                "file": upload,
                "chunks-TOTAL_FORMS": "0",
                "chunks-INITIAL_FORMS": "0",
                "chunks-MIN_NUM_FORMS": "0",
                "chunks-MAX_NUM_FORMS": "1000",
            },
            follow=True,
        )
        document = Document.objects.get(title="Refund Policy")

        response = self.client.get(reverse("admin:base_document_change", args=[document.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "refund policy paragraph")
