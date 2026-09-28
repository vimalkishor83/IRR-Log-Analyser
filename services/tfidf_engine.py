"""
tfidf_engine.py
---------------
Builds a search index so the recommendation engine can find similar
past incidents quickly.

How it works (simple version):
  1. Every incident / KB article / knowledge entry is turned into a
     bag of words (TF-IDF vector).
  2. When a user searches, their query is also turned into a vector.
  3. We compare the query vector against every document vector using
     cosine similarity — higher score = more similar.

The index lives in memory. Call retrain() after new data is imported.
"""

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# These three variables hold the trained index.
# They start as None/empty and are filled by retrain().
_vectorizer = None   # learns the vocabulary and IDF weights
_matrix     = None   # TF-IDF vectors for every document
_documents  = []     # metadata for each document (same order as _matrix rows)


# ── Training ──────────────────────────────────────────────────────────────────

def retrain(incidents, kb_articles, knowledge_entries):
    """
    Build the index from scratch using the data provided.
    Call this after importing incidents or adding knowledge entries.
    Returns the number of documents indexed.
    """
    global _vectorizer, _matrix, _documents

    texts     = []  # raw text for each document
    documents = []  # metadata for each document

    for inc in incidents:
        texts.append(_join(
            inc.incident_number or "",
            inc.error_description or "",
            inc.exception_message or "",
            inc.root_cause or "",
        ))
        documents.append({
            "source":           "Historical Incident",
            "incident_number":  inc.incident_number,
            "resolution":       inc.resolution       or "",
            "root_cause":       inc.root_cause       or "",
            "assignment_group": inc.assignment_group or "",
            "success_count":    inc.success_count    or 1,
            "reason":           "Similar historical incident",
        })

    for article in kb_articles:
        texts.append(_join(
            article.title         or "",
            article.error_pattern or "",
            article.root_cause    or "",
        ))
        documents.append({
            "source":           "KB Article",
            "incident_number":  "KB",
            "resolution":       article.resolution       or "",
            "root_cause":       article.root_cause       or "",
            "assignment_group": article.assignment_group or "",
            "success_count":    1,
            "reason":           "Matched KB article",
        })

    for entry in knowledge_entries:
        texts.append(_join(
            entry.pattern    or "",
            entry.meaning    or "",
            entry.resolution or "",
        ))
        documents.append({
            "source":           "Knowledge Repository",
            "incident_number":  "Manual Knowledge",
            "resolution":       entry.resolution       or "",
            "root_cause":       entry.meaning          or "",
            "assignment_group": entry.assignment_group or "",
            "success_count":    entry.frequency        or 1,
            "reason":           "Matched SME knowledge entry",
        })

    if not texts:
        _vectorizer = None
        _matrix     = None
        _documents  = []
        return 0

    _vectorizer = TfidfVectorizer(min_df=1, stop_words="english", ngram_range=(1, 2))
    _matrix     = _vectorizer.fit_transform(texts)
    _documents  = documents
    return len(documents)


# ── Searching ─────────────────────────────────────────────────────────────────

def search(query_text, top_n=10):
    """
    Find the most similar documents for a query string.
    Returns a list of dicts with similarity score (0-100) and document info.
    Returns [] if the index has not been trained yet.
    """
    if _vectorizer is None or _matrix is None:
        return []

    if not query_text or not query_text.strip():
        return []

    query_vector = _vectorizer.transform([query_text])
    scores       = cosine_similarity(query_vector, _matrix).flatten()

    # Sort indices highest-score-first, take top N
    top_indices = scores.argsort()[::-1][:top_n]

    results = []
    for idx in top_indices:
        score = float(scores[idx])
        if score <= 0:
            break
        doc = dict(_documents[idx])
        doc["similarity"] = round(score * 100, 2)
        results.append(doc)

    return results


def is_trained():
    """Return True if the index is ready to use."""
    return _vectorizer is not None


def document_count():
    """Return how many documents are in the index."""
    return len(_documents)


# ── Internal helper ───────────────────────────────────────────────────────────

def _join(*parts):
    """Combine several text fields into one string, skipping empty ones."""
    return " ".join(p.strip() for p in parts if p and p.strip())
