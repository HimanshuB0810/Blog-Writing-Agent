# Blog Writing Agent

An AI-powered technical blog generation system that turns a topic into a structured Markdown article with conditional web research, parallel section drafting, automatically generated visuals, and a human-in-the-loop (HITL) review cycle. Its Flask interface streams workflow progress, presents the completed draft for approval or revision feedback, and provides downloadable Markdown and ZIP outputs after approval.

## 🎬 Project Demo
Watch the Blog Writing Agent in action:

https://github.com/user-attachments/assets/c90a9117-9ac3-423c-87c2-f36c7a42c699


## Overview

The application uses a **LangGraph workflow** to coordinate the blog-writing process:

1. **Route the topic** — determine whether the topic can be handled from general knowledge or requires current web research.
2. **Research (when needed)** — search the web with Tavily and prepare a deduplicated evidence set.
3. **Plan the article** — use a structured plan with a title, intended audience, tone, blog type, and section-level tasks.
4. **Write sections in parallel** — generate each planned section as Markdown using LangGraph worker nodes.
5. **Merge and plan visuals** — combine sections in the intended order and identify useful image placements.
6. **Generate images** — create technical flowcharts with Graphviz and decorative illustrations through the Pollinations image API using the FLUX model.
7. **Review the draft (HITL)** — pause the LangGraph workflow and show the generated blog for human review.
8. **Revise or approve** — the reviewer can approve the blog or provide feedback; the agent revises the draft and presents it for review again until approved.
9. **Save the approved article** — store the approved Markdown in `REVISED_BLOG/` and make it available to the UI for download.

The system is designed for technical content such as AI/ML concepts, software engineering tutorials, architecture explainers, implementation guides, and topic roundups.

## Features

- **Agentic writing workflow:** specialized routing, research, orchestration, writing, and reduction stages.
- **Conditional web research:** the router decides whether a topic needs current web research and uses Tavily Search only when required.
- **Source citations:** for research-backed topics, generated sections can link claims to URLs in the retrieved evidence so readers can inspect the original sources. Citations still require human verification.
- **Human-in-the-loop review:** generation pauses after the draft and visuals are prepared, letting a user approve the blog or request revisions with specific feedback.
- **Feedback-driven revision loop:** the LLM revises the full draft according to the feedback and returns it to the reviewer until approval.
- **Approval-gated output:** the approved version is saved separately in `REVISED_BLOG/`.
- **Structured planning:** defines sections, goals, key points, word-count targets, and citation/code requirements.
- **Parallel section generation:** independent blog sections are drafted through LangGraph worker tasks.
- **Automatic visual planning:** proposes relevant image locations and descriptions from the generated Markdown.
- **Two types of visuals:**
  - **Technical diagrams:** rendered as SVG flowcharts from structured node-and-edge data using Graphviz.
  - **Decorative images:** generated as PNG images through the Pollinations image endpoint with the FLUX model.
- **Flask web interface:** submit a topic, monitor live stages and progress messages, and preview the completed article.
- **Live updates:** workflow progress is streamed to the browser using Server-Sent Events (SSE).
- **Download options:** download the generated Markdown file or a ZIP containing the blog and its generated images.
- **Logging and exception handling:** application modules use shared logging and custom exception handling.

## Tech Stack

| Component | Technology |
|---|---|
| Language | Python |
| LLM integration | LangChain, Google Generative AI |
| LLM configured in the repository | `gemini-3.5-flash-lite` (configured in `configs/settings.py`) |
| Agent workflow and orchestration | LangGraph |
| Human-in-the-loop | LangGraph `interrupt()`, `InMemorySaver` checkpointer, Flask review endpoint |
| Web research | Tavily Search |
| Web application | Flask |
| Frontend | HTML, CSS, JavaScript, Marked.js, DOMPurify |
| Technical diagrams | Graphviz |
| Decorative image generation | Pollinations API with FLUX |
| Data validation / structured outputs | Pydantic models |
| Output format | Markdown, SVG, PNG, ZIP |

## Architecture

The graph routes the topic to research when needed, writes and illustrates the article, and then pauses for human approval. A request for changes loops through revision and review again.

