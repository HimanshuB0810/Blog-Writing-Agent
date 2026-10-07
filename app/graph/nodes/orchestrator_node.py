from app.graph.state import State,Plan

from langchain.messages import SystemMessage, HumanMessage
from llm.prompts.prompts import ORCHESTRATION_SYSTEM
from llm.models import llm

from logger import get_logger
from custom_execption import CustomException

logger=get_logger(__name__)


def orchestrator_node(state: State):
    try:

        planner = llm.with_structured_output(Plan)

        evidence = state.get("evidence", [])
        mode = state.get("mode", "closed_book")

        plan = planner.invoke(
            [
                SystemMessage(content=ORCHESTRATION_SYSTEM),
                HumanMessage(
                    content=(
                        f"Topic: {state['topic']}\n"
                        f"Mode: {mode}\n\n"
                        f"Evidence (ONLY use for fresh claims; may be empty):\n"
                        f"{[e.model_dump() for e in evidence]}"
                    )
                ),
            ]
        )
        logger.info("Tavily Search Completed")

        return {"plan": plan}

    except Exception as e:
            logger.error(f"Error in Orchestrator Node {e}")
            raise CustomException("Error in Orchestrator Node",e)