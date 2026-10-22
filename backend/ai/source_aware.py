"""Source-aware document tutoring over the authenticated RAG retriever adapter."""
import json
import logging
import re
from pathlib import Path

from backend.ai.answer_contract import (
    AnswerSection, CoverageDecision, SourceAwareFields, choose_depth, citation_ids,
)
from backend.ai.lexical import topic_excerpt
from backend.ai.summary_answer import SummaryDraft, recover_summary

log = logging.getLogger(__name__)
PROMPTS = Path(__file__).with_name("prompts") / "v1"


def prompt(name):
    return (PROMPTS / name).read_text(encoding="utf-8")


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

    @staticmethod
    def _unknown(reason):
        return CoverageDecision(status="unknown", reason=reason)

    def _judge(self, question, sources):
        try:
            data = self.coverage_llm.generate_json(
                json.dumps({"passages": [{"id": i, "text": s["content"][:6000]}
                                        for i, s in enumerate(sources, 1)], "question": question,
                            "conversation_context": self.conversation_context}),
                max_retries=1, system_prompt=prompt("coverage_judge.txt"),
            )
            return CoverageDecision.model_validate(data).check_citations(len(sources))
        except Exception as error:
            log.warning("coverage_check=unavailable error_type=%s", type(error).__name__)
            return self._unknown("Coverage checking is unavailable; absence has not been established.")

    @staticmethod
    def _merge(existing, incoming):
        combined, seen = [], set()
        for item in list(existing) + list(incoming):
            text = " ".join(item.chunk.content.split())
            key = (item.chunk.source_id, text.casefold())
            if not text or key in seen:
                continue
            seen.add(key)
            combined.append(item)
            if len(combined) == 24:
                break
        return combined

    def _retrieve(self, question, scope, top_k, overview, broaden=False):
        results = []
        # A failed required retrieval is not evidence that a topic is absent.
        if overview:
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
        payload = {"passages": [{"id": i, "text": s["content"][:6000]}
                                for i, s in enumerate(sources, 1)],
                   "supported_parts": [part.model_dump() for part in decision.covered_parts],
                   "missing_parts": decision.missing_parts,
                   "profile_style": self.rag.learning_style, "depth_policy": depth_policy,
                   "conversation_context": self.conversation_context,
                   "selected_material": self.rag.selected_source_name,
                   "question": question}
        validation = {"valid": False, "stage": "generation_unavailable"}
        checks = []
        for attempt in range(2):
            try:
                if overview:
                    draft = client.generate_json(json.dumps(payload), max_retries=1,
                        system_prompt=prompt("summary_answer.txt"))
                    text = SummaryDraft.model_validate(draft).render(len(sources))
                else:
                    text = self.rag._normalize_citations(client.generate(
                        json.dumps(payload), max_retries=1, system_prompt=prompt("sourced_answer.txt")))
                validation = self.rag._validate_answer(text, sources, question)
                checks.append(validation)
                log.info("source_answer_check task=%s attempt=%s stage=%s valid=%s",
                         "summary" if overview else "answer", attempt + 1,
                         validation.get("stage"), validation.get("valid") is True)
                if validation.get("valid") is True:
                    return AnswerSection(kind="sourced", text=text, provenance="uploaded_material",
                                         verified=True, citation_ids=citation_ids(text)), validation
                payload["previous_draft"] = text
                payload["feedback"] = self.rag._short_feedback(validation)
                if validation.get("stage") == "verification_unavailable":
                    break
            except Exception as error:
                log.warning("source_answer=unavailable error_type=%s", type(error).__name__)
                validation = {"valid": False, "stage": "generation_unavailable"}
                checks.append(validation)
                payload["feedback"] = "Return the required JSON schema with valid passage IDs." if overview else "Generation was unavailable."
        if overview:
            section, recovered = recover_summary(sources, checks, question)
            if section:
                recovered['draft_stages'] = [check.get('stage') for check in checks]
                return section, recovered
        return None, validation

    def answer(self, question, top_k=3, course_id=None, source_id=None, history=None):
        if course_id is None:
            raise ValueError("Source-aware answering requires an authenticated workspace scope.")
        original_question = question.strip()
        if not original_question:
            raise ValueError("Question cannot be empty.")
        self.rag.requested_question = original_question
        # Retain background assistant turns for referents, without promoting
        # their claims into source evidence. Bound context independently of API input.
        self.conversation_context = [
            {"role": m["role"], "content": m["content"][:3000]}
            for m in (history or [])[-8:]
            if m.get("role") in {"user", "assistant"} and isinstance(m.get("content"), str)
        ]
        question = self.rag._resolve_material_correction(original_question, history or []) if source_id else original_question
        # Keep short depth-only follow-ups tied to the latest user topic without
        # treating the assistant's previous answer as factual evidence.
        if re.fullmatch(r"\s*(go deeper|make it simpler|explain simply|more detail)[.!?]*\s*", question, re.I):
            previous = next((m["content"] for m in reversed(history or [])
                             if m.get("role") == "user" and isinstance(m.get("content"), str)), None)
            if previous:
                question = previous + "\nFollow-up request: " + original_question
        question = self.rag._resolve_followup(question, history or [])
        search_question = re.split(r"\n(?:Answer format requested now|Follow-up request):", question)[0].strip()
        self.rag.retrieval_question = search_question
        overview = source_id is not None and self.rag._is_material_overview(question)
        explicit_grounding = bool(re.search(
            r"\b(?:use only|only use|using only|strictly from|solely from)\b|\bonly (?:my|the|this|these|your) (?:sources?|material|slides?|presentation|documents?|deck)\b",
            original_question, re.I))
        mode = "grounded" if explicit_grounding else self.mode
        depth = choose_depth(original_question, self.requested_depth)
        policy = json.loads(prompt("depth_policy.json"))[depth]
        client = self.rag.llm.for_task("deep" if depth == "advanced" else "answer")
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
        response.update(fields.model_dump(), pipeline_version="aura-source-aware-v1")
        return response
