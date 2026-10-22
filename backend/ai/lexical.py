"""Small, deterministic lexical signals; a topic match is not factual coverage."""
import re
import unicodedata

from backend.ai.grounded_expansion import topic_terms


def normalize(text):
    text = unicodedata.normalize("NFKC", text).casefold()
    for symbol, name in (("β", " beta "), ("α", " alpha "), ("γ", " gamma ")):
        text = text.replace(symbol, name)
    return " ".join(re.findall(r"[a-z0-9]+", text))


def terms_for(question):
    # Conservative plural normalization lets 'proteins' find 'protein' as well
    # as the reverse. SQL and the false-absence guard use the same roots.
    terms = topic_terms(normalize(question))
    return list(dict.fromkeys(t[:-1] if len(t) > 4 and t.endswith("s")
                              and not t.endswith(("ss", "is", "us")) else t for t in terms))


def mentions_topic(question, text):
    terms = terms_for(question)
    words = normalize(text).split()
    return bool(terms) and all(any(w == t or w == t + "s" for w in words) for t in terms)


def topic_excerpt(question, text, max_chars=900):
    """Select an exact local excerpt, never join distant tokens into a claim."""
    terms = terms_for(question)
    if not terms:
        return None
    # A heading and adjacent diagram labels can be evidence of topic presence.
    lines = text.splitlines()
    for index, line in enumerate(lines):
        block = "\n".join(lines[index:index + 5]).strip()
        if len(block) <= max_chars and mentions_topic(question, block):
            return block
    return None
