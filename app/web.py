from flask import Flask, Response, jsonify, render_template, request, send_file, send_from_directory, url_for
from pathlib import Path
from io import BytesIO
from datetime import datetime
import json
import queue
import threading
import uuid
import zipfile
import re

from app.graph.workflow import app as graph_app
from logger import get_logger
from custom_execption import CustomException

logger = get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BLOG_DIR = PROJECT_ROOT / "BLOG"
IMAGE_DIR = BLOG_DIR / "images"

web_app = Flask(__name__, template_folder="templates", static_folder="static")
web_app.config["JSON_SORT_KEYS"] = False

JOBS = {}
JOBS_LOCK = threading.Lock()


def _initial_state(topic: str) -> dict:
    return {
        "topic": topic,
        "mode": "",
        "needs_research": False,
        "queries": [],
        "evidence": [],
        "plan": None,
        "sections": [],
        "merged_md": "",
        "md_with_placeholders": "",
        "image_specs": [],
        "generated_images": [],
        "final": "",
    }


def _event(message: str, stage: str, status: str = "running", data=None) -> str:
    payload = {
        "type": "progress",
        "stage": stage,
        "status": status,
        "message": message,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
    }
    if data:
        payload["data"] = data
    return f"data: {json.dumps(payload, default=str)}\n\n"


def _node_event(node_name: str) -> tuple[str, str]:
    mapping = {
        "router": ("Planning", "planning"),
        "research": ("Researching", "research"),
        "orchestrator": ("Planning sections", "planning"),
        "worker": ("Writing blog sections", "writing"),
        "reducer": ("Finalizing content and visuals", "finalizing"),
        "merge_content": ("Merging written sections", "finalizing"),
        "decide_images": ("Planning images", "images"),
        "generate_images": ("Generating images", "images"),
        "replace_image_placeholders": ("Finalizing blog", "finalizing"),
    }
    return mapping.get(node_name, (node_name.replace("_", " ").title(), node_name))


def _run_job(job_id: str, topic: str):
    events = JOBS[job_id]["queue"]
    try:
        events.put(_event("Starting Blog Writing Agent", "start"))

        final_state = None
        last_node = None

        # stream_mode="updates" yields actual node/subgraph state updates.
        for update in graph_app.stream(_initial_state(topic), stream_mode="updates"):
            if not update:
                continue

            node_name = next(iter(update))
            node_update = update[node_name] or {}
            last_node = node_name

            message, stage = _node_event(node_name)

            if node_name == "router":
                mode = node_update.get("mode")
                needs_research = node_update.get("needs_research")
                if needs_research:
                    message = "Research required; preparing web research"
                else:
                    message = "Research not required; using closed-book planning"
                events.put(_event(message, stage, data={"mode": mode, "needs_research": needs_research}))

            elif node_name == "research":
                evidence = node_update.get("evidence", [])
                events.put(_event(
                    f"Research completed ({len(evidence)} sources)",
                    stage,
                    data={"source_count": len(evidence)}
                ))

            elif node_name == "orchestrator":
                plan = node_update.get("plan")
                task_count = len(getattr(plan, "tasks", [])) if plan is not None else 0
                events.put(_event(
                    f"Plan created with {task_count} sections",
                    stage,
                    data={"sections": task_count}
                ))

            elif node_name == "worker":
                sections = node_update.get("sections", [])
                events.put(_event(
                    f"Section writing completed ({len(sections)} update(s))",
                    stage,
                    data={"sections_completed": len(sections)}
                ))

            elif node_name == "decide_images":
                image_specs = node_update.get("image_specs", [])
                events.put(_event(
                    f"Image plan created ({len(image_specs)} visual(s))",
                    stage,
                    data={"images": len(image_specs)}
                ))

            elif node_name == "generate_images":
                images = node_update.get("generated_images", [])
                events.put(_event(
                    f"Image generation completed ({len(images)} image(s))",
                    stage,
                    data={"images": len(images)}
                ))

            else:
                events.put(_event(message, stage))

            final_state = node_update if node_update.get("final") else final_state

        # The stream does not necessarily expose a final aggregated object,
        # so retrieve the completed state with one final invoke only when needed.
        if not final_state or "final" not in final_state:
            final_state = graph_app.invoke(_initial_state(topic))

        blog_id = job_id
        with JOBS_LOCK:
            JOBS[job_id]["state"] = final_state
            JOBS[job_id]["status"] = "completed"

        events.put(_event("Blog generation completed", "complete", "completed", {
            "blog_id": blog_id,
        }))
    except Exception as exc:
        logger.exception("Blog generation failed")
        with JOBS_LOCK:
            JOBS[job_id]["status"] = "failed"
            JOBS[job_id]["error"] = str(exc)
        events.put(_event(f"Generation failed: {exc}", "error", "failed"))
    finally:
        events.put(None)


