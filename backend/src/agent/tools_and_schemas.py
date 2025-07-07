from typing import List, Union, Literal, Optional
from pydantic import BaseModel, Field


class SearchQueryList(BaseModel):
    query: List[str] = Field(
        description="A list of search queries to be used for web research."
    )
    rationale: str = Field(
        description="A brief explanation of why these queries are relevant to the research topic."
    )


class Reflection(BaseModel):
    is_sufficient: bool = Field(
        description="Whether the current context is sufficient to answer the user's question."
    )
    knowledge_gap: str = Field(
        description="A description of what information is missing or needs clarification."
    )
    follow_up_queries: List[str] = Field(
        description="A list of follow-up queries to address the knowledge gap."
    )
    summary: str = Field(
        description="A text response to the user's question as long as the context is sufficient, otherwise an empty string."
    )

class Outline(BaseModel):
    index: int = Field(
        description="The index of the slide outline, starting from 0."
    )
    prompt: str = Field(
        description="The prompt for the slide outline."
    )
class OutlineList(BaseModel):
    outlines: List[Outline] = Field(
        description="A list of slide outlines, each representing a specific topic or section for presentation slides."
    )



class SlideContent(BaseModel):
    title: str = Field(
        description="The title of the slide."
    )
    content: str = Field(
        description="The detailed content of the slide, formatted in markdown."
    )

class Task(BaseModel):
    task: Optional[Union[Literal["ContextSearch"], Literal["GenerateOutline"], Literal["GenerateSlides"]]] = Field(
        description="A task to be completed."
    )

class TaskList(BaseModel):
    tasks: List[Task] = Field(
        description="""A list of tasks to be completed, the 3 tasks together forms a complete workflow of slide generation. But you 
        need to select a subset of tasks to be completed based on user request. For example if user wants to generate outlines first, then 
        you shouldnt include slide generation task in the list. Or if user just wants to chat with you, you shouldnt include any generation task in the list."""
    )
    text_response: str = Field(
        description="A text response to the user indicating what you gonna do or greet the user."
    )