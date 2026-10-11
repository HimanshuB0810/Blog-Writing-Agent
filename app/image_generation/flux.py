import os
from pathlib import Path
from urllib.parse import quote

import requests
from dotenv import load_dotenv
from PIL import Image
from io import BytesIO

from custom_execption import CustomException
from logger import get_logger

logger = get_logger(__name__)

load_dotenv()

API_KEY = os.getenv("POLLINATIONS_API_KEY")


def generate_image(prompt: str, output_path: str) -> str:
    try:
            

        if not API_KEY:
            raise ValueError("POLLINATIONS_API_KEY is missing from .env")

        url = f"https://gen.pollinations.ai/image/{quote(prompt, safe='')}"

        params = {
            "model": "flux",
            "width": 1024,
            "height": 1024,
        }

        headers = {
            "Authorization": f"Bearer {API_KEY}"
        }

        response = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=180,
        )
        response.raise_for_status()

        # Convert the returned image to PNG.
        image = Image.open(BytesIO(response.content)).convert("RGB")

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path, format="PNG")

        print(f"Image saved to: {path}")

    except Exception as e:
            logger.error(f"Error in Generating Image {e}")
            raise CustomException("Error while Generating Image",e)
    
    return str(path)


if __name__ == "__main__":
    prompt = (
        "Minimal editorial illustration of an AI research workspace, "
        "abstract neural network connections, soft blue and violet palette, "
        "clean composition, modern technology blog aesthetic, no text"
    )

    generate_image(prompt, "generated_images/decorative.png")