import uuid

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver

from app.graph.state import State
from app.graph.nodes.orchestrator_node import orchestrator_node
from app.graph.nodes.router_node import router_node, route_next
from app.graph.nodes.research_node import research_node
from app.graph.nodes.worker_node import worker_node, fanout
from app.graph.nodes.subgraph.reducer_subgraph import reducer_subgraph
from app.graph.nodes.hitl import (
    human_review,
    revise_blog,
    route_after_review,
    save_approved_blog,
)

from logger import get_logger
from custom_execption import CustomException

logger = get_logger(__name__)

g = StateGraph(State)
g.add_node("router", router_node)
g.add_node("research", research_node)
g.add_node("orchestrator", orchestrator_node)
g.add_node("worker", worker_node)
g.add_node("reducer", reducer_subgraph)
g.add_node("human_review", human_review)
g.add_node("revise_blog", revise_blog)
g.add_node("save_approved_blog", save_approved_blog)

g.add_edge(START, "router")
g.add_conditional_edges(
    "router",
    route_next,
    {"research": "research", "orchestrator": "orchestrator"},
)
g.add_edge("research", "orchestrator")
g.add_conditional_edges("orchestrator", fanout, ["worker"])
g.add_edge("worker", "reducer")
g.add_edge("reducer", "human_review")

g.add_conditional_edges(
    "human_review",
    route_after_review,
    {
        "approved": "save_approved_blog",
        "revise": "revise_blog",
    },
)
g.add_edge("revise_blog", "human_review")
g.add_edge("save_approved_blog", END)

try:
    checkpointer = InMemorySaver()
    app = g.compile(checkpointer=checkpointer)
    logger.info("Main Workflow Compile Done")
except Exception as e:
    logger.error("Error in workflow.py: %s", e)
    raise CustomException("Error in Workflow Compile", e)


def run(topic: str, thread_id: str | None = None) -> dict:
    """
    Run the graph once. Because HITL pauses for review, callers must retain
    the returned config and pass it to app.invoke(Command(resume=...), config=...).
    """
    try:
        run_config = {
            "configurable": {
                "thread_id": thread_id or uuid.uuid4().hex,
            }
        }

        out = app.invoke(
            {
                "topic": topic,
                "mode": "",
                "needs_research": False,
                "queries": [],
                "evidence": [],
                "plan": None,
                "sections": [],
                "merged_md": "",
                "md_with_placeholders": "",
                "image_specs": [],
                "generated_images": [],
                "final": "",
                "final_after_review": "",
                "feedback": "",
                "approved": False,
            },
            config=run_config,
        )

        logger.info("Run Function Invoked Successfully")
        return {"result": out, "config": run_config}

    except Exception as e:
        logger.error("Error in run Function: %s", e)
        raise CustomException("Error in run Function", e)
