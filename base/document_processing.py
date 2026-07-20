import os

from docx import Document as DocxDocument
from pypdf import PdfReader

MIN_CHUNK_LENGTH = 30


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


def chunk_text(text, min_length=MIN_CHUNK_LENGTH):
    """Splits text into paragraph chunks, dropping any shorter than min_length characters."""
    raw_chunks = [c.strip() for c in text.split("\n\n")]
    return [c for c in raw_chunks if len(c) >= min_length]
