import json
import os
import string

import nltk
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
# Note: TF-IDF is keyword-based. A paraphrase using very different vocabulary from
# every training question (e.g. "money back" vs "refund") can still mismatch even
# with 1000 phrasings in the dataset. For stronger semantic matching, swap in
# sentence-transformers embeddings — see README "Possible Improvements".

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


# Build the TF-IDF matrix once, at import time, so every request reuses it
# ngram_range=(1,2) lets it match on short phrases ("money back") not just single words,
# which matters a lot now that there are hundreds of paraphrased questions per intent.
_processed_questions = [preprocess(q) for q in QUESTIONS]
_vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)
_faq_vectors = _vectorizer.fit_transform(_processed_questions)


def get_best_answer(user_question: str) -> dict:
    """Return the best-matching FAQ answer plus metadata (score, matched question)."""
    processed = preprocess(user_question)
    if not processed.strip():
        return {
            "answer": "Could you type an actual question? I didn't catch anything there.",
            "matched_question": None,
            "score": 0.0,
        }

    user_vector = _vectorizer.transform([processed])
    similarities = cosine_similarity(user_vector, _faq_vectors).flatten()
    best_idx = similarities.argmax()
    best_score = float(similarities[best_idx])

    if best_score < MATCH_THRESHOLD:
        return {
            "answer": "Sorry, I don't have an answer for that yet. Try rephrasing, "
                      "or contact support@example.com for help.",
            "matched_question": None,
            "score": best_score,
        }

    return {
        "answer": ANSWERS[best_idx],
        "matched_question": QUESTIONS[best_idx],
        "score": best_score,
    }
