import logging

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from . import matcher
from .document_processing import chunk_text, extract_text
from .models import Document, DocumentChunk

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Document)
def process_document(sender, instance, created, **kwargs):
    DocumentChunk.objects.filter(document=instance).delete()

    try:
        text = extract_text(instance)
    except Exception as exc:
        logger.warning("Failed to extract text from %s: %s", instance.file.name, exc)
        Document.objects.filter(pk=instance.pk).update(status="failed", error_message=str(exc))
        matcher.rebuild_index()
        return

    chunks = chunk_text(text)
    if not chunks:
        Document.objects.filter(pk=instance.pk).update(
            status="processed",
            error_message="No text could be extracted from this document.",
        )
        matcher.rebuild_index()
        return

    DocumentChunk.objects.bulk_create(
        DocumentChunk(document=instance, order=i, text=chunk) for i, chunk in enumerate(chunks)
    )
    Document.objects.filter(pk=instance.pk).update(status="processed", error_message="")
    matcher.rebuild_index()


@receiver(post_delete, sender=Document)
def reindex_after_delete(sender, instance, **kwargs):
    matcher.rebuild_index()
