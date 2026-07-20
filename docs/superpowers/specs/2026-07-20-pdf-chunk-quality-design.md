# PDF Chunk Quality — Design

**Date:** 2026-07-20
**Status:** Approved

## Problem

`base/document_processing.py`'s `extract_text()` joins each PDF page's raw
`pypdf`-extracted text with `"\n\n"`, and `chunk_text()` only splits on that
same delimiter. `pypdf` rarely produces real `"\n\n"` paragraph breaks
*within* a page, so in practice each stored `DocumentChunk` for a PDF ends up
being an entire page: headers, tables, and several unrelated paragraphs all
mashed into one large blob.

This dilutes TF-IDF relevance. A question about one specific fact buried in a
dense page (e.g. "By how much did M-Pesa revenue grow?") scores below
`MATCH_THRESHOLD` (0.28) even though the fact is present in the corpus,
because the chunk's vector is dominated by unrelated surrounding text.
Verified live: that exact question scored 0.245 against a real annual-report
PDF upload — just under threshold.

TXT and DOCX are not affected the same way: DOCX paragraphs come from
`python-docx`'s own paragraph objects (already short), and typical TXT files
have real blank-line breaks.

## Goal

Reduce chunk size/dilution for long paragraphs (regardless of source format)
so single-fact questions against dense PDFs reliably score above
`MATCH_THRESHOLD`, without changing extraction code, the matcher, the
threshold, or the DB schema.

## Non-goals

- Not attempting to strip repeated boilerplate (page headers/footers) via
  cross-page frequency analysis — sub-chunking already isolates real
  sentences from adjacent noise without needing that.
- Not guaranteeing perfect isolation for punctuation-free PDF "callout" text
  (e.g. stat blocks with no periods) — `sent_tokenize` splits on sentence
  punctuation, so such text may still be grouped with a neighboring
  fragment. This is an accepted, honest limitation, not a target to solve
  here.
- No change to `MATCH_THRESHOLD`, `MIN_CHUNK_LENGTH`, extraction functions,
  the matcher, or signals.

## Design

All changes are contained to `base/document_processing.py`.

### New constant

```python
MAX_CHUNK_LENGTH = 200
```

Chunks at or under this length are left exactly as today. Chunks over this
length are further split (see below). 200 chars targets roughly 1-2
sentences per resulting chunk, matching the "tight" granularity chosen for
this fix — precise enough for single-fact lookups.

### Updated `chunk_text()`

Pipeline, per paragraph (i.e. per `"\n\n"`-delimited raw chunk):

1. Strip and normalize internal whitespace — collapse any run of whitespace
   (including embedded newlines from PDF line-wrapping) into a single space.
   This also fixes a secondary issue noticed while testing: matched answers
   could show up in the chat UI with raw embedded `\n` characters, which
   looks broken to an end user.
2. If the normalized chunk is `<= MAX_CHUNK_LENGTH`, keep it as-is (this is
   the existing behavior for typical DOCX/TXT paragraphs — unchanged).
3. If it's longer, tokenize into sentences with `nltk.sent_tokenize` and
   greedily regroup consecutive sentences into sub-chunks, each kept under
   `MAX_CHUNK_LENGTH` where possible. A single sentence that alone exceeds
   `MAX_CHUNK_LENGTH` is kept whole rather than split mid-sentence.
4. Apply the existing `MIN_CHUNK_LENGTH` (30) filter across all resulting
   chunks, as today. The grouping algorithm avoids producing tiny trailing
   sentence-fragment chunks by merging a leftover sentence into the previous
   group rather than emitting it as a separate under-sized chunk.

### NLTK data availability

`document_processing.py` currently has no NLTK dependency. `sent_tokenize`
needs the `punkt`/`punkt_tab` data that `matcher.py` already
downloads-if-missing at import time — but `document_processing.py` must not
rely on import order elsewhere in the app to guarantee that data is present.
It will run its own equivalent "download if missing" check for `punkt`/
`punkt_tab`, mirroring the existing pattern in `matcher.py`, so the module is
self-contained.

### Example

A ~2000-character PDF page today becomes one `DocumentChunk`. After this
change, it becomes roughly 10-15 smaller chunks, each ~1-2 sentences,
normalized to clean single-spaced text. A short DOCX paragraph like *"Our
refund window closes exactly fourteen days after purchase confirmation."*
(77 chars) is unaffected — stored exactly as today.

## Testing

New/updated tests in `base/tests/test_document_processing.py`
(`ChunkTextTests`):

- A long paragraph (well over 200 chars, multiple real sentences) splits
  into multiple chunks, each `<= MAX_CHUNK_LENGTH` (with a small tolerance
  for the unsplittable-long-sentence case below).
- A single sentence longer than `MAX_CHUNK_LENGTH` is kept whole as its own
  chunk (not truncated or split mid-sentence).
- Whitespace normalization: a chunk with embedded newlines/multiple spaces
  comes out with normalized single spaces.
- Existing tests (`test_splits_on_paragraph_breaks`, `test_drops_short_chunks`,
  `test_no_paragraph_breaks_returns_single_chunk`) continue to pass
  unmodified — their fixture text is well under 200 chars, so they exercise
  the unchanged short-chunk path.

No changes needed to `test_signals.py`, `test_matcher.py`, or `test_admin.py`
— none of their fixtures approach `MAX_CHUNK_LENGTH`, so their behavior is
unaffected. Full suite (`python manage.py test`) must still pass at 18/18
(or higher, with the new tests added) with pristine output.
