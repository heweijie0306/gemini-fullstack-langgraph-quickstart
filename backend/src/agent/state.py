from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypedDict, Union, Literal, List

from langgraph.graph import add_messages
from typing_extensions import Annotated


import operator
from dataclasses import dataclass, field
from typing_extensions import Annotated

def reduce_with_overwrite(left, right):
    if left is None:
        left = []
    if not right:
        # Overwrite with empty list
        return []
    return left + right


class OverallState(TypedDict):
    messages: Annotated[list, add_messages]
    task_list: Annotated[list, operator.add]
    text_response: Annotated[list, operator.add]
    search_query: Annotated[list, operator.add]
    web_research_result: Annotated[list, operator.add]
    sources_gathered: Annotated[list, operator.add]
    outline_list: list
    slides: Annotated[list, operator.add]
    slide_count: int
    initial_search_query_count: int
    max_research_loops: int = 1
    research_loop_count: int
    reasoning_model: str
    summary: str
    next_task: Union[str, dict, None] 
    reasoning: str
    executed_tasks: list
    processed_outline_list: Annotated[list, operator.add]
    unused_outline_list: list
    task_message: Annotated[list, reduce_with_overwrite]
    execute_outline: list
class ReflectionState(TypedDict):
    is_sufficient: bool
    knowledge_gap: str
    follow_up_queries: Annotated[list, operator.add]
    research_loop_count: int
    number_of_ran_queries: int
    summary: str

class Query(TypedDict):
    query: str
    rationale: str


class QueryGenerationState(TypedDict):
    query_list: list[Query]


class WebSearchState(TypedDict):
    search_query: str
    id: str


class OutlineGenerationState(TypedDict):
    outline_list: list[str]


class SlideGenerationState(TypedDict):
    outline_topic: str
    slide_id: int
    messages: Annotated[list, add_messages]
    web_research_result: Annotated[list, operator.add]


@dataclass(kw_only=True)
class SearchStateOutput:
    running_summary: str = field(default=None)  # Final report