```text
User enters a blog topic
          |
          v
     Flask frontend
          |
          v
      Router node
       /       \\
 research      skip research
    |               |
    v               |
 Tavily search      |
    |               |
    +-------+-------+
            |
            v
    Orchestrator / planner
            |
            v
   Parallel section workers
            |
            v
       Merge sections
            |
            v
      Plan visuals
            |
            v
     Generate images
       /          \\
 Graphviz SVG    FLUX PNG
       \\          /
            v
 Replace image placeholders
            |
            v
      Human review
       /         \\
  approve      request changes
     |               |
     v               v
 Save approved    Revise blog
     |               |
     v               +----> Human review
 Markdown / ZIP
 downloads
```

### Main workflow modules

- `app/graph/workflow.py` — defines and compiles the main LangGraph workflow, including an in-memory checkpointer and the review/revision loop.
- `app/graph/nodes/hitl.py` — pauses execution for human approval, validates feedback, revises the blog, and saves the approved version.
- `app/graph/state.py` — contains the shared graph state and Pydantic models for the plan, research evidence, and visual specifications.
- `app/graph/nodes/router_node.py` — classifies the topic and decides whether research is required.
- `app/graph/nodes/research_node.py` — runs Tavily searches and normalizes the retrieved evidence.
- `app/graph/nodes/orchestrator_node.py` — produces the structured blog outline.
- `app/graph/nodes/worker_node.py` — writes individual sections in parallel.
- `app/graph/nodes/subgraph/reducer_subgraph.py` — coordinates merging, visual planning, image generation, and finalization.
- `app/image_generation/graphviz.py` — renders structured technical flowcharts to SVG.
- `app/image_generation/flux.py` — requests decorative images from Pollinations and saves them as PNG.
- `app/image_generation/router.py` — routes each visual specification to the appropriate generator.
- `app/web.py` — implements the Flask API, background generation jobs, SSE progress, preview, and download endpoints.
- `app/templates/` and `app/static/` — contain the HTML template, CSS, and browser JavaScript.

## Project Structure

The following is a simplified view of the relevant files:

```text
Blog-Writing-Agent/
├── app/
│   ├── graph/
│   │   ├── nodes/
│   │   │   ├── orchestrator_node.py
│   │   │   ├── research_node.py
│   │   │   ├── router_node.py
│   │   │   ├── worker_node.py
│   │   │   ├── hitl.py
│   │   │   ├── reducer.py
│   │   │   └── subgraph/
│   │   │       └── reducer_subgraph.py
│   │   ├── state.py
│   │   └── workflow.py
│   ├── image_generation/
│   │   ├── flux.py
│   │   ├── graphviz.py
│   │   └── router.py
│   ├── static/
│   │   ├── css/style.css
│   │   └── js/script.js
│   ├── templates/
│   │   └── index.html
│   ├── main.py
│   └── web.py
├── configs/
│   └── settings.py
├── llm/
│   ├── models.py
│   └── prompts/
│       └── prompts.py
├── BLOG/                 # Generated drafts and images
├── REVISED_BLOG/          # Blogs approved through human review
├── notebook/              # Step-by-step project development notebooks
│   ├── 1.bwa_basics.ipynb
│   ├── 2_bwa_improved_prompting.ipynb
│   ├── 3.bwa_research.ipynb
│   ├── 4.bwa_images.ipynb
│   ├── 5.bwa_images_flowchart.ipynb
│   └── 6.bwa_with_HITL.ipynb
├── logger.py
├── custom_execption.py
├── requirements.txt
└── setup.py
```

## Development Notebooks

The `notebook/` directory documents the project's step-by-step evolution through Jupyter notebooks, from basic blog generation and prompt improvements to web research, image generation, Graphviz flowcharts, and the human-in-the-loop review workflow. These notebooks are useful for comparing iterations and understanding why features were introduced.

## Prerequisites

- Python 3.10 or later is recommended. The repository contains Python 3.12-generated cache files, but the project does not declare a formal minimum Python version.
- A Google Generative AI API key for the configured LLM.
- A Tavily API key for research-enabled topics.
- A Pollinations API key for decorative image generation.
- Graphviz installed on the operating system for rendering technical flowcharts. The Python package alone may not install the Graphviz system executable.

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/HimanshuB0810/Blog-Writing-Agent.git
cd Blog-Writing-Agent
```

### 2. Create and activate a virtual environment

Linux / macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
python -m venv .venv
.venv\\Scripts\\Activate.ps1
```

### 3. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Install Graphviz

Install the Graphviz system package for your operating system and verify that the `dot` executable is available on your `PATH`.

Ubuntu / Debian:

