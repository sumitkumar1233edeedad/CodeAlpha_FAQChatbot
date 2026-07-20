import json
import os
import string

import nltk
from django.db.utils import OperationalError, ProgrammingError
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Make sure the required NLTK data is available (safe to call repeatedly; no-op if already downloaded)
for pkg in ("punkt", "punkt_tab", "stopwords"):
    try:
        nltk.data.find(
            f"tokenizers/{pkg}" if "punkt" in pkg else f"corpora/{pkg}"
        )
    except LookupError:
        nltk.download(pkg, quiet=True)

STOP_WORDS = set(stopwords.words("english"))
MATCH_THRESHOLD = 0.28  # below this similarity score, we admit we don't know the answer

FAQ_PATH = os.path.join(os.path.dirname(__file__), "faqs.json")

with open(FAQ_PATH, "r", encoding="utf-8") as f:
    FAQ_DATA = json.load(f)

QUESTIONS = [item["question"] for item in FAQ_DATA]
ANSWERS = [item["answer"] for item in FAQ_DATA]


def preprocess(text: str) -> str:
    """Lowercase, tokenize, strip punctuation and stopwords."""
    tokens = word_tokenize(text.lower())
    tokens = [t for t in tokens if t not in string.punctuation and t not in STOP_WORDS]
    return " ".join(tokens)


# Rebuilt by rebuild_index() whenever a Document is added/removed, so the
# matcher stays current without needing a server restart.
_vectorizer = None
_corpus_vectors = None
_corpus_answers = []
_corpus_matched_questions = []
_corpus_sources = []


def _document_chunk_entries():
    """Returns (text, answer, matched_question, source) tuples for every DocumentChunk row."""
    from .models import DocumentChunk

    try:
        chunks = list(DocumentChunk.objects.select_related("document").all())
    except (OperationalError, ProgrammingError):
        # The table may not exist yet -- e.g. during the initial `migrate`,
        # or when this module is imported for test collection before the
        # test database has been built.
        return []

    entries = []
    for chunk in chunks:
        source = chunk.document.title or os.path.basename(chunk.document.file.name)
        entries.append((chunk.text, chunk.text, None, source))
    return entries


def rebuild_index():
    """Rebuilds the TF-IDF index from FAQ_DATA plus every DocumentChunk in the database."""
    global _vectorizer, _corpus_vectors, _corpus_answers, _corpus_matched_questions, _corpus_sources

    texts, answers, matched_questions, sources = [], [], [], []

    for question, answer in zip(QUESTIONS, ANSWERS):
        texts.append(question)
        answers.append(answer)
        matched_questions.append(question)
        sources.append(None)

    for text, answer, matched_question, source in _document_chunk_entries():
        texts.append(text)
        answers.append(answer)
        matched_questions.append(matched_question)
        sources.append(source)

    processed = [preprocess(t) for t in texts]
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)
    vectors = vectorizer.fit_transform(processed)

    _vectorizer = vectorizer
    _corpus_vectors = vectors
    _corpus_answers = answers
    _corpus_matched_questions = matched_questions
    _corpus_sources = sources


def get_best_answer(user_question: str) -> dict:
    """Return the best-matching answer (FAQ or document chunk) plus metadata."""
    processed = preprocess(user_question)
    if not processed.strip():
        return {
            "answer": "Could you type an actual question? I didn't catch anything there.",
            "matched_question": None,
            "score": 0.0,
        }

    user_vector = _vectorizer.transform([processed])
    similarities = cosine_similarity(user_vector, _corpus_vectors).flatten()
    best_idx = similarities.argmax()
    best_score = float(similarities[best_idx])

    if best_score < MATCH_THRESHOLD:
        return {
            "answer": "Sorry, I don't have an answer for that yet. Try rephrasing, "
                      "or contact support@example.com for help.",
            "matched_question": None,
            "score": best_score,
        }

    answer = _corpus_answers[best_idx]
    source = _corpus_sources[best_idx]
    if source:
        answer = f"{answer} (Source: {source})"

    return {
        "answer": answer,
        "matched_question": _corpus_matched_questions[best_idx],
        "score": best_score,
    }


rebuild_index()
