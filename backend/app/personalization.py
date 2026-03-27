"""
Lightweight keyword-based personalization for the trending feed.

Given a human's recently liked post captions, we extract weighted keywords
and compute a boost multiplier for each candidate post.  Posts whose captions
share words with liked posts score higher.
"""

import re
from collections import Counter

_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "have", "will",
    "are", "was", "were", "been", "your", "its", "our", "their", "into",
    "onto", "over", "under", "between", "through", "about", "after",
    "before", "which", "where", "when", "there", "here", "what", "who",
    "not", "but", "can", "all", "any", "each", "more", "most", "also",
    "just", "like", "than", "then", "some", "such", "very", "well",
    "only", "even", "both", "too", "out", "one", "two", "three",
    "they", "them", "these", "those", "her", "his", "him", "she",
    "has", "had", "does", "did", "would", "could", "should", "may",
    "might", "every", "nothing", "everything", "something", "while",
    "around", "still", "always", "never", "makes", "made", "make",
}


def extract_keywords(captions: list[str | None]) -> Counter:
    """
    Tokenise captions and count word frequency, filtering short words and
    stopwords.  The resulting Counter is used as a weighted interest profile.
    """
    counts: Counter = Counter()
    for cap in captions:
        if not cap:
            continue
        words = re.findall(r"[a-z]{4,}", cap.lower())
        counts.update(w for w in words if w not in _STOPWORDS)
    return counts


def personalization_boost(caption: str | None, keywords: Counter) -> float:
    """
    Return a multiplier >= 1.0 representing how well ``caption`` matches the
    user's interest keywords.

    Scoring: each matched word contributes its frequency weight * 0.3, capped
    at a 2x total boost.  Zero-overlap posts are returned unchanged (1.0).
    """
    if not caption or not keywords:
        return 1.0
    words = re.findall(r"[a-z]{4,}", caption.lower())
    score = sum(keywords[w] for w in words if w in keywords)
    return 1.0 + min(score * 0.3, 1.0)
