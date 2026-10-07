from langgraph.graph import StateGraph
from langchain.messages import SystemMessage, HumanMessage
from llm.models import llm
from app.graph.state import State, RouterDecision
from llm.prompts.prompts import ROUTER_SYSTEM

from logger import get_logger
from custom_execption import CustomException

logger=get_logger(__name__)

def router_node(state:State) -> dict:
    try:

        topic = state['topic']
        decider = llm.with_structured_output(RouterDecision)
        decision = decider.invoke(
            [
                SystemMessage(content=ROUTER_SYSTEM),
                HumanMessage(content=f"Topic: {topic}")
            ]
        )

        logger.info("router node work completed") 
        return{
            "needs_research":decision.needs_research,
            "mode":decision.mode,
            "queries":decision.queries
        }
    except Exception as e:
            logger.error(f"Error during Router Node {e}")
            raise CustomException("Error while Router Node",e)

def route_next(state:State) -> str:
    try:
        return "research" if state['needs_research'] else "orchestrator"
    except Exception as e:
        logger.error("Error in Route Next in router node")
        raise CustomException("Error in Route Next in router Node",e)