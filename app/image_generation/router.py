import os
from pathlib import Path
from app.graph.state import *
from app.image_generation.flux import _huggingface_generate_image
from app.image_generation.graphviz import render_flowchart

PROJECT_ROOT = Path(__file__).resolve().parents[2]
# IMAGE_DIR = PROJECT_ROOT / "images"
BLOG_DIR = PROJECT_ROOT / "BLOG"
IMAGE_DIR = BLOG_DIR / "images"

BLOG_DIR.mkdir(parents=True,exist_ok=True)

IMAGE_DIR.mkdir(parents=True,exist_ok=True)


from logger import get_logger
from custom_execption import CustomException
logger = get_logger(__name__)

def generate_images(state: State):

    try:

        image_specs = state["image_specs"]

        generated_images = []

        for spec in image_specs:

            
            # TECHNICAL → GRAPHVIZ
            
            if spec["image_type"] == "technical":

                flowchart_data = spec.get("flowchart")

                if not flowchart_data:
                    raise ValueError(
                        f"No flowchart specification found for "
                        f"{spec['filename']}"
                    )

                flowchart_spec = FlowchartSpec.model_validate(
                    flowchart_data
                )

                # output_path = (
                #     Path("images") /
                #     Path(spec["filename"]).with_suffix("")
                # )

                output_path = IMAGE_DIR / Path(spec["filename"]).with_suffix("")

                render_flowchart(
                    flowchart_spec,
                    str(output_path)
                )
                relative_path = Path("images") / Path(spec["filename"]).with_suffix(".svg").as_posix()
                path = str(relative_path) 


            # DECORATIVE → FLUX

            elif spec["image_type"] == "decorative":

                image = _huggingface_generate_image(
                    spec["prompt"]
                )

                # output_path = Path("images") / spec["filename"]

                # output_path.parent.mkdir(
                #     parents=True,
                #     exist_ok=True
                # )
                
                output_path = IMAGE_DIR / Path(spec["filename"]).with_suffix(".png")
                relative_path = Path("images") / Path(spec["filename"]).with_suffix(".png").as_posix()



                image.save(output_path)

                path = str(relative_path)


            else:
                raise ValueError(
                    f"Unknown image type: {spec['image_type']}"
                )


            generated_images.append({
                "placeholder": spec["placeholder"],
                "path": path,
                "alt": spec["alt"],
                "caption": spec["caption"]
            })

        logger.info("Image Generated and saved in the Images Folder")
        return {
            "generated_images": generated_images
        }
    except Exception as e:
        logger.error(f"Error in router.py {e}")
        raise CustomException("Error while Routing Image Generation",e)