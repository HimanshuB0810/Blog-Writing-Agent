from app.graph.state import *
from langgraph.graph import StateGraph, START, END

from app.graph.nodes.reducer import *
from app.image_generation.router import generate_images

from logger import get_logger
from custom_execption import CustomException
logger = get_logger(__name__)

reducer_graph = StateGraph(State)
reducer_graph.add_node("merge_content",merge_content)
reducer_graph.add_node("decide_images",decide_images)
reducer_graph.add_node("generate_images",generate_images)
reducer_graph.add_node("replace_image_placeholders",replace_image_placeholders)

reducer_graph.add_edge(START,"merge_content")
reducer_graph.add_edge("merge_content","decide_images")
reducer_graph.add_edge("decide_images","generate_images")
reducer_graph.add_edge("generate_images","replace_image_placeholders")
reducer_graph.add_edge("replace_image_placeholders",END)

try:
    reducer_subgraph = reducer_graph.compile()
    logger.info("Reducer SubGraph Compiled Successfully")
except Exception as e:
        logger.error(f"Error in Reducer SubGraph {e}")
        raise CustomException("Error in Reducer SubGraph",e)