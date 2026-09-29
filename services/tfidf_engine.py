"""Builds a TF-IDF search index so recommendations can find similar past incidents."""

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

_vectorizer = None   # learns the vocabulary and IDF weights
_matrix     = None   # TF-IDF vectors for every document
_documents  = []     # metadata for each document (same order as _matrix rows)


def retrain(incidents, kb_articles, knowledge_entries):
    """Rebuild the index from scratch. Returns the number of documents indexed."""
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


def search(query_text, top_n=10):
    """Return the most similar documents for a query, with similarity 0-100."""
    if _vectorizer is None or _matrix is None:
        return []

    if not query_text or not query_text.strip():
        return []

    query_vector = _vectorizer.transform([query_text])
    scores       = cosine_similarity(query_vector, _matrix).flatten()
    top_indices  = scores.argsort()[::-1][:top_n]

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
    return _vectorizer is not None


def document_count():
    return len(_documents)


def _join(*parts):
    return " ".join(p.strip() for p in parts if p and p.strip())
