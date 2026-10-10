from flask import Flask, Response, jsonify, render_template, request, send_file, send_from_directory, url_for
from pathlib import Path
from io import BytesIO
import json
import queue
import threading
import uuid
import zipfile
from datetime import datetime

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


def _merge_update(state: dict, update: dict) -> None:
    """
    Reconstruct the final parent state from LangGraph state updates.

    The existing State definition uses operator.add for sections, so
    section updates must be appended rather than overwritten.
    """
    for key, value in update.items():
        if key == "sections":
            state["sections"].extend(value or [])
        else:
            state[key] = value


def _run_job(job_id: str, topic: str):
    events = JOBS[job_id]["queue"]
    state = _initial_state(topic)
    first_event = True

    try:
        # Stream the existing graph and its reducer subgraph. LangGraph exposes
        # subgraph node updates when subgraphs=True.
        for namespace, chunk in graph_app.stream(
            _initial_state(topic),
            stream_mode="updates",
            subgraphs=True,
        ):
            if first_event:
                events.put(_event("Starting Blog Writing Agent", "planning"))
                first_event = False

            if not chunk:
                continue

            update = next(iter(chunk.values()))
            node_name = next(iter(chunk.keys()))
            _merge_update(state, update)

            is_subgraph = bool(namespace)

            if node_name == "router":
                if state.get("needs_research"):
                    events.put(_event(
                        "Research required; routing to web research",
                        "research",
                        data={"mode": state.get("mode")}
                    ))
                else:
                    events.put(_event(
                        "Research not required; continuing with planning",
                        "planning",
                        data={"mode": state.get("mode")}
                    ))

            elif node_name == "research":
                events.put(_event(
                    f"Research completed ({len(state.get('evidence') or [])} sources)",
                    "research",
                    data={"source_count": len(state.get("evidence") or [])}
                ))

            elif node_name == "orchestrator":
                plan = state.get("plan")
                task_count = len(getattr(plan, "tasks", []) or []) if plan else 0
                events.put(_event(
                    f"Blog plan created ({task_count} sections)",
                    "planning",
                    data={"sections": task_count}
                ))

            elif node_name == "worker":
                completed = len(state.get("sections") or [])
                events.put(_event(
                    f"Writing in progress ({completed} section(s) completed)",
                    "writing",
                    data={"sections_completed": completed}
                ))

            elif is_subgraph and node_name == "merge_content":
                events.put(_event("Merging written sections", "finalizing"))

            elif is_subgraph and node_name == "decide_images":
                count = len(state.get("image_specs") or [])
                events.put(_event(
                    f"Image plan created ({count} visual(s))",
                    "images",
                    data={"images": count}
                ))

            elif is_subgraph and node_name == "generate_images":
                count = len(state.get("generated_images") or [])
                events.put(_event(
                    f"Image generation completed ({count} image(s))",
                    "images",
                    data={"images": count}
                ))

            elif is_subgraph and node_name == "replace_image_placeholders":
                events.put(_event(
                    "Finalizing blog and replacing image placeholders",
                    "finalizing"
                ))

            # The parent 'reducer' roll-up is intentionally not emitted as a
            # separate event because its child updates already describe it.

        if not state.get("final"):
            raise RuntimeError("LangGraph completed without producing a final blog.")

        with JOBS_LOCK:
            JOBS[job_id]["state"] = state
            JOBS[job_id]["status"] = "completed"

        events.put(_event(
            "Blog generation completed",
            "complete",
            "completed",
            {
                "blog_id": job_id,
                "markdown": state["final"],
                "download_url": url_for("download_markdown", job_id=job_id),
                "package_url": url_for("download_package", job_id=job_id),
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
