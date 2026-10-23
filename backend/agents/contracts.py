from typing import Annotated, Literal, Union
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class MemoryInput(Strict):
    kind: Literal['preference', 'decision', 'event', 'task_progress', 'learner_fact']
    text: str = Field(min_length=1, max_length=1000)
    depth: Literal['beginner', 'standard', 'advanced'] | None = None
    examples: bool | None = None

    @model_validator(mode='after')
    def valid_preference(self):
        if not self.text.strip():
            raise ValueError('Memory text cannot be blank.')
        if self.kind != 'preference' and (self.depth is not None or self.examples is not None):
            raise ValueError('Depth and example settings apply to preferences only.')
        return self


class TaskInput(Strict):
    title: str = Field(min_length=1, max_length=240)
    details: str = Field(default='', max_length=1200)

    @model_validator(mode='after')
    def nonblank(self):
        if not self.title.strip():
            raise ValueError('A task needs a title.')
        return self


class Search(Strict):
    tool: Literal['document_search']
    query: str = Field(min_length=1, max_length=500)


class ReadMemory(Strict):
    tool: Literal['memory_read']


class WriteMemory(Strict):
    tool: Literal['memory_write']
    record: MemoryInput


class ReadTasks(Strict):
    tool: Literal['task_list']


class CreateTask(Strict):
    tool: Literal['task_create']
    task: TaskInput


class Finish(Strict):
    tool: Literal['finish']
    answer: str = Field(min_length=1, max_length=12000)
    references: list[str] = Field(default_factory=list, max_length=24)


class Decision(Strict):
    plan: list[str] = Field(min_length=1, max_length=6)
    action: Annotated[Union[Search, ReadMemory, WriteMemory, ReadTasks, CreateTask, Finish], Field(discriminator='tool')]

    @model_validator(mode='after')
    def bounded_plan(self):
        if any(not step.strip() or len(step) > 180 for step in self.plan):
            raise ValueError('Use short, concrete plan steps.')
        return self


class RunInput(Strict):
    course_id: int = Field(gt=0)
    source_id: int | None = Field(default=None, gt=0)
    skill: Literal['study_plan', 'research_brief']
    goal: str = Field(min_length=1, max_length=3000)
    allow_memory_write: bool = False
    max_steps: int = Field(default=8, ge=2, le=12)
    max_tokens: int = Field(default=32000, ge=4000, le=64000)
    max_seconds: int = Field(default=120, ge=15, le=180)

    @model_validator(mode='after')
    def nonblank(self):
        if not self.goal.strip():
            raise ValueError('Describe the agent task.')
        return self


SKILLS = {
    'study_plan': {'instruction': 'Create an actionable study plan using the goal, selected material and relevant saved preferences. You may create study tasks. Do not invent assessment results.',
                   'tools': {'document_search', 'memory_read', 'task_list', 'task_create'}},
    'research_brief': {'instruction': 'Research the selected uploaded material and draft a clear brief. Cite document references from observations; identify limitations. Web access is not available in this version.',
                       'tools': {'document_search', 'memory_read'}},
}


def allowed_tools(request):
    tools = set(SKILLS[request.skill]['tools'])
    if request.allow_memory_write:
        tools.add('memory_write')
    return tools | {'finish'}
