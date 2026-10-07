from flask import Flask, Response, jsonify, render_template, request, send_file, send_from_directory, url_for
from pathlib import Path
from io import BytesIO
from datetime import datetime
import json
import queue
import threading
import uuid
import zipfile

from app.graph.workflow import app as graph_app
from logger import get_logger

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


def _emit_state_events(previous: dict | None, current: dict, events: queue.Queue):
    """
    Convert real LangGraph state changes into user-facing SSE milestones.
    No workflow progress is invented; each milestone is caused by a state change.
    """
    previous = previous or {}

    if not previous:
        events.put(_event("Starting Blog Writing Agent", "planning"))

    if current.get("mode") and current.get("mode") != previous.get("mode"):
        if current.get("needs_research"):
            events.put(_event(
                "Research required; routing to web research",
                "research",
                data={"mode": current.get("mode")}
            ))
        else:
            events.put(_event(
                "Research not required; continuing with planning",
                "planning",
                data={"mode": current.get("mode")}
            ))

    old_evidence = previous.get("evidence") or []
    new_evidence = current.get("evidence") or []
    if len(new_evidence) > len(old_evidence):
        events.put(_event(
            f"Research completed ({len(new_evidence)} sources)",
            "research",
            data={"source_count": len(new_evidence)}
        ))

    if current.get("plan") is not None and previous.get("plan") is None:
        plan = current["plan"]
        tasks = getattr(plan, "tasks", []) or []
        events.put(_event(
            f"Blog plan created ({len(tasks)} sections)",
            "planning",
            data={"sections": len(tasks)}
        ))

    old_sections = previous.get("sections") or []
    new_sections = current.get("sections") or []
    if len(new_sections) > len(old_sections):
        events.put(_event(
            f"Writing in progress ({len(new_sections)} section update(s) completed)",
            "writing",
            data={"sections_completed": len(new_sections)}
        ))

    if current.get("merged_md") and current.get("merged_md") != previous.get("merged_md"):
        events.put(_event("Written sections merged", "finalizing"))

    old_specs = previous.get("image_specs") or []
    new_specs = current.get("image_specs") or []
    if len(new_specs) != len(old_specs):
        events.put(_event(
            f"Image plan created ({len(new_specs)} visual(s))",
            "images",
            data={"images": len(new_specs)}
        ))

    old_images = previous.get("generated_images") or []
    new_images = current.get("generated_images") or []
    if len(new_images) > len(old_images):
        events.put(_event(
            f"Image generation completed ({len(new_images)} image(s))",
            "images",
            data={"images": len(new_images)}
        ))

    if current.get("final") and current.get("final") != previous.get("final"):
        events.put(_event("Final blog assembled and saved", "finalizing"))


def _run_job(job_id: str, topic: str):
    events = JOBS[job_id]["queue"]

    try:
        final_state = None
        previous_state = None

        # One real LangGraph execution. Cumulative state updates let us both
        # stream milestones and retain the final state without a second invoke.
        for current_state in graph_app.stream(
            _initial_state(topic),
            stream_mode="values",
        ):
            final_state = current_state
            _emit_state_events(previous_state, current_state, events)
            previous_state = current_state

        if final_state is None or not final_state.get("final"):
            raise RuntimeError("LangGraph completed without producing a final blog.")

        with JOBS_LOCK:
            JOBS[job_id]["state"] = final_state
            JOBS[job_id]["status"] = "completed"

        events.put(_event(
            "Blog generation completed",
            "complete",
            "completed",
            {"blog_id": job_id},
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
    job_queue = queue.Queue()

    with JOBS_LOCK:
        JOBS[job_id] = {
            "status": "running",
            "topic": topic,
            "queue": job_queue,
            "state": None,
            "error": None,
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

    markdown = job["state"].get("final", "")
    markdown_files = sorted(
        BLOG_DIR.glob("*.md"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    for candidate in markdown_files:
        try:
            if candidate.read_text(encoding="utf-8") == markdown:
                return candidate
        except OSError:
            continue

    return markdown_files[0] if markdown_files else None


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

    image_names = {
        Path(item["path"]).name
        for item in job["state"].get("generated_images", [])
        if item.get("path")
    }

    buffer = BytesIO()

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(
            markdown_path,
            arcname=f"BLOG/{markdown_path.name}",
        )

        for image_name in image_names:
            image_path = IMAGE_DIR / image_name
            if image_path.is_file():
                archive.write(
                    image_path,
                    arcname=f"BLOG/images/{image_name}",
                )

    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"blog_{job_id}.zip",
        mimetype="application/zip",
    )


if __name__ == "__main__":
    web_app.run(debug=True)
