from langchain_google_genai import ChatGoogleGenerativeAI

from configs.settings import LLM_MODEL, LLM_TEMPERATURE

llm = ChatGoogleGenerativeAI(model=LLM_MODEL,temperature=LLM_TEMPERATURE)
