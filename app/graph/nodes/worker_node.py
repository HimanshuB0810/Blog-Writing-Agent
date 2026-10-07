from app.graph.state import *

from langchain.messages import SystemMessage, HumanMessage
from llm.prompts.prompts import WORKER_SYSTEM
from llm.models import llm
from langgraph.types import Send

from logger import get_logger
from custom_execption import CustomException

logger = get_logger(__name__)

def fanout(state: State):
    try:
        logger.info("Fanout Started")
        return [
            Send(
                "worker",
                {
                    "task": task.model_dump(),
                    "topic": state["topic"],
                    "mode": state["mode"],
                    "plan": state["plan"].model_dump(),
                    "evidence": [e.model_dump() for e in state.get("evidence", [])],
                },
            )
            for task in state["plan"].tasks
        ]
    except Exception as e:
        logger.error(f"Error in Fanout {e}")
        raise CustomException("Error during Fanout",e)


def worker_node(payload: dict) -> dict:

    try:
    
        task = Task(**payload["task"])
        plan = Plan(**payload["plan"])
        evidence = [EvidenceItem(**e) for e in payload.get("evidence", [])]
        topic = payload["topic"]
        mode = payload.get("mode", "closed_book")

        bullets_text = "\n- " + "\n- ".join(task.bullets)

        evidence_text = ""
        if evidence:
            evidence_text = "\n".join(
                f"- {e.title} | {e.url} | {e.published_at or 'date:unknown'}".strip()
                for e in evidence[:20]
            )

        response = llm.invoke(
            [
                SystemMessage(content=WORKER_SYSTEM),
                HumanMessage(
                    content=(
                        f"Blog title: {plan.blog_title}\n"
                        f"Audience: {plan.audience}\n"
                        f"Tone: {plan.tone}\n"
                        f"Blog kind: {plan.blog_kind}\n"
                        f"Constraints: {plan.constraints}\n"
                        f"Topic: {topic}\n"
                        f"Mode: {mode}\n\n"
                        f"Section title: {task.title}\n"
                        f"Goal: {task.goal}\n"
                        f"Target words: {task.target_words}\n"
                        f"Tags: {task.tags}\n"
                        f"requires_research: {task.requires_research}\n"
                        f"requires_citations: {task.requires_citations}\n"
                        f"requires_code: {task.requires_code}\n"
                        f"Bullets:{bullets_text}\n\n"
                        f"Evidence (ONLY use these URLs when citing):\n{evidence_text}\n"
                    )
                ),
            ]
        )    
        
        # Convert Gemini's content into a normal string
        if isinstance(response.content, str):
            section_md = response.content.strip()

        elif isinstance(response.content, list):
            section_md = "\n".join(
                block["text"]
                for block in response.content
                if isinstance(block, dict)
                and block.get("type") == "text"
                and block.get("text")
            ).strip()

        else:
            raise TypeError(
                f"Unexpected response.content type: {type(response.content)}"
            )

        logger.info("Woker Node Completed")
        return {"sections": [(task.id, section_md)]}

    except Exception as e:
        logger.error(f"Error in Fanout {e}")
        raise CustomException("Error during Fanout",e)