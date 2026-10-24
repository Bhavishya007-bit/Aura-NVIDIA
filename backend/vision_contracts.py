"""Validated visual outputs with bounded repair and content-free diagnostics."""
import json
import logging
from typing import Annotated

from fastapi import HTTPException
from pydantic import Field, ValidationError, field_validator, model_validator

from backend.ai.answer_contract import StrictModel
from backend.visual_tasks import sql_completion_feedback

log = logging.getLogger(__name__)
ShortText = Annotated[str, Field(min_length=1, max_length=900)]


class ImageDraft(StrictModel):
    answerable: bool
    observations: list[ShortText] = Field(max_length=12)
    explanation: str = Field(min_length=1, max_length=4500)
    limitations: list[ShortText] = Field(max_length=8)

    @field_validator('explanation')
    @classmethod
    def explanation_has_text(cls, value):
        if not value.strip():
            raise ValueError('Explanation is blank')
        return value

    @model_validator(mode='after')
    def evidence_has_text(self):
        if self.answerable and not self.observations:
            raise ValueError('An answer requires visible observations')
        if any(not value.strip() for value in self.observations + self.limitations):
            raise ValueError('Evidence fields must not be blank')
        return self


class VisionVerdict(StrictModel):
    supported: bool
    reason: str = Field(default='', max_length=900)


class VisionOutputError(HTTPException):
    """Malformed/truncated provider output; never a transport/authentication error."""
    def __init__(self, failure_code):
        super().__init__(503, 'Aura could not read a complete image-model response. Please retry.')
        self.failure_code = failure_code


def schema_fields(error):
    allowed = {'answerable', 'observations', 'explanation', 'limitations', 'image', 'text', 'supported', 'reason'}
    # Pydantic errors can include the input itself, unknown keys and validator
    # messages. Keep only known field paths and error types, never that content.
    return [{'path': [part if isinstance(part, int) or part in allowed else '<field>'
                      for part in item['loc']], 'type': item['type']}
            for item in error.errors(include_input=False, include_url=False)[:6]]


def visual_output(generate, images, prompt, contract, *, task, tokens, question=None):
    """At most two model attempts, shared by schema and task-completion repairs.

    Do not coerce booleans, invent observations or default missing answer fields.
    Ownership, attribution and other evidence checks stay outside this helper.
    """
    schema = contract.model_json_schema()
    base = prompt + '\nREQUIRED OUTPUT SCHEMA (JSON only, with all required fields): ' + json.dumps(schema)
    request = base
    for attempt in (1, 2):
        fields = []
        try:
            raw = generate(images, request, tokens=tokens, output_schema=schema)
            result = contract.model_validate(raw)
            feedback = sql_completion_feedback(question, result.model_dump()) if question is not None else None
            if not feedback:
                if attempt > 1:
                    log.info('vision_output=recovered task=%s attempt=%d', task, attempt)
                return result
            code = 'task_incomplete'
        except ValidationError as error:
            fields = schema_fields(error)
            code = 'schema_invalid'
            feedback = ('Return JSON matching the required output schema, with exact field names and types. '
                        'Do not omit fields or replace the response object with SQL alone. '
                        'Include the solution in explanation and readable evidence in observations. '
                        'Set answerable=false only for actual missing or unreadable evidence. '
                        'Validation fields: ' + json.dumps(fields))
        except VisionOutputError as error:
            code = error.failure_code
            feedback = ('The response was malformed or truncated. Return one complete JSON object '
                        'matching the required schema. Keep observations and explanation concise; '
                        'include every required field. No text outside the JSON object.')
        log.warning('vision_output=invalid task=%s attempt=%d failure_code=%s fields=%s',
                    task, attempt, code, json.dumps(fields))
        request = base + '\nREVISION REQUIREMENT: ' + feedback
    raise HTTPException(503, 'Aura could not produce a complete image answer after retrying. Please retry the question.')
