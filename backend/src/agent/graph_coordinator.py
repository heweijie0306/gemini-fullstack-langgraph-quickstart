import os
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from agent.tools_and_schemas import SearchQueryList, Reflection, OutlineList, SlideContent, Decision, FinalResponse, Coordinator, EditContent
from dotenv import load_dotenv
from langchain_core.messages import AIMessage
from langgraph.types import Send
from langgraph.graph import StateGraph
from langgraph.graph import START, END
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import HumanMessage
from google.genai import Client
from langchain_openai import ChatOpenAI
from agent.state import (
    OverallState,
    QueryGenerationState,
    ReflectionState,
    WebSearchState,
    OutlineGenerationState,
    SlideGenerationState,
    AfterGenState,
)
from agent.configuration import Configuration
from agent.prompts import (
    get_current_date,
    query_writer_instructions,
    web_searcher_instructions,
    reflection_instructions,
    answer_instructions,
    outline_generation_instructions,
    slide_generation_instructions,
    task_list_generation_instructions,
    coordinator_instructions,
    add_new_slide_instructions,
    editor_instructions,
)
from langchain_google_genai import ChatGoogleGenerativeAI
from agent.utils import (
    get_citations,
    get_research_topic,
    insert_citation_markers,
    resolve_urls,
)

def get_gemini_client():
    return Client(api_key=os.getenv("GEMINI_API_KEY"))

def get_llm(model: str, temperature: float = 0):
    llm = ChatOpenAI(
        model=model,
        api_key=os.getenv("OPENROUTER_API_KEY"),
        base_url="https://openrouter.ai/api/v1",
        temperature=temperature,    
    )
    return llm

def coordinator(state:AfterGenState, config: Configuration) -> AfterGenState:
    configurable = Configuration.from_runnable_config(config)
    reasoning_model = state.get("reasoning_model") or configurable.reasoning_model
    llm = get_llm(reasoning_model, 0.3)
    formatted_prompt = coordinator_instructions.format(
        current_date=get_current_date(),
        research_topic=get_research_topic(state["messages"]),
        summaries="\n---\n\n".join(state["web_research_result"]),
    )
    result = llm.with_structured_output(Coordinator).invoke(formatted_prompt)
    if isinstance(result.next_task, FinalResponse):
        return {
            "next_task": result.next_task,  # Set the FinalResponse object
            "text_response": [result.next_task.response],  # Also set the response text
            "reasoning": result.reasoning
        }
    else:
        return {
            "next_task": result.next_task,
            "reasoning": result.reasoning
        }
def task_router(state: AfterGenState, config: Configuration) -> AfterGenState:
    if state["next_task"] == "add_new_slide":
        return "add_new_slide"
    elif state["next_task"] == "editor":
        return "editor"
    else:
        return END
def add_new_slide(state: AfterGenState, config:Configuration) -> AfterGenState:
    configurable = Configuration.from_runnable_config(config)
    reasoning_model = state.get("reasoning_model") or configurable.reasoning_model
    llm = get_llm(reasoning_model, 0.3)
    formatted_prompt = add_new_slide_instructions.format(
        current_date=get_current_date(),
        research_topic=get_research_topic(state["messages"]),
    )
    result = llm.with_structured_output(SlideContent).invoke(formatted_prompt)
    return {
        "new_slide": result.content,
        "task_message": [result.response]
    }
def editor(state:AfterGenState, config: Configuration) -> AfterGenState:
    configurable = Configuration.from_runnable_config(config)
    reasoning_model = state.get("reasoning_model") or configurable.reasoning_model
    llm = get_llm(reasoning_model, 0.3)
    formatted_prompt = editor_instructions.format(
        current_date=get_current_date(),
        research_topic=get_research_topic(state["messages"]),
    )
    result = llm.with_structured_output(EditContent).invoke(formatted_prompt)
    return {
        "edited_content": result.content,
        "task_message": [result.response]
    }

def graph_builder(genai_client: Client):
    builder = StateGraph(AfterGenState)
    builder.add_node("coordinator", coordinator)
    builder.add_node("add_new_slide", add_new_slide)
    builder.add_node("editor", editor)
    builder.add_edge(START, "coordinator")
    builder.add_conditional_edges("coordinator", task_router, [
        "add_new_slide",
        "editor",
        END
    ])
    builder.add_edge("add_new_slide", "coordinator")
    builder.add_edge("editor", "coordinator")
    return builder.compile(name="coordinator-graph")

# Load environment variables and create the client
load_dotenv()
genai_client = get_gemini_client()

# Create the graph instance for import
coordinator_graph = graph_builder(genai_client)
