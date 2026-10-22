"""Recognize generic file summaries without turning named topics into overviews."""
import re

from backend.ai.response_request import is_format_followup


def generic_material_summary(question):
    """Only a whole-file task and presentation modifiers qualify.

    The broader retrieval overview detector also accepts requests with topical
    restrictions. Those still need a semantic intent judge; this test is narrow.
    """
    parts = re.split(r'\n(?:Answer format requested now|Follow-up request):', question)
    if any(not is_format_followup(part.strip()) for part in parts[1:]):
        return False
    text = ' '.join(parts[0].casefold().split()).strip(' .!?')
    text = re.sub(r'^(?:(?:please|can you|could you|would you)\s+)+', '', text)
    document = (r'(?:(?:the|my|this|that|these|those|selected|uploaded|attached|entire|whole|full)\s+)*'
                r'(?:pptx?|powerpoint(?: presentation)?|presentation|slides?|slide deck|'
                r'pdf|documents?|files?|material|lecture|textbook|video|audio|recording|it|this)\b')
    patterns = [
        r'(?:summari[sz]e|explain|describe)\s+(?:about\s+)?' + document,
        r'(?:(?:give|provide|write)\s+(?:me\s+)?(?:a\s+)?)?'
        r'(?:brief\s+|short\s+|detailed\s+)?(?:summary|overview)\s+(?:of|for)\s+' + document,
        r'what\s+(?:is|are)\s+' + document + r'\s+(?:about|regarding)\b',
        r'what\s+(?:does|do)\s+' + document + r'\s+(?:cover|contain)\b',
        r'(?:(?:give|provide|write)\s+(?:me\s+)?(?:a\s+)?)?(?:summary|overview)\b',
    ]
    for pattern in patterns:
        match = re.match(pattern, text)
        if not match:
            continue
        remaining = text[match.end():].strip(' .!?')
        if not remaining or is_format_followup(remaining):
            return True
    return False
