import os
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from agent.tools_and_schemas import SearchQueryList, Reflection, OutlineList, SlideContent, Decision, FinalResponse
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

# Nodes
def decision_maker(state: OverallState, config: RunnableConfig) -> OverallState:
    """LangGraph node that generates a task list based on the user's question.

    Uses Gemini 2.0 Flash to create a task list based on the user's question.
    """
    configurable = Configuration.from_runnable_config(config)
    reasoning_model = state.get("reasoning_model") or configurable.reasoning_model
    # Format the prompt
    current_date = get_current_date()
    formatted_prompt = task_list_generation_instructions.format(
        current_date=current_date,
        search_result="\n---\n\n".join(state.get("web_research_result", [])),
        processed_outline_list=state.get("processed_outline_list", []),
        unused_outline_list=state.get("unused_outline_list", []),
        slides=state.get("slides", []),
        research_topic=get_research_topic(state["messages"]),
        task_message=state.get("task_message", [])
    )
    llm = get_llm(reasoning_model, 1.0)
    result = llm.with_structured_output(Decision).invoke(formatted_prompt)
    
    # Always set next_task, and optionally set text_response for FinalResponse
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

def continue_to_next_task(state: OverallState):
    if state["next_task"] == "ContextSearch":
        return "generate_query"
    elif state["next_task"] == "GenerateOutline":
        return "generate_outline"
    elif state["next_task"] == "GenerateSlides":
        if state.get("unused_outline_list"):
            # Return Send objects for fan-out - each gets its own topic
            return [
                Send("generate_slide_content", {
                    "outline_topic": outline, 
                    "messages":get_research_topic(state["messages"]),
                    "web_research_result": state["web_research_result"],
                    "slides": state.get("slides", []),
                    "reasoning_model": state.get("reasoning_model"),
                    "executed_tasks": state.get("executed_tasks", [])
                })
                for idx, outline in enumerate(state["unused_outline_list"])
                if outline not in state["processed_outline_list"]
            ]
        else:
            return Send("generate_slide_content", {
            "outline_topic": get_research_topic(state["messages"]),
            "web_research_result": state["web_research_result"],
        })
    elif isinstance(state["next_task"], FinalResponse):
        return "reset_task_messages"
    
def generate_query(state: OverallState, config: RunnableConfig) -> QueryGenerationState:
    """LangGraph node that generates a search queries based on the User's question.

    Uses Gemini 2.0 Flash to create an optimized search query for web research based on
    the User's question.

    Args:
        state: Current graph state containing the User's question
        config: Configuration for the runnable, including LLM provider settings

    Returns:
        Dictionary with state update, including search_query key containing the generated query
    """
    configurable = Configuration.from_runnable_config(config)

    # check for custom initial search query count
    if state.get("initial_search_query_count") is None:
        state["initial_search_query_count"] = configurable.number_of_initial_queries

    # init Gemini 2.0 Flash
    llm = get_llm(configurable.query_generator_model, 1.0)
    structured_llm = llm.with_structured_output(SearchQueryList)

    # Format the prompt
    current_date = get_current_date()
    formatted_prompt = query_writer_instructions.format(
        current_date=current_date,
        research_topic=get_research_topic(state["messages"]),
        number_queries=state["initial_search_query_count"],
    )
    # Generate the search queries
    result = structured_llm.invoke(formatted_prompt)
    return {"query_list": result.query}


def continue_to_web_research(state: QueryGenerationState):
    """LangGraph node that sends the search queries to the web research node.

    This is used to spawn n number of web research nodes, one for each search query.
    """
    return [
        Send("web_research", {"search_query": search_query, "id": int(idx)})
        for idx, search_query in enumerate(state["query_list"])
    ]


