import shutil
import tempfile

from django.test import TestCase, override_settings


class TempMediaTestCase(TestCase):
    """TestCase that redirects FileField uploads to a throwaway temp directory
    instead of the project's real media/ folder."""

    @classmethod
    def setUpClass(cls):
        cls._media_root = tempfile.mkdtemp()
        cls._override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)
