import re
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


def requested_days(goal):
    numbers = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6,
               'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10, 'eleven': 11,
               'twelve': 12, 'thirteen': 13, 'fourteen': 14}
    matches = re.findall(r'\b(\d{1,3}|' + '|'.join(numbers) + r')\s*[-–]?\s*days?\b', goal, re.I)
    values = {int(value) if value.isdigit() else numbers[value.lower()] for value in matches}
    return next(iter(values)) if len(values) == 1 else None


class PlanDay(Strict):
    day: int = Field(ge=1, le=14)
    title: str = Field(min_length=1, max_length=160)
    details: str = Field(min_length=1, max_length=600)
    references: list[str] = Field(default_factory=list, max_length=8)


class CreateStudyPlan(Strict):
    tool: Literal['study_plan_create']
    overview: str = Field(min_length=1, max_length=1600)
    days: list[PlanDay] = Field(min_length=1, max_length=14)

    @model_validator(mode='after')
    def sequential_days(self):
        if [day.day for day in self.days] != list(range(1, len(self.days) + 1)):
            raise ValueError('Plan days must be sequential, starting at one.')
        if not self.overview.strip() or any(not d.title.strip() or not d.details.strip() for d in self.days):
            raise ValueError('A plan needs complete daily tasks.')
        return self


class Finish(Strict):
    tool: Literal['finish']
    answer: str = Field(min_length=1, max_length=12000)
    references: list[str] = Field(default_factory=list, max_length=24)


class Decision(Strict):
    plan: list[str] = Field(min_length=1, max_length=6)
    action: Annotated[Union[Search, ReadMemory, WriteMemory, ReadTasks, CreateTask, CreateStudyPlan, Finish], Field(discriminator='tool')]

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
        days = requested_days(self.goal)
        if self.skill == 'study_plan' and days is not None and not 1 <= days <= 14:
            raise ValueError('Choose a study plan between one and fourteen days.')
        return self


SKILLS = {
    'study_plan': {'instruction': 'Gather relevant evidence, then use study_plan_create to create the whole daily plan and save its tasks in one action. Do not keep searching after gathering useful material. Do not invent assessment results.',
                   'tools': {'document_search', 'memory_read', 'task_list', 'task_create', 'study_plan_create'}},
    'research_brief': {'instruction': 'Research the selected uploaded material and draft a clear brief. Cite document references from observations; identify limitations. Web access is not available in this version.',
                       'tools': {'document_search', 'memory_read'}},
}


def allowed_tools(request):
    tools = set(SKILLS[request.skill]['tools'])
    if request.allow_memory_write:
        tools.add('memory_write')
    return tools | {'finish'}