def web_research(state: WebSearchState, config: RunnableConfig) -> OverallState:
    """LangGraph node that performs web research using the native Google Search API tool.

    Executes a web search using the native Google Search API tool in combination with Gemini 2.0 Flash.

    Args:
        state: Current graph state containing the search query and research loop count
        config: Configuration for the runnable, including search API settings

    Returns:
        Dictionary with state update, including sources_gathered, research_loop_count, and web_research_results
    """
    # Configure
    configurable = Configuration.from_runnable_config(config)
    formatted_prompt = web_searcher_instructions.format(
        current_date=get_current_date(),
        research_topic=state["search_query"],
    )

    # Uses the google genai client as the langchain client doesn't return grounding metadata
    response = genai_client.models.generate_content(
        model="gemini-2.0-flash",
        contents=formatted_prompt,
        config={
            "tools": [{"google_search": {}}],
            "temperature": 0,
        },
    )
    # resolve the urls to short urls for saving tokens and time
    resolved_urls = resolve_urls(
        response.candidates[0].grounding_metadata.grounding_chunks, state["id"]
    )
    # Gets the citations and adds them to the generated text
    citations = get_citations(response, resolved_urls)
    modified_text = insert_citation_markers(response.text, citations)
    sources_gathered = [item for citation in citations for item in citation["segments"]]

    return {
        "sources_gathered": sources_gathered,
        "search_query": [state["search_query"]],
        "web_research_result": [modified_text],
    }
def tavily_search(state: WebSearchState, config: RunnableConfig) -> OverallState:
    """LangGraph node that performs web research using the Tavily API tool.

    Executes a web search using the Tavily API tool in combination with Gemini 2.0 Flash.
    """
    pass

def reflection(state: OverallState, config: RunnableConfig) -> ReflectionState:
    """LangGraph node that identifies knowledge gaps and generates potential follow-up queries.

    Analyzes the current summary to identify areas for further research and generates
    potential follow-up queries. Uses structured output to extract
    the follow-up query in JSON format.

    Args:
        state: Current graph state containing the running summary and research topic
        config: Configuration for the runnable, including LLM provider settings

    Returns:
        Dictionary with state update, including search_query key containing the generated follow-up query
    """
    configurable = Configuration.from_runnable_config(config)
    # Increment the research loop count and get the reasoning model
    state["research_loop_count"] = state.get("research_loop_count", 0) + 1
    reasoning_model = state.get("reasoning_model") or configurable.reasoning_model

    # Format the prompt
    current_date = get_current_date()
    formatted_prompt = reflection_instructions.format(
        current_date=current_date,
        research_topic=get_research_topic(state["messages"]),
        summaries="\n\n---\n\n".join(state["web_research_result"]),
    )
    # init Reasoning Model
    llm = get_llm(reasoning_model, 1.0)
    result = llm.with_structured_output(Reflection).invoke(formatted_prompt)

    return {
        "is_sufficient": result.is_sufficient,
        "knowledge_gap": result.knowledge_gap,
        "follow_up_queries": result.follow_up_queries,
        "research_loop_count": state["research_loop_count"],
        "number_of_ran_queries": len(state["search_query"]),
        "summary": result.summary,
        "executed_tasks": state.get("executed_tasks", []) + ["ContextSearch"]
    }

def evaluate_research(
    state: ReflectionState,
    config: RunnableConfig,
) -> OverallState:
    """LangGraph routing function that determines the next step in the research flow.

    Controls the research loop by deciding whether to continue gathering information
    or to finalize the summary based on the configured maximum number of research loops.

    Args:
        state: Current graph state containing the research loop count
        config: Configuration for the runnable, including max_research_loops setting

    Returns:
        String literal indicating the next node to visit ("web_research" or "finalize_summary")
    """
    configurable = Configuration.from_runnable_config(config)
    max_research_loops = (
        state.get("max_research_loops")
        if state.get("max_research_loops") is not None
        else configurable.max_research_loops
    )
    if state["is_sufficient"] or state["research_loop_count"] >= max_research_loops:
        return "decision_maker"
    else:
        return [
            Send(
                "web_research",
                {
                    "search_query": follow_up_query,
                    "id": state["number_of_ran_queries"] + int(idx),
                },
            )
            for idx, follow_up_query in enumerate(state["follow_up_queries"])
        ]



