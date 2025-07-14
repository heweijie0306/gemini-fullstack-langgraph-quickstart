from typing import List, Union, Literal, Optional
from pydantic import BaseModel, Field
from tavily import TavilyClient
import os
from langchain_core.tools import tool


@tool
def tavily_search(query: str, search_depth: str = "advanced", topic: str = "general") -> str:
    """
    Search the web for information using the Tavily API.
    Args:
        query: The search query to be used for web research.
        search_depth: The depth of the search. Could be "basic", "advanced".
        topic: The topic of the search. Could be "general", "news"
    Returns:
        A object containing the search results.
    """
    client = TavilyClient("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")
    response = client.search(
        query=query,
        search_depth=search_depth,
        topic=topic,
    )
    return response

@tool
def url_extract(url: str, extract_depth: str = "basic") -> str:
    """
    Extract the content of a URL using the Tavily API.
    Args:
        url: The URL to be extracted.
        extract_depth: The depth of the extraction. Could be "basic", "advanced".
    Returns:
        A object containing the extracted content.
    """
    client = TavilyClient("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")
    response = client.extract(url)
    return response

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
    response: str = Field(
        description="A brief response indicating that the outlines have been generated."
    )


class SlideContent(BaseModel):

    content: str = Field(
        description="The detailed content of the slide, formatted in markdown."
    )
    response: str = Field(
        description="A brief response indicating that the slide content has been generated."
    )
class Task(BaseModel):
    task: Optional[Union[Literal["ContextSearch"], Literal["GenerateOutline"], Literal["GenerateSlides"]]] = Field(
        description="A task to be completed."
    )

class FinalResponse(BaseModel):
    response: str = Field(
        description="The final response to the user when no more tasks need to be completed."
    )

class Decision(BaseModel):
    reasoning: str = Field(
        description="Brief explanation of your next move based on the current state and user request."
    )
    next_task: Union[
        Literal["ContextSearch"], 
        Literal["GenerateOutline"]                   , 
        Literal["GenerateSlides"],
        FinalResponse
    ] = Field(                      
        description="The next task to be completed as a string, or a FinalResponse object if workflow is complete."
    )



