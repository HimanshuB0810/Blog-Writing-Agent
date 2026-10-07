import os
from huggingface_hub import InferenceClient
from configs.settings import FLUX_MODEL

from logger import get_logger
from custom_execption import CustomException
logger = get_logger(__name__)

def _huggingface_generate_image(prompt: str):
    """
    Generate an image using FLUX.1-schnell through
    Hugging Face Inference Providers.

    Requires:
        HUGGINGFACEHUB_API_TOKEN
    """
    try:

        api_key = os.environ.get("HUGGINGFACEHUB_API_TOKEN")

        if not api_key:
            raise RuntimeError(
                "HUGGINGFACEHUB_API_TOKEN is not set."
            )

        client = InferenceClient(
            api_key=api_key
        )

        image = client.text_to_image(
            prompt=prompt,
            model=FLUX_MODEL
        )

        logger.info("Image Generation Completed")
        return image
    
    except Exception as e:
            logger.error(f"Error in Image Generation {e}")
            raise CustomException("Error in Image Generation",e)