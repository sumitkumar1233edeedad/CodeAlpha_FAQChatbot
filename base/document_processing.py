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
        trailing = groups.pop()
        groups[-1] = f"{groups[-1]} {trailing}"

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
