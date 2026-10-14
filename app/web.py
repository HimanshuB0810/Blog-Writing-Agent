from flask import (
    Flask, Response, jsonify, render_template, request,
    send_file, send_from_directory, url_for,
)
from pathlib import Path
from io import BytesIO
import json
import queue
import threading
import uuid
import zipfile
from datetime import datetime

from langgraph.types import Command

from app.graph.workflow import app as graph_app
from logger import get_logger

logger = get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BLOG_DIR = PROJECT_ROOT / "BLOG"
REVISED_BLOG_DIR = PROJECT_ROOT / "REVISED_BLOG"
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
        "final_after_review": "",
        "feedback": "",
        "approved": False,
    }


def _event(message: str, stage: str, status: str = "running", data=None) -> str:
    payload = {
        "type": "progress",
        "stage": stage,
        "status": status,
        "message": message,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
    }
    if data is not None:
        payload["data"] = data
    return f"data: {json.dumps(payload, default=str)}\n\n"


def _merge_update(state: dict, update: dict) -> None:
    """Collect partial updates for progress logging only."""
    for key, value in update.items():
        if key == "sections":
            state.setdefault("sections", []).extend(value or [])
        else:
            state[key] = value


def _thread_config(job_id: str) -> dict:
    return {"configurable": {"thread_id": job_id}}


def _pending_interrupts(snapshot) -> list:
    """Return payloads from interrupts currently waiting in the graph."""
    pending = []
    for task in snapshot.tasks:
        for interrupt_item in task.interrupts:
            pending.append(interrupt_item.value)
    return pending


def _latest_markdown(state: dict) -> str:
    """Return the approved/revised blog if present, otherwise the original."""
    return state.get("final_after_review") or state.get("final") or ""


