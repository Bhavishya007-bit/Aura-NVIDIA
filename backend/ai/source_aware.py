"""Source-aware document tutoring over the authenticated RAG retriever adapter."""
import json
import logging
import re
from pathlib import Path

from pydantic import ValidationError

from backend.ai.answer_contract import (
    AnswerSection, CoverageDecision, SourceAwareFields, choose_depth, citation_ids,
)
from backend.ai.lexical import topic_excerpt
from backend.ai.answer_quality import evidence_text
from backend.ai.llm import LLMConnectionError, LLMResponseError
from backend.ai.long_summary import expand_summary
from backend.ai.summary_answer import SummaryDraft, SummaryDraftError, summary_contract, recover_summary
from backend.ai.response_request import response_request, resolve_format_followup, length_check, length_distance, word_count

log = logging.getLogger(__name__)
PROMPTS = Path(__file__).with_name("prompts") / "v1"


def prompt(name):
    return (PROMPTS / name).read_text(encoding="utf-8")


def _schema_errors(error):
    """Log schema paths/types without model text, input values or unknown field names."""
    if not isinstance(error, ValidationError):
        return None
    known = {"status", "covered_parts", "missing_parts", "reason", "ambiguous",
             "clarifying_question", "part", "citation_ids", "sentences", "text"}
    return {"count": error.error_count(), "errors": [
        {"path": [p if type(p) is int or p in known else "<field>" for p in item["loc"]],
         "type": item["type"]}
        for item in error.errors(include_input=False, include_context=False, include_url=False)[:8]
    ]}


