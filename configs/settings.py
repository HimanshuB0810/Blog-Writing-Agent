import os
from dotenv import load_dotenv

load_dotenv()

# API Keys

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY")


# LLM Configuration

LLM_MODEL = "gemini-3.5-flash-lite"
LLM_TEMPERATURE = 0.7


# Image Generation

FLUX_MODEL = "black-forest-labs/FLUX.1-schnell"


# Paths

IMAGE_DIR = "images"
OUTPUT_DIR = "outputs"


# Blog Configuration

MAX_IMAGES = 2