@web_app.get("/")
def index():
    return render_template("index.html")


@web_app.post("/api/generate")
def generate():
    payload = request.get_json(silent=True) or {}
    topic = str(payload.get("topic", "")).strip()

    if not topic:
        return jsonify({"error": "Blog topic is required."}), 400
    if len(topic) > 500:
        return jsonify({"error": "Blog topic must be 500 characters or fewer."}), 400

    job_id = uuid.uuid4().hex
    job_queue = queue.Queue()

    with JOBS_LOCK:
        JOBS[job_id] = {
            "status": "running",
            "topic": topic,
            "queue": job_queue,
            "state": None,
            "error": None,
        }

    thread = threading.Thread(target=_run_job, args=(job_id, topic), daemon=True)
    thread.start()

    return jsonify({
        "id": job_id,
        "status": "running",
        "stream_url": url_for("stream_events", job_id=job_id),
        "blog_url": url_for("get_blog", job_id=job_id),
    }), 202


@web_app.get("/api/generate/<job_id>/stream")
def stream_events(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)

    if not job:
        return jsonify({"error": "Generation job not found."}), 404

    def generate():
        while True:
            item = job["queue"].get()
            if item is None:
                break
            yield item

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@web_app.get("/api/blog/<job_id>")
def get_blog(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)

    if not job:
        return jsonify({"error": "Blog not found."}), 404
    if job["status"] == "failed":
        return jsonify({"error": job["error"]}), 500
    if job["status"] != "completed":
        return jsonify({"status": job["status"]}), 202

    state = job["state"]
    return jsonify({
        "id": job_id,
        "topic": job["topic"],
        "markdown": state.get("final", ""),
        "download_url": url_for("download_markdown", job_id=job_id),
        "package_url": url_for("download_package", job_id=job_id),
    })


@web_app.get("/api/blog/<job_id>/images/<path:filename>")
def blog_image(job_id: str, filename: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)

    if not job:
        return jsonify({"error": "Blog not found."}), 404

    safe_name = Path(filename).name
    allowed_images = {
        Path(item["path"]).name
        for item in (job.get("state") or {}).get("generated_images", [])
    }
    if safe_name not in allowed_images:
        return jsonify({"error": "Image not found."}), 404

    return send_from_directory(IMAGE_DIR, safe_name)


def _job_blog_path(job_id: str) -> Path:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job or job["status"] != "completed":
        return None

    markdown = job["state"].get("final", "")
    files = list(BLOG_DIR.glob("*.md"))
    if not files:
        return None

    topic = job["topic"]
    candidates = sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)
    for candidate in candidates:
        try:
            if candidate.read_text(encoding="utf-8") == markdown:
                return candidate
        except OSError:
            continue
    return candidates[0]


@web_app.get("/api/blog/<job_id>/download")
def download_markdown(job_id: str):
    markdown_path = _job_blog_path(job_id)
    if markdown_path is None:
        return jsonify({"error": "Completed blog file not found."}), 404

    return send_file(
        markdown_path,
        as_attachment=True,
        download_name=markdown_path.name,
        mimetype="text/markdown",
    )


@web_app.get("/api/blog/<job_id>/package")
def download_package(job_id: str):
    markdown_path = _job_blog_path(job_id)
    if markdown_path is None:
        return jsonify({"error": "Completed blog file not found."}), 404

    with JOBS_LOCK:
        job = JOBS.get(job_id)

    state = job["state"]
    image_names = {
        Path(item["path"]).name
        for item in state.get("generated_images", [])
    }

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(markdown_path, arcname=f"BLOG/{markdown_path.name}")
        for image_name in image_names:
            image_path = IMAGE_DIR / image_name
            if image_path.is_file():
                archive.write(image_path, arcname=f"BLOG/images/{image_name}")

    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"blog_{job_id}.zip",
        mimetype="application/zip",
    )


# Development entry point.
if __name__ == "__main__":
    web_app.run(debug=True)