class SourceAwareTutor:
    """Reuse citation verification and owned retrieval; never issue database queries here."""

    def __init__(self, rag, mode="intelligence", depth=None):
        if mode not in {"grounded", "intelligence"}:
            raise ValueError("Unsupported answer mode.")
        self.rag = rag
        self.mode = mode
        self.requested_depth = depth
        self.coverage_llm = rag.llm.for_task("coverage")
        self.conversation_context = []
        self.response_request = response_request('')
        self.context_limit = 24
        self.material_context = {'scope': 'sampled_passages'}
        self.selected_source_id = None

    @staticmethod
    def _unknown(reason):
        return CoverageDecision(status="unknown", reason=reason)

    def _judge(self, question, sources):
        try:
            data = self.coverage_llm.generate_json(
                json.dumps({"passages": [{"id": i, "text": s["content"][:6000]}
                                        for i, s in enumerate(sources, 1)], "question": question,
                            "conversation_context": self.conversation_context,
                            "output_schema": CoverageDecision.model_json_schema(),
                            "source_id_range": {"minimum": 1, "maximum": len(sources)}}),
                max_retries=1, system_prompt=prompt("coverage_judge.txt"),
            )
            return CoverageDecision.model_validate(data).check_citations(len(sources))
        except Exception as error:
            log.warning("coverage_check=unavailable error_type=%s schema_errors=%s",
                        type(error).__name__, _schema_errors(error))
            return self._unknown("Coverage checking is unavailable; absence has not been established.")

    def _merge(self, existing, incoming):
        combined, seen = [], set()
        for item in list(existing) + list(incoming):
            text = " ".join(evidence_text(item.chunk.content).split())
            key = (item.chunk.source_id, item.chunk.page, item.chunk.slide,
                   item.chunk.timestamp_start, text.casefold())
            if not text or key in seen:
                continue
            seen.add(key)
            combined.append(item)
            if len(combined) == self.context_limit:
                break
        return combined

    def _retrieve(self, question, scope, top_k, overview, broaden=False):
        results = []
        # A failed required retrieval is not evidence that a topic is absent.
        if overview:
            full_context = getattr(self.rag.retriever, 'document_context', None)
            if self.response_request['long_form'] and full_context:
                context = full_context(**scope, limit=self.context_limit)
                results = context['results']
                self.material_context = {k: v for k, v in context.items() if k != 'results'}
            else:
                results = self.rag.retriever.overview(**scope, limit=16)
        else:
            # Lexical evidence remains usable when the embedding service fails.
            # Reserve room for exact-topic headings and their same-slide labels.
            errors = []
            semantic, lexical = [], []
            try:
                semantic = self.rag.retriever.search(question, **scope, top_k=16 if broaden else max(6, top_k))
            except Exception as error:
                errors.append(error)
            if scope["source_id"] is not None:
                try:
                    lexical = self.rag.retriever.concept_context(question, **scope, limit=14 if broaden else 10)
                except Exception as error:
                    errors.append(error)
            results = self._merge(lexical, semantic)
            if errors:
                self.retrieval_incomplete = True
                log.warning("retrieval_branch=unavailable successful_candidates=%s", len(results))
                if not results:
                    raise errors[0]
        if broaden and scope["source_id"] is not None and not overview:
            # Reserve room for diverse locations before adding more ranked hits;
            # otherwise top-K candidates can crowd out the broader document scan.
            results = self._merge(results[:18], self._merge(
                self.rag.retriever.overview(**scope, limit=6), results[18:]))
        return self._merge([], results)

    def _source_answer(self, question, sources, decision, client, depth_policy, overview=False):
        if overview and self.response_request['long_form'] and hasattr(client, 'for_summary'):
            client = client.for_summary()
        payload = {"passages": [{"id": i, "text": s["content"][:6000]}
                                for i, s in enumerate(sources, 1)],
                   "supported_parts": [part.model_dump() for part in decision.covered_parts],
                   "missing_parts": decision.missing_parts,
                   "profile_style": self.rag.learning_style, "depth_policy": depth_policy,
                   "conversation_context": self.conversation_context,
                   "selected_material": self.rag.selected_source_name,
                   "response_request": self.response_request,
                   "material_context": self.material_context,
                   "question": question}
        if overview:
            payload['draft_contract'] = summary_contract(self.response_request, len(sources))
        validation = {"valid": False, "stage": "generation_unavailable"}
        checks = []
        best_checked = None
        for attempt in range(2):
            draft = None
            points = None
            try:
                if overview:
                    draft = client.generate_json(json.dumps(payload), max_retries=1,
                        system_prompt=prompt("summary_long.txt" if self.response_request['long_form'] else "summary_answer.txt"))
                    parsed = SummaryDraft.model_validate(draft)
                    log.info('summary_draft attempt=%s sentences=%s actual_words=%s target_words=%s',
                             attempt + 1, len(parsed.sentences),
                             word_count(' '.join(item.text for item in parsed.sentences)),
                             self.response_request['target_words'])
                    text = parsed.render(len(sources), self.response_request)
                    points = parsed.points(len(sources), self.response_request)
                else:
                    text = self.rag._normalize_citations(client.generate(
                        json.dumps(payload), max_retries=1, system_prompt=prompt("sourced_answer.txt")))
                intent_context = ({'scope': 'selected_material_overview',
                                   'source_id': self.selected_source_id} if overview and sources else None)
                validation = self.rag._validate_answer(text, sources, question,
                    structured_points=points, intent_context=intent_context)
                checks.append(validation)
                log.info("source_answer_check task=%s attempt=%s stage=%s valid=%s intent_method=%s",
                         "summary" if overview else "answer", attempt + 1,
                         validation.get("stage"), validation.get("valid") is True,
                         validation.get('question_validation', {}).get('method', 'semantic_judge'))
                if validation.get("valid") is True:
                    section = AnswerSection(kind="sourced", text=text, provenance="uploaded_material",
                                            verified=True, citation_ids=citation_ids(text))
                    length = length_check(text, self.response_request)
                    validation['length_validation'] = length
                    if length['valid']:
                        return section, validation
                    if best_checked is None or length_distance(length) < length_distance(best_checked[1]['length_validation']):
                        best_checked = (section, dict(validation))
                    payload['previous_draft'] = text
                    payload['feedback'] = {'length_validation': length,
                        'instruction': 'Revise the checked explanation to meet the requested word/sentence/paragraph targets using the supplied passages. Do not claim the full file is missing or pad with invented facts.'}
                    continue
                payload["previous_draft"] = text
                payload["feedback"] = self.rag._short_feedback(validation)
                if validation.get("stage") == "verification_unavailable":
                    break
            except Exception as error:
                code = (error.failure_code if isinstance(error, (SummaryDraftError, LLMResponseError, LLMConnectionError))
                        else 'schema_validation' if isinstance(error, ValidationError) else 'unexpected_error')
                log.warning("source_answer=unavailable task=%s attempt=%s error_type=%s failure_code=%s schema_errors=%s",
                            "summary" if overview else "answer", attempt + 1,
                            type(error).__name__, code, _schema_errors(error))
                validation = {"valid": False, "stage": "summary_draft_invalid" if overview and draft is not None
                              else "generation_unavailable", 'failure_code': code}
                checks.append(validation)
                if (overview and self.response_request['long_form'] and
                    isinstance(error, LLMResponseError) and error.failure_code == 'output_truncated'):
                    # Keep the existing two-attempt limit. Reserve the requested
                    # writing allowance plus measured reasoning, within the global cap.
                    if attempt == 0 and error.reasoning_tokens and hasattr(client, 'with_output_budget'):
                        client = client.with_output_budget(error.max_tokens + error.reasoning_tokens)
                    payload['feedback'] = ('The previous completion exhausted its output budget. '
                        'Produce the final supported answer directly in the required format. '
                        'Keep the requested length; omit planning and commentary.')
                elif overview and draft is not None:
                    # The model must see what needs repair; generic instructions
                    # previously discarded the draft and often elicited an empty list.
                    payload['previous_draft'] = draft
                    payload['feedback'] = {
                        'draft_error': error.feedback if isinstance(error, SummaryDraftError) else _schema_errors(error),
                        'instruction': ('Repair the previous draft using draft_contract and the original passages. '
                            'Keep supported teaching points, correct only invalid formatting or source IDs, '
                            'and develop the explanation to the requested word target. Return a nonempty '
                            'sentences list. Previous drafts and feedback are not source evidence.')}
                else:
                    payload["feedback"] = "Return the required JSON schema with valid passage IDs." if overview else "Generation was unavailable."
        if overview:
            section, recovered = recover_summary(sources, checks, question, self.response_request)
            if section:
                recovered['draft_stages'] = [check.get('stage') for check in checks]
                recovered['length_validation'] = length_check(section.text, self.response_request)
                if best_checked is None or length_distance(recovered['length_validation']) < length_distance(best_checked[1]['length_validation']):
                    best_checked = section, recovered
            # A checked subset is useful evidence, but it must not end a long
            # request before scoped expansion has had a bounded chance to finish.
            # Empty/malformed/truncated whole-file drafts also need that chance:
            # exact excerpts prove origin, not that synthesis is impossible.
            checked_support = any(item.get('supported') is True for check in checks
                                  for item in check.get('grounding_validation', {}).get('results', []))
            recoverable_draft = any(check.get('stage') in {'summary_draft_invalid', 'grounding', 'question_relevance'}
                or check.get('failure_code') in {'output_truncated', 'content_json', 'content_shape', 'empty_content'}
                for check in checks)
            connection_failed = bool(checks and checks[-1].get('failure_code') in
                                     {'model_timeout', 'model_connection_failed'})
            if (self.response_request['target_words'] and self.response_request['target_words'] >= 1200
                and (best_checked is None or (not best_checked[1]['length_validation']['valid']
                    and best_checked[1]['length_validation']['actual_words'] < int(self.response_request['target_words'] * .9)))
                and (checked_support or recoverable_draft) and not connection_failed
                and not any(check.get('stage') == 'verification_unavailable' for check in checks)):
                log.info('summary_expansion=start seed_mode=%s',
                         best_checked[1].get('response_mode', 'generated') if best_checked else 'none')
                expanded = expand_summary(self.rag, client, sources, question, self.response_request,
                                          payload, _schema_errors)
                if expanded and (best_checked is None or
                    length_distance(expanded[1]['length_validation']) < length_distance(best_checked[1]['length_validation'])):
                    expanded[1]['draft_stages'] = [check.get('stage') for check in checks]
                    best_checked = expanded
        if best_checked:
            if not best_checked[1]['length_validation']['valid']:
                best_checked[1]['stage'] = 'requested_length_not_met'
            return best_checked
        return None, validation

    def answer(self, question, top_k=3, course_id=None, source_id=None, history=None):
        if course_id is None:
            raise ValueError("Source-aware answering requires an authenticated workspace scope.")
        original_question = question.strip()
        if not original_question:
            raise ValueError("Question cannot be empty.")
        self.rag.requested_question = original_question
        self.selected_source_id = source_id
        # Retain background assistant turns for referents, without promoting
        # their claims into source evidence. Bound context independently of API input.
        self.conversation_context = [
            {"role": m["role"], "content": m["content"][:3000]}
            for m in (history or [])[-8:]
            if m.get("role") in {"user", "assistant"} and isinstance(m.get("content"), str)
        ]
        question = self.rag._resolve_material_correction(original_question, history or []) if source_id else original_question
        question = resolve_format_followup(question, history or [],
            fallback='Explain the selected material.' if source_id else None)
        if question == original_question:
            question = self.rag._resolve_followup(question, history or [])
        self.response_request = response_request(question)
        self.context_limit = 96 if self.response_request['long_form'] else 24
        search_question = re.split(r"\n(?:Answer format requested now|Follow-up request):", question)[0].strip()
        self.rag.retrieval_question = search_question
        overview = source_id is not None and self.rag._is_material_overview(question)
        explicit_grounding = bool(re.search(
            r"\b(?:use only|only use|using only|strictly from|solely from)\b|\bonly (?:my|the|this|these|your) (?:sources?|material|slides?|presentation|documents?|deck)\b",
            question, re.I))
        mode = "grounded" if explicit_grounding else self.mode
        depth = choose_depth(original_question, self.requested_depth)
        policy = json.loads(prompt("depth_policy.json"))[depth]
        policy += ' Explicit length and format requests override the usual brief-answer default.'
        client = self.rag.llm.for_task("deep" if depth == "advanced" else "answer")
        if self.response_request['target_words'] and hasattr(client, 'with_output_budget'):
            client = client.with_output_budget(self.response_request['token_budget'])
        scope = {"course_id": course_id, "source_id": source_id}
        reading_warnings = []
        health = getattr(self.rag.retriever, "reading_warnings", None)
        if health:
            try:
                reading_warnings = health(**scope)
            except Exception:
                reading_warnings = ["Material reading status is unavailable."]
        sources, results, attempts, retrieval_error = [], [], 0, False
        self.retrieval_incomplete = False
        decision = self._unknown("No readable passages were retrieved; coverage is unknown.")
        supported_snapshot = None
        # Overview lookup already samples across the file. Repeating the exact
        # same sample/judge call cannot establish more complete coverage.
        for broaden in ((False,) if overview else (False, True)):
            attempts += 1
            try:
                found = self._retrieve(search_question, scope, top_k, overview, broaden)
                # Each retry is a fresh, bounded candidate set. Appending to a
                # full first-pass set previously discarded all rescued evidence.
                results = self._merge(found, results) if broaden else found
                sources = self.rag._build_sources(results)
                if sources:
                    decision = self._judge(question, sources)
                    if decision.covered_parts:
                        supported_snapshot = (decision, sources)
            except Exception as error:
                retrieval_error = True
                log.warning("source_retrieval=unavailable error_type=%s", type(error).__name__)
                decision = self._unknown("Retrieval failed; source coverage cannot be determined.")
            if decision.status == "fully_covered":
                break
        # A failed broader lookup/check must not erase evidence already checked
        # on the first pass. Restore its matching citation list as one unit.
        if not decision.covered_parts and supported_snapshot is not None:
            decision, sources = supported_snapshot
        if (retrieval_error or self.retrieval_incomplete) and decision.status == "not_covered":
            decision = self._unknown("Retrieval was incomplete; absence has not been established.")
        if reading_warnings and decision.status == "not_covered":
            decision = self._unknown("Some material could not be read completely; source absence has not been established.")
        sections = []
        source_validation = {"valid": False, "stage": "coverage_unknown"}
        mention_found = False
        if decision.status in {"not_covered", "unknown"} and not decision.covered_parts:
            for number, source in enumerate(sources, 1):
                excerpt = topic_excerpt(search_question, source["content"])
                if not excerpt or citation_ids(excerpt):
                    continue
                # Exact quotes establish presence only. They never turn labels
                # into a claimed mechanism or override the coverage judge.
                quoted = "\n".join("> " + line for line in excerpt.splitlines())
                sections.append(AnswerSection(kind="sourced",
                    text=f"The material includes this text:\n{quoted} [{number}]",
                    provenance="uploaded_material", verified=True, citation_ids=[number]))
                decision = self._unknown("The topic is explicitly mentioned, but sufficient explanatory coverage could not be verified.")
                source_validation = {"valid": True, "stage": "exact_source_excerpt"}
                mention_found = True
                break
        if decision.covered_parts or (overview and sources):
            section, source_validation = self._source_answer(question, sources, decision, client, policy, overview=overview)
            if section:
                sections.append(section)
                if overview and decision.status == 'not_covered':
                    decision = self._unknown('A source-based overview was produced from readable samples; whole-file coverage has not been established.')
        # An overview is about the uploaded file, so general knowledge cannot fill
        # missing document content. Unknown coverage is never labeled not covered.
        if mode == "intelligence" and not overview and decision.status != "fully_covered":
            try:
                extra = client.generate(json.dumps({"missing_parts": decision.missing_parts,
                    "coverage_status": decision.status, "depth_policy": policy,
                    "response_request": self.response_request,
                    "conversation_context": self.conversation_context,
                    "profile_style": self.rag.learning_style, "question": question}),
                    max_retries=1, system_prompt=prompt("beyond_material.txt")).strip()
                section = AnswerSection(kind="beyond", text=extra, provenance="model_knowledge", verified=False)
                sections.append(section)
            except Exception as error:
                # Reject fabricated document citations rather than stripping them
                # and presenting the same unsupported text with a cleaner label.
                log.warning("background_answer=unavailable error_type=%s", type(error).__name__)
        notices = []
        if overview and sections:
            if source_validation.get('response_mode') == 'extractive':
                notices.append("I couldn't check a complete summary, so here are selected excerpts from your material.")
            elif source_validation.get('response_mode') == 'checked_points':
                notices.append("Here are the points I could verify from your material.")
        elif decision.status == "not_covered":
            notices.append("I couldn't find this in the material passages I checked.")
        elif decision.status == "partially_covered":
            notices.append("Your material covers part of this question. The remaining parts were not found in the passages checked.")
        elif decision.status == "unknown":
            notices.append("I found this topic in your material, but couldn't verify a full explanation from the available text and labels."
                           if mention_found else "I couldn't determine whether your material covers this question. This does not mean it is absent.")
        if reading_warnings and decision.status != "fully_covered":
            notices.append("Some parts of this file could not be read completely. Review its reading notices; image or diagram details may need a clearer upload.")
        length = length_check('\n'.join(s.text for s in sections), self.response_request) if sections else None
        if length and not length['valid']:
            if length['requested_words']:
                notices.append(f"This response is {length['actual_words']} words; the requested target was approximately {length['requested_words']} words.")
            else:
                notices.append('The checked explanation does not fully match the requested sentence or paragraph count.')
        if self.response_request['requested_words'] != self.response_request['target_words']:
            notices.append(f"This response uses a maximum target of {self.response_request['target_words']} words; the requested length was {self.response_request['requested_words']}.")
        if decision.covered_parts and not any(s.kind == "sourced" for s in sections):
            notices.append("I found related evidence, but couldn't verify a source-backed explanation right now.")
        if not sections and not notices:
            notices.append("I couldn't prepare a checked answer right now. Please retry.")
        blocks = list(notices)
        for section in sections:
            label = "From your material" if section.kind == "sourced" else "Beyond your material — model knowledge, not web verified"
            blocks.append(label + ":\n" + section.text)
        clarification = decision.clarifying_question if decision.ambiguous and sections else None
        if clarification:
            blocks.append(clarification)
        has_source = any(s.kind == "sourced" for s in sections)
        has_beyond = any(s.kind == "beyond" for s in sections)
        stage = ("source_plus_background" if has_source and has_beyond else "complete" if has_source
                 else "general_background" if has_beyond else "verification_unavailable")
        response = self.rag._response("\n\n".join(blocks), sources, {
            "valid": has_source and not has_beyond, "stage": stage,
            "source_validation": source_validation, "background_verified": False,
            "response_mode": source_validation.get('response_mode', 'generated'),
        })
        fields = SourceAwareFields.model_validate({
            "coverage": {**decision.model_dump(), "scope": "retrieved_passages", "retrieval_attempts": attempts},
            "sections": [s.model_dump() for s in sections], "mode": mode, "depth": depth,
            "clarifying_question": clarification,
            "follow_up_options": ["Explain simply", "Go deeper"] if sections else [],
        })
        response.update(fields.model_dump(), pipeline_version="aura-source-aware-v1",
            response_request=self.response_request,
            length_validation=length_check('\n'.join(s.text for s in sections), self.response_request),
            material_context=self.material_context)
        return response
