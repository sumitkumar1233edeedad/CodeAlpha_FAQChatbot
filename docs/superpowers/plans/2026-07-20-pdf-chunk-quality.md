# PDF Chunk Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce chunk size/dilution for long paragraphs (mainly PDF pages, which currently become one giant chunk each) so single-fact questions against dense documents reliably score above the matcher's threshold.

**Architecture:** `base/document_processing.py`'s `chunk_text()` keeps its existing paragraph-level (`"\n\n"`) split, but any resulting paragraph over `MAX_CHUNK_LENGTH` (200 chars) gets further split by sentence (via `nltk.sent_tokenize`) and greedily regrouped into smaller sub-chunks. All chunks also get whitespace-normalized (collapsing embedded newlines/extra spaces to single spaces) before the length checks.

**Tech Stack:** Django (existing), `nltk` (existing dependency, already used by `base/matcher.py` — this task adds its own self-contained `punkt`/`punkt_tab` data check rather than relying on import order).

## Global Constraints

- Changes are contained entirely to `base/document_processing.py` and its tests. No changes to `extract_text()`, `base/matcher.py`, `base/signals.py`, `MATCH_THRESHOLD` (0.28), or the DB schema.
- `MIN_CHUNK_LENGTH` stays 30 (unchanged) — applied as the final filter after sub-splitting, same as today.
- New constant `MAX_CHUNK_LENGTH = 200` — chunks at or under this length are left exactly as today's behavior; longer ones get sentence-split.
- A single sentence longer than `MAX_CHUNK_LENGTH` is kept whole rather than split mid-sentence.
- A trailing sentence-group shorter than `MIN_CHUNK_LENGTH` is folded into the previous group rather than emitted as its own tiny chunk (avoids silently losing content to the min-length filter).
- All chunks get whitespace-normalized (any run of whitespace, including embedded newlines, collapsed to a single space) before length checks — this also fixes matched answers showing raw `\n` characters in the chat UI.
- Existing `ChunkTextTests` fixtures (`test_splits_on_paragraph_breaks`, `test_drops_short_chunks`, `test_no_paragraph_breaks_returns_single_chunk`) must continue to pass unmodified — all their fixture text is well under 200 chars, so they exercise the unchanged short-chunk path.
- Full suite (`python manage.py test`) must pass with pristine output (currently 18/18; this task adds 3 more).

---

### Task 1: Sentence-level sub-chunking for long paragraphs

**Files:**
- Modify: `base/document_processing.py`
- Modify: `base/tests/test_document_processing.py`

