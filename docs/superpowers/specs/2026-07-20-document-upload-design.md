# Document Upload for FAQ Chatbot — Design

**Date:** 2026-07-20
**Status:** Approved

## Problem

The chatbot currently answers only from `base/faqs.json`, a hand-curated list of
Q&A pairs. There's no way to add knowledge from real documents (PDF/DOCX/TXT)
without manually converting their content into Q&A pairs.

## Goal

Let an admin upload a document via Django admin. The system extracts its text,
splits it into chunks, and makes those chunks searchable by the existing
TF-IDF matcher — so the chatbot can answer questions using document content,
not just `faqs.json`.

## Non-goals

- No custom (non-admin) upload UI.
- No OCR for scanned/image-only PDFs.
- No semantic/embedding-based search (stays TF-IDF, consistent with the
  existing matcher).
- No multi-tenant or per-user document scoping — single shared knowledge base.

## Data model

Two new models in `base/models.py`:

```python
class Document(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processed", "Processed"),
        ("failed", "Failed"),
    ]
    title = models.CharField(max_length=255, blank=True)
    file = models.FileField(upload_to="documents/")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    error_message = models.TextField(blank=True)

class DocumentChunk(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="chunks")
    text = models.TextField()
    order = models.PositiveIntegerField()
```

- `status`/`error_message` surface extraction failures in the admin list view
  instead of failing silently.
- `DocumentChunk.order` preserves original document order (not used for
  matching, but useful for debugging/inspection).

## Extraction & chunking

New module `base/document_processing.py`:

- `extract_text(document) -> str` — dispatches on file extension:
  - `.pdf` → `pypdf`
  - `.docx` → `python-docx`
  - `.txt` → plain read (UTF-8, errors="ignore")
  - Anything else → raises `ValueError("Unsupported file type: ...")`
- `chunk_text(text) -> list[str]` — splits on blank-line paragraph breaks,
  strips whitespace, and drops chunks shorter than a minimum length (default
  30 characters) to avoid indexing headers/page numbers/noise.

New dependencies added to `requirements.txt`: `pypdf`, `python-docx`.

## Upload flow & reindexing

1. Admin uploads a `Document` via `/admin/`.
2. A `post_save` signal on `Document` (registered in `base/apps.py`) runs:
   - `extract_text()` — on failure, sets `status="failed"`, `error_message=str(e)`,
     saves, and returns (no chunks created, no crash).
   - On success: deletes any existing chunks for this document (handles
     re-upload/replace-file case), creates new `DocumentChunk` rows via
     `chunk_text()`, sets `status="processed"`.
   - Calls `matcher.rebuild_index()` to fold the new chunks into the live
     TF-IDF index immediately — no server restart needed.
3. A `post_delete` signal on `Document` calls `matcher.rebuild_index()` after
   Django's cascade delete removes the chunks.
4. Signals guard against recursion (the save inside the handler uses
   `Document.objects.filter(pk=...).update(...)` rather than `.save()`, so it
   doesn't re-trigger `post_save`).

## Matcher integration

`matcher.py` changes from "build the TF-IDF matrix once at import time" to a
`rebuild_index()` function that:

1. Builds a combined corpus:
   - For each FAQ entry: matchable text = `question`, answer = `answer`,
     source = `None`.
   - For each `DocumentChunk`: matchable text = `chunk.text`, answer =
     `chunk.text` (same string — there's no separate "question" for a chunk),
     source = `chunk.document.title or chunk.document.file.name`.
2. Preprocesses all matchable texts, fits `TfidfVectorizer`, stores the
   fitted vectorizer + matrix + parallel answer/source lists as module-level
   state.
3. Runs once at import time (module load), and again whenever
   `rebuild_index()` is called by the signals above.

`get_best_answer()` behavior changes:
- If the winning corpus entry came from a document chunk, the returned
  `answer` string gets `" (Source: <source>)"` appended.
- Response dict gains no new required keys — existing frontend JS (which just
  renders `answer`) needs no changes.
- `matched_question` stays `None` for document-chunk matches (there's no
  literal "question" to show), same as the existing no-match fallback case.

## Admin UI

`base/admin.py` registers:
- `DocumentAdmin`: list view shows `title`, `uploaded_at`, `status`; read-only
  `error_message` shown on the detail page so failures are visible without
  digging into logs.
- `DocumentChunk` is not separately registered for editing (managed entirely
  through the signal pipeline) but is visible as a read-only inline on the
  `Document` admin page, for debugging what got indexed.

## Error handling

- Unsupported file extension or parse failure → caught in the signal handler,
  recorded on the model, does not raise/crash the admin save request.
- Empty extracted text (e.g., scanned PDF with no text layer) → produces zero
  chunks; `status="processed"` but with an `error_message` noting "no text
  extracted" so it's still distinguishable from a real failure.
- Concurrent uploads: out of scope — single-admin, low-frequency usage; no
  locking added around `rebuild_index()`.

## Testing

- Unit tests for `extract_text()` per file type using small fixture files
  under a test-only fixtures directory.
- Unit tests for `chunk_text()` covering: normal multi-paragraph text, text
  with no paragraph breaks, text that's all below the minimum chunk length.
- Integration test (Django `TestCase`): create a `Document` with fixture file
  content, assert `DocumentChunk` rows are created and `get_best_answer()`
  returns content from that document for a relevant question.
- Integration test: delete a `Document`, assert its chunks are gone and the
  matcher no longer returns them.
- Integration test: upload a corrupt/unsupported file, assert `status="failed"`
  and no unhandled exception propagates.