def _run_job(job_id: str, topic: str):
    events = JOBS[job_id]["queue"]
    progress_state = _initial_state(topic)
    first_event = True
    config = _thread_config(job_id)

    try:
        for namespace, chunk in graph_app.stream(
            _initial_state(topic),
            config=config,
            stream_mode="updates",
            subgraphs=True,
        ):
            if first_event:
                events.put(_event("Starting Blog Writing Agent", "planning"))
                first_event = False

            if not chunk:
                continue

            node_name = next(iter(chunk.keys()))
            update = next(iter(chunk.values()))
            _merge_update(progress_state, update)
            is_subgraph = bool(namespace)

            if node_name == "router":
                if progress_state.get("needs_research"):
                    events.put(_event(
                        "Research required; routing to web research",
                        "research",
                        data={"mode": progress_state.get("mode")},
                    ))
                else:
                    events.put(_event(
                        "Research not required; continuing with planning",
                        "planning",
                        data={"mode": progress_state.get("mode")},
                    ))

            elif node_name == "research":
                events.put(_event(
                    f"Research completed ({len(progress_state.get('evidence') or [])} sources)",
                    "research",
                    data={"source_count": len(progress_state.get("evidence") or [])},
                ))

            elif node_name == "orchestrator":
                plan = progress_state.get("plan")
                tasks = getattr(plan, "tasks", []) if plan else []
                events.put(_event(
                    f"Blog plan created ({len(tasks or [])} sections)",
                    "planning",
                    data={"sections": len(tasks or [])},
                ))

            elif node_name == "worker":
                events.put(_event(
                    f"Writing in progress ({len(progress_state.get('sections') or [])} section(s) completed)",
                    "writing",
                    data={"sections_completed": len(progress_state.get("sections") or [])},
                ))

            elif is_subgraph and node_name == "merge_content":
                events.put(_event("Merging written sections", "finalizing"))

            elif is_subgraph and node_name == "decide_images":
                count = len(progress_state.get("image_specs") or [])
                events.put(_event(
                    f"Image plan created ({count} visual(s))",
                    "images",
                    data={"images": count},
                ))

            elif is_subgraph and node_name == "generate_images":
                count = len(progress_state.get("generated_images") or [])
                events.put(_event(
                    f"Image generation completed ({count} image(s))",
                    "images",
                    data={"images": count},
                ))

            elif is_subgraph and node_name == "replace_image_placeholders":
                events.put(_event(
                    "Finalizing blog and replacing image placeholders",
                    "finalizing",
                ))

        # Use the checkpoint as the source of truth, not the partial stream state.
        snapshot = graph_app.get_state(config)
        state = dict(snapshot.values)
        pending = _pending_interrupts(snapshot)

        with JOBS_LOCK:
            JOBS[job_id]["state"] = state

        if pending:
            review = pending[0]
            blog = review.get("blog") or _latest_markdown(state)
            with JOBS_LOCK:
                JOBS[job_id]["status"] = "awaiting_review"
                JOBS[job_id]["review"] = review

            events.put(_event(
                "Blog is ready for human review",
                "review",
                "awaiting_review",
                {
                    "blog_id": job_id,
                    "blog": blog,
                    "question": review.get("question", "Do you approve this blog?"),
                    "instruction": review.get("instruction", "Approve or request changes."),
                },
            ))
            return

        # Defensive check: normal generation should pause at human_review.
        if not state.get("final"):
            raise RuntimeError("Graph ended without producing a blog or a pending review.")

        with JOBS_LOCK:
            JOBS[job_id]["status"] = "completed"
            JOBS[job_id]["state"] = state

        markdown = _latest_markdown(state)
        events.put(_event(
            "Blog generation completed",
            "complete",
            "completed",
            {
                "blog_id": job_id,
                "markdown": markdown,
                "download_url": f"/api/blog/{job_id}/download",
                "package_url": f"/api/blog/{job_id}/package",
            },
        ))

    except Exception as exc:
        logger.exception("Blog generation failed")
        with JOBS_LOCK:
            JOBS[job_id]["status"] = "failed"
            JOBS[job_id]["error"] = str(exc)

        events.put(_event(
            f"Generation failed: {exc}",
            "error",
            "failed",
        ))

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

    with JOBS_LOCK:
        JOBS[job_id] = {
            "status": "running",
            "topic": topic,
            "queue": queue.Queue(),
            "state": None,
            "error": None,
            "review": None,
        }

    threading.Thread(
        target=_run_job,
        args=(job_id, topic),
        daemon=True,
    ).start()

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

    def event_stream():
        while True:
            item = job["queue"].get()
            if item is None:
                break
            yield item

    return Response(
        event_stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@web_app.post("/api/blog/<job_id>/review")
def submit_review(job_id: str):
    payload = request.get_json(silent=True) or {}
    approved = payload.get("approved")
    feedback = str(payload.get("feedback", "")).strip()

    if not isinstance(approved, bool):
        return jsonify({"error": "'approved' must be a boolean."}), 400

    if not approved and not feedback:
        return jsonify({"error": "Enter feedback before requesting changes."}), 400

    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return jsonify({"error": "Blog not found."}), 404
        if job["status"] != "awaiting_review":
            return jsonify({
                "error": f"Blog is not awaiting review (status: {job['status']})."
            }), 409
        job["status"] = "processing_review"

    config = _thread_config(job_id)

    try:
        graph_app.invoke(
            Command(resume={"approved": approved, "feedback": feedback}),
            config=config,
        )

        snapshot = graph_app.get_state(config)
        state = dict(snapshot.values)
        pending = _pending_interrupts(snapshot)
        markdown = _latest_markdown(state)

        with JOBS_LOCK:
            job = JOBS[job_id]
            job["state"] = state
            if pending:
                job["status"] = "awaiting_review"
                job["review"] = pending[0]
            else:
                job["status"] = "completed"
                job["review"] = None

        if pending:
            review = pending[0]
            return jsonify({
                "status": "awaiting_review",
                "blog": review.get("blog") or markdown,
                "question": review.get("question", "Do you approve this blog?"),
                "instruction": review.get("instruction", "Approve or request changes."),
            })

        return jsonify({
            "status": "completed",
            "markdown": markdown,
            "download_url": url_for("download_markdown", job_id=job_id),
            "package_url": url_for("download_package", job_id=job_id),
        })

    except Exception:
        logger.exception("HITL review submission failed")
        # Retain the current pending review if a transient error occurred.
        try:
            snapshot = graph_app.get_state(config)
            state = dict(snapshot.values)
            pending = _pending_interrupts(snapshot)
            with JOBS_LOCK:
                job = JOBS[job_id]
                job["state"] = state
                if pending:
                    job["status"] = "awaiting_review"
                    job["review"] = pending[0]
                else:
                    job["status"] = "failed"
                    job["error"] = "Review processing failed. Check server logs."
        except Exception:
            with JOBS_LOCK:
                JOBS[job_id]["status"] = "failed"
                JOBS[job_id]["error"] = "Review processing failed. Check server logs."

        return jsonify({
            "error": "Unable to process the review. Check server logs."
        }), 500


@web_app.get("/api/blog/<job_id>")
def get_blog(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)

    if not job:
        return jsonify({"error": "Blog not found."}), 404

    if job["status"] == "failed":
        return jsonify({"error": job.get("error", "Blog generation failed.")}), 500

    if job["status"] == "awaiting_review":
        review = job.get("review") or {}
        state = job.get("state") or {}
        return jsonify({
            "id": job_id,
            "topic": job["topic"],
            "status": "awaiting_review",
            "blog": review.get("blog") or _latest_markdown(state),
            "question": review.get("question", "Do you approve this blog?"),
        }), 200

    if job["status"] != "completed":
        return jsonify({"status": job["status"]}), 202

    state = job["state"] or {}
    return jsonify({
        "id": job_id,
        "topic": job["topic"],
        "markdown": _latest_markdown(state),
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
    generated_images = (job.get("state") or {}).get("generated_images", [])
    allowed_images = {
        Path(item["path"]).name
        for item in generated_images
        if item.get("path")
    }

    if safe_name not in allowed_images:
        return jsonify({"error": "Image not found."}), 404

    return send_from_directory(IMAGE_DIR, safe_name)


def _job_blog_path(job_id: str) -> Path | None:
    with JOBS_LOCK:
        job = JOBS.get(job_id)

    if not job or job["status"] != "completed":
        return None

    state = job.get("state") or {}
    markdown = _latest_markdown(state)
    candidates = []

    for directory in (REVISED_BLOG_DIR, BLOG_DIR):
        if directory.is_dir():
            candidates.extend(directory.glob("*.md"))

    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)

    for candidate in candidates:
        try:
            if candidate.read_text(encoding="utf-8") == markdown:
                return candidate
        except OSError:
            continue

    return None


@web_app.get("/api/blog/<job_id>/download")
def download_markdown(job_id: str):
    markdown_path = _job_blog_path(job_id)

    if markdown_path is None:
        return jsonify({"error": "Approved blog file not found."}), 404

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
        return jsonify({"error": "Approved blog file not found."}), 404

    with JOBS_LOCK:
        job = JOBS.get(job_id)

    image_names = {
        Path(item["path"]).name
        for item in (job["state"] or {}).get("generated_images", [])
        if item.get("path")
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


if __name__ == "__main__":
    web_app.run(debug=True)