**Interfaces:**
- Consumes: nothing new from other modules — `nltk` is already a project dependency (see `base/matcher.py`'s existing `nltk.download`-if-missing pattern, which this task mirrors independently).
- Produces: `chunk_text(text, min_length=MIN_CHUNK_LENGTH, max_length=MAX_CHUNK_LENGTH) -> list[str]` (extends the existing signature with a new `max_length` keyword argument; existing callers like `base/signals.py`'s `chunk_text(text)` are unaffected since both new/old params have defaults). `MAX_CHUNK_LENGTH = 200` (new module constant, importable alongside the existing `MIN_CHUNK_LENGTH`).

- [ ] **Step 1: Write the failing tests**

Add these three test methods to the existing `ChunkTextTests` class in `base/tests/test_document_processing.py` (leave the existing three test methods in that class untouched), and update the top import line to also pull in `MAX_CHUNK_LENGTH`:

Change:
```python
from base.document_processing import chunk_text, extract_text
```
to:
```python
from base.document_processing import MAX_CHUNK_LENGTH, chunk_text, extract_text
```

Then add to `ChunkTextTests`:

```python
    def test_long_paragraph_splits_into_sentence_chunks(self):
        text = (
            "The company reported strong results across all business units this year. "
            "Revenue grew steadily due to increased customer demand in urban markets. "
            "Operating costs were kept under control through efficiency programs. "
            "Management expects continued growth in the coming fiscal year."
        )
        self.assertGreater(len(text), MAX_CHUNK_LENGTH)  # sanity check: fixture must trigger the split path

        result = chunk_text(text)

        self.assertGreater(len(result), 1)
        for chunk in result:
            self.assertLessEqual(len(chunk), MAX_CHUNK_LENGTH)
        joined = " ".join(result)
        self.assertIn("Revenue grew steadily", joined)
        self.assertIn("Management expects continued growth", joined)

    def test_single_long_sentence_kept_whole(self):
        text = (
            "This is one single very long run on sentence without any period "
            "in the middle that just keeps going and going through many many "
            "words until it finally reaches its very end without ever giving "
            "the sentence tokenizer a chance to split it into smaller pieces"
        )
        self.assertGreater(len(text), MAX_CHUNK_LENGTH)  # sanity check: fixture must trigger the split path

        result = chunk_text(text)

        self.assertEqual(result, [text])

    def test_normalizes_internal_whitespace(self):
        text = "This   paragraph has\nirregular   whitespace\nand line breaks  in the middle of it."

        result = chunk_text(text)

        self.assertEqual(
            result,
            ["This paragraph has irregular whitespace and line breaks in the middle of it."],
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test base.tests.test_document_processing -v 2`
Expected: FAIL — `ImportError: cannot import name 'MAX_CHUNK_LENGTH' from 'base.document_processing'` (the constant doesn't exist yet).

- [ ] **Step 3: Implement the sub-chunking logic**

Replace `base/document_processing.py` in full:

```python
import os
import re

import nltk
from docx import Document as DocxDocument
from nltk.tokenize import sent_tokenize
from pypdf import PdfReader

MIN_CHUNK_LENGTH = 30
MAX_CHUNK_LENGTH = 200

# Make sure the required NLTK data is available (safe to call repeatedly; no-op if already downloaded)
for _pkg in ("punkt", "punkt_tab"):
    try:
        nltk.data.find(f"tokenizers/{_pkg}")
    except LookupError:
        nltk.download(_pkg, quiet=True)


def extract_text(document):
    """Extracts raw text from a Document's uploaded file, based on its file extension."""
    ext = os.path.splitext(document.file.name)[1].lower()

    if ext == ".txt":
        with document.file.open("rb") as f:
            return f.read().decode("utf-8", errors="ignore")

    if ext == ".pdf":
        with document.file.open("rb") as f:
            reader = PdfReader(f)
            return "\n\n".join(page.extract_text() or "" for page in reader.pages)

    if ext == ".docx":
        with document.file.open("rb") as f:
            docx_doc = DocxDocument(f)
            return "\n\n".join(p.text for p in docx_doc.paragraphs)

    raise ValueError(f"Unsupported file type: {ext}")


def _normalize_whitespace(text):
    """Collapses any run of whitespace (including embedded newlines from PDF
    line-wrapping) into a single space."""
    return re.sub(r"\s+", " ", text).strip()


def _split_into_sentence_groups(text, max_length, min_length):
    """Splits text into sentences and greedily regroups them into chunks no
    longer than max_length where possible. A single sentence longer than
    max_length is kept whole rather than split mid-sentence. A trailing
    group shorter than min_length is folded into the previous group instead
    of being emitted as its own tiny fragment."""
    sentences = sent_tokenize(text)
    if not sentences:
        return []

    groups = [sentences[0]]
    for sentence in sentences[1:]:
        candidate = f"{groups[-1]} {sentence}"
        if len(candidate) <= max_length:
            groups[-1] = candidate
        else:
            groups.append(sentence)

    if len(groups) > 1 and len(groups[-1]) < min_length:
        groups[-2] = f"{groups[-2]} {groups.pop()}"

    return groups


def chunk_text(text, min_length=MIN_CHUNK_LENGTH, max_length=MAX_CHUNK_LENGTH):
    """Splits text into paragraph chunks. Paragraphs longer than max_length
    are further split into sentence-level sub-chunks so no single chunk mixes
    too many unrelated sentences. Drops any resulting chunk shorter than
    min_length characters."""
    raw_paragraphs = [_normalize_whitespace(p) for p in text.split("\n\n")]

    chunks = []
    for paragraph in raw_paragraphs:
        if not paragraph:
            continue
        if len(paragraph) <= max_length:
            chunks.append(paragraph)
        else:
            chunks.extend(_split_into_sentence_groups(paragraph, max_length, min_length))

    return [c for c in chunks if len(c) >= min_length]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python manage.py test base.tests.test_document_processing -v 2`
Expected: `Ran 10 tests ... OK` (7 existing + 3 new)

- [ ] **Step 5: Run the full test suite to check for regressions**

Run: `python manage.py test -v 2`
Expected: `Ran 21 tests ... OK` (18 existing + 3 new), pristine output (the existing intentional `logger.warning` line from the unsupported-file-type signal test is expected and fine, same as before this task).

- [ ] **Step 6: Commit**

```bash
git add base/document_processing.py base/tests/test_document_processing.py
git commit -m "Split long paragraphs into sentence-level chunks to reduce TF-IDF dilution"
```
