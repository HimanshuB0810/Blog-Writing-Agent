from typing import List
from langchain_community.tools.tavily_search import TavilySearchResults

from app.graph.state import *
from langchain.messages import SystemMessage, HumanMessage
from llm.prompts.prompts import RESEARCH_SYSTEM
from llm.models import llm

from logger import get_logger
from custom_execption import CustomException

logger=get_logger(__name__)

def _tavily_search(query: str, max_results: int = 3) -> List[dict]:

    try:
    
        tool = TavilySearchResults(max_results=max_results)
        results = tool.invoke({"query": query})

        normalized: List[dict] = []
        for r in results or []:
            normalized.append(
                {
                    "title": r.get("title") or "",
                    "url": r.get("url") or "",
                    "snippet": r.get("content") or r.get("snippet") or "",
                    "published_at": r.get("published_date") or r.get("published_at"),
                    "source": r.get("source"),
                }
            )
            logger.info("Tavily Search Completed")
        return normalized

    except Exception as e:
            logger.error(f"Error during Tavily Search Node {e}")
            raise CustomException("Error while Tavily Search",e)


def research_node(state: State) -> dict:
    try:
        queries = (state.get("queries", [] or []))
        max_results = 2

        raw_results: List[dict] = []

        for q in queries:
            raw_results.extend(_tavily_search(q, max_results=max_results))

        if not raw_results:
            return {"evidence": []}

        extractor = llm.with_structured_output(EvidencePack)
        pack = extractor.invoke(
            [
                SystemMessage(content=RESEARCH_SYSTEM),
                HumanMessage(content=f"Raw results:\n{raw_results}"),
            ]
        )

        # Deduplicate by URL
        dedup = {}
        for e in pack.evidence:
            if e.url:
                dedup[e.url] = e

        logger.info("Research Node Completed")
        
        return {"evidence": list(dedup.values())}

    except Exception as e:
                logger.error(f"Error during Research Node {e}")
                raise CustomException("Error in Research Node",e)