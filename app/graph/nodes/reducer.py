from app.graph.state import *

from langchain.messages import SystemMessage, HumanMessage
from llm.prompts.prompts import IMAGE_PLANNER_SYSTEM
from llm.models import llm
from pathlib import Path

from logger import get_logger
from custom_execption import CustomException
logger = get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BLOG_DIR = PROJECT_ROOT / "BLOG"
BLOG_DIR.mkdir(parents=True,exist_ok=True)

def merge_content(state: State) -> dict:
    try:

        plan = state["plan"]
        
        ordered_sections = [md for _, md in sorted(state["sections"], key=lambda x: x[0])]
        body = "\n\n".join(ordered_sections).strip()
        merged_md = f"# {plan.blog_title}\n\n{body}\n"

        logger.info("Merging Content Done")

        return {"merged_md":merged_md}
    except Exception as e:
            logger.error(f"Error in Merge Content {e}")
            raise CustomException("Error while Merging Content",e)

def decide_images(state: State) -> dict:
    plan = state["plan"]
    assert plan is not None
    merged_md = state["merged_md"]

    planner = llm.with_structured_output(GlobalImagePlan)
    try:
        image_plan = planner.invoke(
            [
                SystemMessage(content=IMAGE_PLANNER_SYSTEM),
                HumanMessage(
                    content=(
                        f"Blog kind: {plan.blog_kind}\n"
                        f"Topic: {state['topic']}\n\n"
                        "Insert placeholders + propose image prompts.\n\n"
                        f"{merged_md}"
                    )
                ),
            ]
        )
    except Exception:
        # if the planner fails, ship the blog without images
        return {"md_with_placeholders": merged_md, "image_specs": []}

    logger.info("Decide Images Done and Markdown with Placeholders")
    return{
            "md_with_placeholders":image_plan.md_with_placeholders,
            "image_specs": [img.model_dump() for img in image_plan.images]
        }
    
def replace_image_placeholders(state: State):
    try:

        md = state["md_with_placeholders"]

        for image in state["generated_images"]:

            markdown_image = (
                f"![{image['alt']}]"
                f"({image['path']})\n\n"
                f"*{image['caption']}*"
            )

            md = md.replace(image["placeholder"],markdown_image)

        plan = state['plan']
        filename = f"{plan.blog_title}.md"

        output_path = BLOG_DIR / filename
        
        output_path.write_text(
                md,
                encoding="utf-8"
            )
        logger.info(f"Blog saved to: {output_path}")
        logger.info("Replaced placeholder with Images")
        return {"final": md}

    except Exception as e:
            logger.error(f"Error in Replacing placeholder with Images {e}")
            raise CustomException("Error while Replacing placeholder with Images",e)