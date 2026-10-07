from pydantic import Field, BaseModel
from typing import List, Optional, Literal, TypedDict, Annotated
import operator


# STATE FOR GRAPHVIZ
class FlowNode(BaseModel):
    id: str
    label: str


class FlowEdge(BaseModel):
    source: str
    target: str
    label: str = ""


class FlowchartSpec(BaseModel):
    nodes: List[FlowNode]
    edges: List[FlowEdge]


# STATES FOR OTHER NODES

class Task(BaseModel):
    id: int
    title: str

    goal: str = Field(description="One sentence describing what the reader should be able to do/understand after this section.",)
    bullets: List[str] = Field(
        min_length=3,
        max_length=5,
        description="3–5 concrete, non-overlapping subpoints to cover in this section.",
    )
    target_words: int = Field(description="Target word count for this section (120–300).")

    tags: List[str] = Field(default_factory=list)
    requires_research: bool = False
    requires_citations: bool = False
    requires_code: bool = False


class Plan(BaseModel):
    blog_title: str
    audience: str
    tone: str
    blog_kind: Literal["explainer", "tutorial", "news_roundup", "comparison", "system_design"] = "explainer"
    constraints: List[str] = Field(default_factory=list)
    tasks: List[Task]


class EvidenceItem(BaseModel):
    title: str
    url: str
    published_at: Optional[str] = None  
    snippet: Optional[str] = None
    source: Optional[str] = None


class RouterDecision(BaseModel):
    needs_research: bool
    mode: Literal["closed_book", "hybrid", "open_book"]
    queries: List[str] = Field(default_factory=list)


class EvidencePack(BaseModel):
    evidence: List[EvidenceItem] = Field(default_factory=list)

class ImageSpec(BaseModel):
    placeholder: str = Field(description="examples= [[IMAGE_1]]")
    filename: str = Field(description="Save under images/ example = abc_flow.png")
    alt: str
    caption: str
    prompt: str = Field(description="Prompt to send to the image model for images")
    size: Literal["1024x1024", "1024x1536", "1536x1536"] = "1024x1024"
    quality: Literal["low", "medium", "high"] = "medium"
    image_type: Literal[ "technical", "decorative"]

    flowchart: FlowchartSpec | None = Field(default=None, description="Required for technical images. Must be null for decorative images.")

class GlobalImagePlan(BaseModel):
    md_with_placeholders: str
    images: List[ImageSpec] = Field(default_factory=list)

# MAIN STATE

class State(TypedDict):
    topic: str

    # routing / research
    mode: str
    needs_research: bool
    queries: List[str]
    evidence: List[EvidenceItem]
    plan: Optional[Plan]

    # workers
    sections: Annotated[List[tuple[int, str]], operator.add]  # (task_id, section_md)

    # reducer / image
    merged_md: str
    md_with_placeholders: str
    image_specs: List[dict]

    generated_images: list[dict[str, str]]

    final: str    