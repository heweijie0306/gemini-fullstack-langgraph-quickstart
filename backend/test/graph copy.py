import os

from agent.tools_and_schemas import SearchQueryList, Reflection, OutlineList, SlideContent
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
)
from langchain_google_genai import ChatGoogleGenerativeAI
from agent.utils import (
    get_citations,
    get_research_topic,
    insert_citation_markers,
    resolve_urls,
)


# def get_gemini_client():
#     return Client(api_key=os.getenv("GEMINI_API_KEY"))

def get_llm(model: str, temperature: float = 0):
    llm = ChatOpenAI(
        model=model,
        api_key=os.getenv("OPENROUTER_API_KEY"),
        base_url=os.getenv("OPENROUTER_BASE_URL"),
        temperature=temperature,
    )
    return llm

# Nodes
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
        model=configurable.query_generator_model,
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
        return "generate_outline"
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
        summaries="\n---\n\n".join(state["web_research_result"]),
    )

    # init Reasoning Model
    llm = get_llm(reasoning_model, 0.3)
    result = llm.with_structured_output(OutlineList).invoke(formatted_prompt)

    return {"outline_list": result.outlines}


def continue_to_slide_generation(state: OutlineGenerationState):
    """LangGraph node that sends outlines to slide generation nodes.

    This is used to spawn n number of slide generation nodes, one for each outline.
    """
    return [
        Send("generate_slides", {"outline_topic": outline, "slide_id": int(idx)})
        for idx, outline in enumerate(state["outline_list"])
    ]


def generate_slides(state: OverallState, config: RunnableConfig) -> OverallState:
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
        research_topic=get_research_topic(state["messages"]),
        outline_topic=state["outline_topic"],
        summaries="\n---\n\n".join(state["web_research_result"]),
    )

    # init Reasoning Model
    llm = get_llm(reasoning_model, 0.3)
    result = llm.with_structured_output(SlideContent).invoke(formatted_prompt)

    slide_data = {
        "slide_id": state["slide_id"],
        "title": result.title,
        "content": result.content,
        "outline_topic": state["outline_topic"]
    }

    return {"slides": [slide_data]}

def graph_builder(genai_client: Client):
    # Create our Agent Graph
    builder = StateGraph(OverallState, config_schema=Configuration)

    # Define the nodes we will cycle between
    builder.add_node("generate_query", generate_query)
    builder.add_node("web_research", web_research)
    builder.add_node("reflection", reflection)
    builder.add_node("generate_outline", generate_outline)
    builder.add_node("generate_slides", generate_slides)

    # Set the entrypoint as `generate_query`
    # This means that this node is the first one called
    builder.add_edge(START, "generate_query")
    # Add conditional edge to continue with search queries in a parallel branch
    builder.add_conditional_edges(
        "generate_query", continue_to_web_research, ["web_research"]
    )
    # Reflect on the web research
    builder.add_edge("web_research", "reflection")
    # Evaluate the research
    builder.add_conditional_edges(
        "reflection", evaluate_research, ["web_research", "generate_outline"]
    )
    # Generate outline for slides
    builder.add_conditional_edges(
        "generate_outline", continue_to_slide_generation, ["generate_slides"]
    )
    # Generate slides and finish
    builder.add_edge("generate_slides", END)

    return builder.compile(name="pro-search-agent")


if __name__ == "__main__":
    load_dotenv()

    genai_client = get_gemini_client()
    graph = graph_builder(genai_client)
    graph.invoke({"messages": [HumanMessage(content="What is the capital of France?")]})