def generate_outline(state: OverallState, config: RunnableConfig) -> OutlineGenerationState:
    """LangGraph node that generates presentation slide outlines based on research findings.

    Analyzes the research summaries to create a structured outline for presentation slides
    that comprehensively covers the research findings in a logical flow.

    Args:
        state: Current graph state containing the research summaries and research topic
        config: Configuration for the runnable, including LLM provider settings

    Returns:
        Dictionary with state update, including outline_list key containing the generated outlines
    """
    configurable = Configuration.from_runnable_config(config)
    reasoning_model = state.get("reasoning_model") or configurable.reasoning_model

    # Format the prompt
    current_date = get_current_date()
    formatted_prompt = outline_generation_instructions.format(
        current_date=current_date,
        research_topic=get_research_topic(state["messages"]),
        processed_outline_list=state.get("processed_outline_list", []),
        unused_outline_list=state.get("unused_outline_list", []),
        summaries="\n---\n\n".join(state["web_research_result"]),
    )

    # init Reasoning Model
    llm = get_llm(reasoning_model, 0.3)
    result = llm.with_structured_output(OutlineList).invoke(formatted_prompt)

    return {"unused_outline_list": state.get("unused_outline_list", []) + result.outlines, 
            "task_message": [result.response],
            "executed_tasks": state.get("executed_tasks", []) + ["GenerateOutline"]}

def evaluate_outline(state: OverallState, config: RunnableConfig) -> OverallState:
    """LangGraph node that evaluates the outline and asks for human feedback.

    Uses Gemini 2.0 Flash to evaluate the outline and asks for human feedback.
    """
    if state["outline_list"]:
        return "decision_maker"
    else:
        return END

# def continue_to_slide_generation(state: OverallState):
#     """LangGraph node that sends outlines to slide generation nodes.

#     This is used to spawn n number of slide generation nodes, one for each outline.
#     """
#     if state["outline_list"]:
#         return [
#             Send("generate_slide_content", {
#                 "outline_topic": outline, 
#                 "slide_id": int(idx),
#                 "messages": state["messages"],
#                 "web_research_result": state["web_research_result"]
#             })
#             for idx, outline in enumerate(state["outline_list"])
#         ]
#     else:
#         return END


def generate_slide_content(state: OverallState, config: RunnableConfig) -> OverallState:
    """LangGraph node that generates slide content based on outline and research summaries.

    Creates detailed slide content for a specific outline topic using the research findings
    and formats it as presentation-ready content.

    Args:
        state: Current graph state containing the outline topic, slide ID, and research data
        config: Configuration for the runnable, including LLM provider settings

    Returns:
        Dictionary with state update, including slides key containing the generated slide content
    """
    configurable = Configuration.from_runnable_config(config)
    reasoning_model = state.get("reasoning_model") or configurable.reasoning_model

    # Format the prompt
    current_date = get_current_date()
    formatted_prompt = slide_generation_instructions.format(
        current_date=current_date,
        outline_topic=state["outline_topic"],
        summaries="\n---\n\n".join(state["web_research_result"]),
        slides=state.get("slides", []),
    )

    # init Reasoning Model
    llm = get_llm(reasoning_model, 0.3)
    result = llm.with_structured_output(SlideContent).invoke(formatted_prompt)

    slide_data = {  
        "content": result.content,
    }

    return {
        "slides": [slide_data],
        "task_message":[result.response],
        "processed_outline_list": [state["outline_topic"]]
    }


def cleanup_outline_list(state: OverallState) -> OverallState:
    """Remove processed topics from unused_outline_list"""
    processed = state.get("processed_outline_list", [])
    current_unused = state.get("unused_outline_list", [])
    
    # Remove all processed topics
    updated_unused = [topic for topic in current_unused if topic not in processed]
    
    return {
        "unused_outline_list": updated_unused,
        "processed_outline_list": []  
    }

