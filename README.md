# CodeAlpha_FAQChatbot (Django version)

A rule-based FAQ chatbot built with Django. Matches user questions to a curated
FAQ dataset using NLTK preprocessing + TF-IDF + cosine similarity — no external
API or paid LLM required.

## Features
- Real-time chat UI (AJAX, no page reloads)
- Quick-start suggestion chips for common questions
- **1000 Q&A pairs** across ~84 distinct intents (enrollment, billing, certificates,
  account, technical support, instructor tools, accessibility, and more), with
  multiple natural phrasings per intent for more robust matching
- NLP preprocessing: tokenization, lowercasing, stopword removal (NLTK)
- TF-IDF (unigrams + bigrams) + cosine similarity matching (scikit-learn)
- Graceful fallback message when no confident match is found (score threshold)

## Tech Stack
- Python 3 / Django
- NLTK (tokenization, stopwords)
- scikit-learn (TfidfVectorizer, cosine_similarity)
- Vanilla JS (Fetch API) for the chat interface


## Setup & Run

```bash
python -m venv venv
source venv/bin/activate      # venv\Scripts\activate on Windows

pip install -r requirements.txt
python -c "import nltk; nltk.download('punkt'); nltk.download('punkt_tab'); nltk.download('stopwords')"

python manage.py migrate
python manage.py runserver
```

Open **http://127.0.0.1:8000/** and start chatting.

## How It Works
1. On server start, `matcher.py` loads `faqs.json`, preprocesses every question
   (tokenize → lowercase → remove stopwords/punctuation), and builds a TF-IDF
   matrix once — so matching stays fast on every request.
2. When a user sends a message, the frontend POSTs it as JSON to `/ask/`.
3. `matcher.get_best_answer()` vectorizes the user's question, computes cosine
   similarity against every FAQ question, and returns the best match — or a
   fallback message if the best score is below `MATCH_THRESHOLD` (0.25).

## About the Dataset
`faqs.json` contains 1000 question/answer pairs built from ~84 real course-platform
intents (e.g. "reset my password", "request a refund", "become an instructor"),
each expressed as many natural phrasings ("How do I...", "Can I...", "Is there a way
to...", etc.) mapped to the same canonical answer. This gives the matcher far more
surface-form coverage than 84 raw questions would, without diluting answer quality.

**Known limitation:** TF-IDF is keyword-based. A paraphrase using very different
vocabulary from anything in the dataset (e.g. "get my money back" instead of
"refund") can still mismatch, even with 1000 phrasings on file. This isn't a bug —
it's the ceiling of frequency-based matching. See "Possible Improvements" below.

## Customizing for Your Own Topic
Just edit `chatbot_app/faqs.json` with your own question/answer pairs — the
matching engine rebuilds itself automatically from that file on server start.
More pairs (30-50+) and more natural phrasing of questions = better matching.

## Possible Improvements
- Swap TF-IDF for `sentence-transformers` embeddings for genuine semantic matching
  (would fix the "money back" vs "refund" style mismatches)
- Log unanswered / low-confidence questions to identify FAQ gaps
- Add multi-turn context (remember previous messages in the conversation)

---
Built for the CodeAlpha AI Internship — Task 2: Chatbot for FAQs.
