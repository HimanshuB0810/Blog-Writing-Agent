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
    # Do not wrap interrupt() in a broad try/except.
    # LangGraph uses an internal control-flow exception to pause execution.
    blog = state.get("final_after_review") or state["final"]

    decision = interrupt({
        "blog": blog,
        "question": "Do you approve this blog?",
        "instruction": (
            "Approve the blog or request changes with specific feedback."
        ),
    })

    if not isinstance(decision, dict):
        raise ValueError("Review response must be a dictionary.")

    approved = decision.get("approved")
    if not isinstance(approved, bool):
        raise ValueError("'approved' must be a boolean.")

    feedback = str(decision.get("feedback", "")).strip()

    if not approved and not feedback:
        raise ValueError("Feedback is required when requesting revisions.")

    logger.info("Human review received")

    return {
        "approved": approved,
        "feedback": "" if approved else feedback,
    }


def revise_blog(state: State) -> dict:
    try:
        current_blog = state.get("final_after_review") or state["final"]

        response = llm.invoke([
            SystemMessage(content=REVIEW_BLOG),
            HumanMessage(content=f"""
CURRENT BLOG:
{current_blog}

HUMAN FEEDBACK:
{state["feedback"]}

Revise the complete blog according to the feedback. Return only the complete
revised blog in Markdown.
"""),
        ])

        content = response.content

        if isinstance(content, list):
            content = "\n".join(
                block["text"]
                if isinstance(block, dict) and "text" in block
                else str(block)
                for block in content
            )

        revised_blog = content.strip()
        if not revised_blog:
            raise ValueError("The model returned an empty revised blog.")

        logger.info("Blog revised according to human feedback")

        return {
            "final_after_review": revised_blog,
            "approved": False,
            "feedback": "",
        }

    except Exception as e:
        logger.exception("Error in revise_blog node")
        raise CustomException("Error in revise_blog node", e)


def route_after_review(state: State) -> str:
    return "approved" if state["approved"] else "revise"


def save_approved_blog(state: State) -> dict:
    project_root = Path(__file__).resolve().parents[2]
    blog_dir = project_root.parent / "REVISED_BLOG"
    blog_dir.mkdir(parents=True, exist_ok=True)

    approved_blog = state.get("final_after_review") or state["final"]
    title = state["plan"].blog_title

    # Avoid path traversal and ensure the result remains a Markdown file.
    safe_title = Path(title).name.replace("/", "_").replace("\\", "_")
    output_path = blog_dir / f"{safe_title}.md"
    output_path.write_text(approved_blog, encoding="utf-8")

    logger.info("Approved blog saved to %s", output_path)
    return {"final_after_review": approved_blog}
