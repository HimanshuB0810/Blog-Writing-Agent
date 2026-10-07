from app.graph.state import State
from langgraph.graph import StateGraph, START, END
from app.graph.nodes.subgraph import reducer_subgraph

from app.graph.nodes.orchestrator_node import orchestrator_node
from app.graph.nodes.router_node import router_node, route_next
from app.graph.nodes.research_node import research_node
from app.graph.nodes.worker_node import worker_node, fanout
from app.graph.nodes.worker_node import fanout
from app.graph.nodes.subgraph.reducer_subgraph import reducer_subgraph


from logger import get_logger
from custom_execption import CustomException
logger = get_logger(__name__)

g = StateGraph(State)
g.add_node("router", router_node)
g.add_node("research", research_node)
g.add_node("orchestrator", orchestrator_node)
g.add_node("worker", worker_node)
g.add_node("reducer", reducer_subgraph)

g.add_edge(START, "router")
g.add_conditional_edges("router", route_next, {"research": "research", "orchestrator": "orchestrator"})
g.add_edge("research", "orchestrator")

g.add_conditional_edges("orchestrator", fanout, ["worker"])
g.add_edge("worker", "reducer")
g.add_edge("reducer", END)

try:
    app = g.compile()
    logger.info("Main Workflow Compile Done")

except Exception as e:
        logger.error(f"Error in workflow.py {e}")
        raise CustomException("Error in Workflow Compile",e)

def run(topic: str):
    try:
        out = app.invoke(
            {
                "topic":topic,
                "mode":"",
                "needs_research":False,
                "queries":[],
                "evidence":[],
                "plan":None,
                "sections":[],
                "merged_md":"",
                "md_with_placeholders":"",
                "image_specs":[],
                "generated_images":[],
                "final":""
            }
        )
        logger.info("Run Function Invoked Successfully")
        return out

    except Exception as e:
        logger.error(f"Error in run Function{e}")
        raise CustomException("Error in run Function",e)