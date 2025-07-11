from agent.graph_gen import generator_graph
from agent.graph_coordinator import coordinator_graph
from langgraph.graph import StateGraph, START, END
from typing import TypedDict
class MainState(TypedDict):
    slide_content: list
    
def router(state: MainState) -> MainState:
    if state["slide_content"]:
        return "coordinator_graph"
    else:
        return "generator_graph"

def graph_builder():
    builder = StateGraph(MainState)
    builder.add_node("router", router)
    builder.add_node("coordinator_graph", coordinator_graph)
    builder.add_node("generator_graph", generator_graph)
    builder.add_edge(START, "router")
    builder.add_conditional_edges("router", router, ["coordinator_graph", "generator_graph"])
    return builder.compile(name="main-graph")

graph = graph_builder()









