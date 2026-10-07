import os
from app.graph.state import *
from logger import get_logger
from custom_execption import CustomException
logger = get_logger(__name__)

from graphviz import Digraph


def render_flowchart(spec: FlowchartSpec, output_path: str):

    try:

        dot = Digraph(format="svg")

        dot.attr(
            rankdir="TB",
            splines="ortho"
        )

        dot.attr(
            "node",
            shape="box",
            style="rounded"
        )

        for node in spec.nodes:
            dot.node(
                node.id,
                node.label
            )

        for edge in spec.edges:
            dot.edge(
                edge.source,
                edge.target,
                label=edge.label
            )

        dot.render(
            output_path,
            cleanup=True
        )
        logger.info("Graphviz Made")
    except Exception as e:
        logger.error(f"Error in Image Generation {e}")
        raise CustomException("Error in Image Generation",e)