```bash
sudo apt update
sudo apt install graphviz
dot -V
```

### 5. Configure environment variables

Create a `.env` file in the repository root. Do not commit API keys.

```dotenv
GOOGLE_API_KEY=your_google_generative_ai_api_key
TAVILY_API_KEY=your_tavily_api_key
POLLINATIONS_API_KEY=your_pollinations_api_key
```

The application reads the Google API key through the LLM configuration and uses Tavily for research and Pollinations for decorative images. Keep these credentials private. If you do not need current web research, you can still try an evergreen topic, but the configured model and any image-generation requests still need valid provider access.

> **Configuration note:** The current `configs/settings.py` hard-codes the model name `gemini-3.5-flash-lite` and temperature `0.7`. Model availability can change. If the model is unavailable to your API account, update `LLM_MODEL` to a currently supported model before running the app.

## Run the application

Start the Flask application from the repository root:

```bash
python -m app.main
```

Then open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.

Enter a topic in the **Blog topic** field and click **Generate Blog**. The page displays workflow progress as the agent routes, researches when required, plans, writes, and generates visuals. The workflow then pauses at **Human Review**. Inspect the rendered draft, click **Approve** to finish, or provide specific suggestions and click **Request Changes**. The agent revises the blog and returns the updated version for another review. Download links appear after approval.

The repository also contains a direct Flask entry point in `app/web.py`, but `python -m app.main` is the intended entry point for the current layout.

## API Endpoints

The Flask interface currently exposes these endpoints:

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/` | Serve the web interface. |
| `POST` | `/api/generate` | Start a blog-generation job. Requires a JSON body with a `topic` field. |
| `GET` | `/api/generate/<job_id>/stream` | Stream progress events using Server-Sent Events. |
| `GET` | `/api/blog/<job_id>` | Retrieve the blog, current status, or review draft. |
| `POST` | `/api/blog/<job_id>/review` | Approve the draft or submit revision feedback; resumes the paused graph. The JSON body requires `approved` (boolean) and, when rejecting, a non-empty `feedback` string. |
| `GET` | `/api/blog/<job_id>/images/<filename>` | Serve an image generated for the job, if it belongs to that job. |
| `GET` | `/api/blog/<job_id>/download` | Download the Markdown file. |
| `GET` | `/api/blog/<job_id>/package` | Download a ZIP with the Markdown blog and available generated images. |

Example request:

```bash
curl -X POST http://127.0.0.1:5000/api/generate \
  -H "Content-Type: application/json" \
  -d '{"topic":"Demystifying Transformer Architecture and Self-Attention"}'
```

A successful request returns HTTP `202` with a job ID and URLs for progress streaming and retrieving the blog. The topic is required and limited to 500 characters.

## Output

Generated drafts and visuals are stored in `BLOG/` and `BLOG/images/`. After a reviewer approves the content, the approved Markdown is saved in `REVISED_BLOG/`. The web application provides a Markdown download and can package the approved article with its generated images into a ZIP download.

The Markdown contains image links relative to the `BLOG/` directory, for example:

```markdown
![Diagram description](images/example_flow.svg)

*Caption describing the diagram.*
```

The repository also includes example generated articles and assets in `BLOG/`.

## Troubleshooting

- **LLM authentication or model errors:** verify `GOOGLE_API_KEY`, provider access, quota, and the model name in `configs/settings.py`.
- **Research failures:** verify `TAVILY_API_KEY`, internet connectivity, and Tavily account availability.
- **Decorative image failures:** verify `POLLINATIONS_API_KEY` and that the image service is reachable.
- **Graphviz rendering errors:** install the Graphviz system executable and check that `dot -V` succeeds.
- **Missing images in output:** inspect the generation logs and check that the files exist in `BLOG/images/`; image generation depends on external services for decorative images.
- **Dependency conflicts:** use a clean virtual environment and install from `requirements.txt`.

## Security and limitations

- Keep API keys in `.env` and out of version control.
- The current Flask application uses an in-memory job registry, daemon threads, and an `InMemorySaver` checkpointer. Review sessions and graph state are not durable across process restarts; use persistent job storage and a persistent LangGraph checkpointer for production deployment.
- The current Flask entry point runs with `debug=True`; do not expose the development server directly to the public internet.
- Research-dependent accuracy relies on the web results returned by Tavily and on the generated text correctly using the provided evidence.
- LLM outputs and image generation can vary between runs and provider availability may change.
