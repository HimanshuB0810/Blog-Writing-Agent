from pathlib import Path

from langgraph.types import interrupt
from langchain_core.messages import SystemMessage, HumanMessage

from app.graph.state import State
from llm.models import llm
from llm.prompts.prompts import REVIEW_BLOG

from logger import get_logger
from custom_execption import CustomException

logger = get_logger(__name__)


def human_review(state: State) -> dict:
    try:

        # Review the latest version available.
        blog = state.get("final_after_review") or state["final"]

        decision = interrupt({
            "blog": blog,
            "question": "Do you approve this blog?",
            "instruction": (
                "Approve the blog or request changes "
                "with specific feedback."
            )
        })

        approved = bool(decision.get("approved", False))
        feedback = str(decision.get("feedback", "")).strip()

        if not approved and not feedback:
            raise ValueError("Feedback is required when requesting revisions.")

        logger.info("Interrupt Occured")

        return {
            "approved": approved,
            "feedback": "" if approved else feedback
        }
    except Exception as e:
            logger.error(f"Error in human_review Node {e}")
            raise CustomException("Error in human_review Node",e)


def revise_blog(state: State) -> dict:
    try:
        current_blog = (state.get("final_after_review") or state["final"])

        response = llm.invoke([
            SystemMessage(content=REVIEW_BLOG),
            HumanMessage(content=f"""
            CURRENT BLOG:
            {current_blog}

            HUMAN FEEDBACK:
            {state["feedback"]}
            """)
        ])

        content = response.content

        if isinstance(content, list):
            content = "\n".join(
                block["text"]
                if isinstance(block, dict) and "text" in block
                else str(block)
                for block in content
            )

        logger.info("Blog Revised According to the Feedback")

        return {
            "final_after_review": content.strip(),
            "approved": False,
            "feedback": ""
        }

    except Exception as e:
            logger.error(f"Error in human_review Node {e}")
            raise CustomException("Error in human_review Node",e)


def route_after_review(state: State) -> str:
    if state["approved"]:
        return "approved"

    return "revise"


def save_approved_blog(state: State) -> dict:
    project_root = Path(__file__).resolve().parents[2]
    blog_dir = project_root.parent / "REVISED_BLOG"
    blog_dir.mkdir(parents=True, exist_ok=True)

    approved_blog = (
        state.get("final_after_review") or state["final"]
    )

    title = state["plan"].blog_title
    output_path = blog_dir / f"{title}.md"

    output_path.write_text(
        approved_blog,
        encoding="utf-8"
    )

    return {
        "final_after_review": approved_blog
    }