def reset_task_messages(state: OverallState) -> OverallState:
    return {
        "task_message": []
    }
    

def graph_builder(genai_client: Client):
    # Create our Agent Graph
    builder = StateGraph(OverallState, config_schema=Configuration)

    # Define the nodes
    builder.add_node("decision_maker", decision_maker)
    builder.add_node("generate_query", generate_query)
    builder.add_node("web_research", web_research)
    builder.add_node("reflection", reflection)
    builder.add_node("generate_outline", generate_outline)
    builder.add_node("generate_slide_content", generate_slide_content)
    builder.add_node("cleanup_outline_list", cleanup_outline_list)
    builder.add_node("reset_task_messages", reset_task_messages)
    
    # Entry point
    builder.add_edge(START, "decision_maker")
    
    # Route to next task based on decision maker output
    builder.add_conditional_edges(
        "decision_maker", 
        continue_to_next_task, 
        ["generate_outline", "generate_slide_content", "reset_task_messages"]
    )
    
    # Web research flow (when ContextSearch task is selected)
    builder.add_conditional_edges(
        "generate_query", continue_to_web_research, ["web_research"]
    )
    builder.add_edge("web_research", "reflection")
    builder.add_conditional_edges(
        "reflection", evaluate_research, ["web_research", "decision_maker"]
    )
    
    # Outline generation flow (when GenerateOutline task is selected)
    builder.add_edge("generate_outline", "decision_maker")
    builder.add_edge("generate_slide_content", "cleanup_outline_list")
    builder.add_edge("cleanup_outline_list", "decision_maker")
    builder.add_edge("reset_task_messages", END)


    return builder.compile(name="pro-search-agent")


# Load environment variables and create the client
load_dotenv()
genai_client = get_gemini_client()

# Create the graph instance for import
graph = graph_builder(genai_client)

if __name__ == "__main__":
    import time
    from typing import Dict, Any

    class GraphMonitor:
        def __init__(self, graph):
            self.graph = graph
            self.execution_log = []
        
        def tracked_invoke(self, input_data: Dict[str, Any], config: Dict[str, Any]):
            start_time = time.time()
            thread_id = config.get("configurable", {}).get("thread_id")
            
            print(f"🚀 Starting graph execution for thread: {thread_id}")
            
            # Stream the execution to track each step
            final_state = None
            for event in self.graph.stream(input_data, config, stream_mode="updates"):
                node_name = list(event.keys())[0] if event else "unknown"
                timestamp = time.time()
                
                # Extract and format output for display
                node_output = event.get(node_name, {}) if event else {}
                output_preview = self._format_output_preview(node_output)
                
                log_entry = {
                    "timestamp": timestamp,
                    "node": node_name,
                    "data": event,
                    "output_preview": output_preview,
                    "elapsed": timestamp - start_time
                }
                self.execution_log.append(log_entry)
                
                print(f"⚡ [{timestamp - start_time:.2f}s] Node '{node_name}' executed")
                print(f"   Output: {output_preview}")
                final_state = event
            
            total_time = time.time() - start_time
            print(f"✅ Graph execution completed in {total_time:.2f}s")
            
            return final_state
        
        def _format_output_preview(self, output: Dict[str, Any]) -> str:
            """Format output data to show first 100 characters"""
            if not output:
                return "No output"
            
            # Convert output to string representation
            output_str = str(output)
            
            # Truncate to first 100 characters
            
            return output_str
        
        def print_execution_summary(self):
            print("\n📊 Execution Summary:")
            for entry in self.execution_log:
                print(f"  {entry['elapsed']:.2f}s - {entry['node']}")
                print(f"    Output: {entry['output_preview']}")
            
    # Usage
    monitor = GraphMonitor(graph)
    result = monitor.tracked_invoke(
        {"messages": [HumanMessage(content="generate 3 slides on the topic of AI and the future of work")]},
        {"configurable": {"thread_id": "monitored_thread"}}
    )

