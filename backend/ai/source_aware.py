"""Source-aware document tutoring over the authenticated RAG retriever adapter."""
import json
import logging
import re
from pathlib import Path

from backend.ai.answer_contract import (
    AnswerSection, CoverageDecision, SourceAwareFields, choose_depth, citation_ids,
)

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

    @staticmethod
    def _unknown(reason):
        return CoverageDecision(status="unknown", reason=reason)

    def _judge(self, question, sources):
        try:
            data = self.coverage_llm.generate_json(
                json.dumps({"passages": [{"id": i, "text": s["content"][:6000]}
                                        for i, s in enumerate(sources, 1)], "question": question}),
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
            results = self.rag.retriever.search(question, **scope, top_k=16 if broaden else max(6, top_k))
            if scope["source_id"] is not None:
                results = self._merge(results, self.rag.retriever.concept_context(
                    question, **scope, limit=10 if broaden else 6))
        if broaden and scope["source_id"] is not None and not overview:
            # Reserve room for diverse locations before adding more ranked hits;
            # otherwise top-K candidates can crowd out the broader document scan.
            results = self._merge(self.rag.retriever.overview(**scope, limit=10), results)
        return self._merge([], results)

    def _source_answer(self, question, sources, decision, client, depth_policy):
        payload = {"passages": [{"id": i, "text": s["content"][:6000]}
                                for i, s in enumerate(sources, 1)],
                   "supported_parts": [part.model_dump() for part in decision.covered_parts],
                   "missing_parts": decision.missing_parts,
                   "profile_style": self.rag.learning_style, "depth_policy": depth_policy,
                   "question": question}
        validation = {"valid": False, "stage": "generation_unavailable"}
        for attempt in range(2):
            try:
                text = self.rag._normalize_citations(client.generate(
                    json.dumps(payload), max_retries=1, system_prompt=prompt("sourced_answer.txt")))
                validation = self.rag._validate_answer(text, sources, question)
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
                break
        return None, validation

    def answer(self, question, top_k=3, course_id=None, source_id=None, history=None):
        if course_id is None:
            raise ValueError("Source-aware answering requires an authenticated workspace scope.")
        original_question = question.strip()
        if not original_question:
            raise ValueError("Question cannot be empty.")
        self.rag.requested_question = original_question
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
        sources, results, attempts, retrieval_error = [], [], 0, False
        decision = self._unknown("No readable passages were retrieved; coverage is unknown.")
        for broaden in (False, True):
            attempts += 1
            try:
                found = self._retrieve(search_question, scope, top_k, overview, broaden)
                results = self._merge(results, found)
                sources = self.rag._build_sources(results)
                if sources:
                    decision = self._judge(question, sources)
            except Exception as error:
                retrieval_error = True
                log.warning("source_retrieval=unavailable error_type=%s", type(error).__name__)
                decision = self._unknown("Retrieval failed; source coverage cannot be determined.")
            if decision.status == "fully_covered":
                break
        if retrieval_error and decision.status == "not_covered":
            decision = self._unknown("Retrieval was incomplete; absence has not been established.")
        sections = []
        source_validation = {"valid": False, "stage": "coverage_unknown"}
        if decision.covered_parts:
            section, source_validation = self._source_answer(question, sources, decision, client, policy)
            if section:
                sections.append(section)
        # An overview is about the uploaded file, so general knowledge cannot fill
        # missing document content. Unknown coverage is never labeled not covered.
        if mode == "intelligence" and not overview and decision.status != "fully_covered":
            try:
                extra = client.generate(json.dumps({"missing_parts": decision.missing_parts,
                    "coverage_status": decision.status, "depth_policy": policy,
                    "profile_style": self.rag.learning_style, "question": question}),
                    max_retries=1, system_prompt=prompt("beyond_material.txt")).strip()
                section = AnswerSection(kind="beyond", text=extra, provenance="model_knowledge", verified=False)
                sections.append(section)
            except Exception as error:
                # Reject fabricated document citations rather than stripping them
                # and presenting the same unsupported text with a cleaner label.
                log.warning("background_answer=unavailable error_type=%s", type(error).__name__)
        notices = []
        if decision.status == "not_covered":
            notices.append("I couldn't find this in the material passages I checked.")
        elif decision.status == "partially_covered":
            notices.append("Your material covers part of this question. The remaining parts were not found in the passages checked.")
        elif decision.status == "unknown":
            notices.append("I couldn't determine whether your material covers this question. This does not mean it is absent.")
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
        })
        fields = SourceAwareFields.model_validate({
            "coverage": {**decision.model_dump(), "scope": "retrieved_passages", "retrieval_attempts": attempts},
            "sections": [s.model_dump() for s in sections], "mode": mode, "depth": depth,
            "clarifying_question": clarification,
            "follow_up_options": ["Explain simply", "Go deeper"] if sections else [],
        })
        response.update(fields.model_dump(), pipeline_version="aura-source-aware-v1")
        return response
