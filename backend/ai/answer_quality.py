"""Language and relevance boundaries for tutoring; originals stay unchanged."""
import re

CJK = re.compile(r'[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uac00-\ud7af]')


def english_requested(question: str) -> bool:
    if re.search(r'\b(?:answer|reply|respond|explain|write|translate)\b.{0,35}\b(?:in|into|to)\s+(?:Chinese|Mandarin|Japanese|Korean|Hindi|Tamil|Telugu|Bengali|Marathi|French|Spanish)\b', question, re.I):
        return False
    return not bool(CJK.search(question))


def wrong_script(answer: str, question: str) -> bool:
    return english_requested(question) and bool(CJK.search(answer or ''))


def source_sentences(text: str, question: str = '') -> list[str]:
    """Select intact sentences; never delete characters inside a quoted sentence."""
    if not isinstance(text,str): return []
    result=[]
    for sentence in re.split(r'\n+|(?<=[.!?])\s+(?=[A-Z“"(])',text):
        sentence=sentence.strip()
        if not 8 <= len(sentence.split()) <= 90 or len(sentence)>700: continue
        if wrong_script(sentence,question): continue
        if '?' in sentence or re.match(r'^(?:[a-dA-D][.)]|Image \d+ recognized|Slide \d+:|Page \d+ recognized)',sentence): continue
        if not re.search(r'\b(?:is|are|was|were|means|refers|provides?|contains?|maintain\w*|add\w*|los\w*|form\w*|bind\w*|result\w*|can|must|requires?|support\w*|use\w*|play\w*|determine\w*)\b',sentence,re.I): continue
        if sentence not in result:result.append(sentence)
    return result


def compact_evidence(question: str, sources: list[dict], overview=False) -> list[dict]:
    from backend.ai.grounded_expansion import topic_terms
    terms=set(topic_terms(question)); candidates=[]
    for number,source in enumerate(sources,1):
        for sentence in source_sentences(source.get('content',''),question):
            words=set(re.findall(r'[a-z]{3,}',sentence.casefold()))
            overlap=terms & words
            if not overview and not overlap:continue
            score=len(overlap)*5
            if any(re.match(re.escape(term)+r'\s+(?:is|means|refers)\b',sentence,re.I) for term in terms):score+=10
            candidates.append((score,number,sentence))
    picked=[];seen=set();locations=set()
    for _,number,text in sorted(candidates,key=lambda row:-row[0]):
        key=' '.join(text.casefold().split())
        if key in seen:continue
        source=sources[number-1];location=(source.get('source_id'),source.get('page'),source.get('slide'),source.get('timestamp_start'))
        if overview and location in locations:continue
        seen.add(key);locations.add(location);picked.append({'citation':number,'text':text})
        if len(picked)==4:break
    return picked
