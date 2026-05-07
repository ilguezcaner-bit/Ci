import os
import uuid
import threading
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from editor import get_clip_info, process_edit_plan
from ai_parser import parse_instructions

UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("outputs")
CHUNKS_DIR = Path("uploads/.chunks")
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
CHUNKS_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Video Editor")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

clips: dict = {}
jobs: dict = {}
jobs_lock = threading.Lock()

# upload_id → {name, ext, total_chunks, received: set}
pending_uploads: dict = {}
pending_lock = threading.Lock()


@app.post("/upload/chunk")
async def upload_chunk(
    file: UploadFile = File(...),
    upload_id: str = Form(...),
    chunk_index: int = Form(...),
    total_chunks: int = Form(...),
    filename: str = Form(...),
):
    chunk_path = CHUNKS_DIR / f"{upload_id}_{chunk_index}"
    with open(chunk_path, "wb") as f:
        while data := await file.read(1024 * 1024):
            f.write(data)

    with pending_lock:
        if upload_id not in pending_uploads:
            ext = Path(filename).suffix or ".mp4"
            pending_uploads[upload_id] = {
                "name": filename,
                "ext": ext,
                "total_chunks": total_chunks,
                "received": set(),
            }
        pending_uploads[upload_id]["received"].add(chunk_index)
        all_received = len(pending_uploads[upload_id]["received"]) == total_chunks

    if not all_received:
        return {"status": "chunk_received", "chunk_index": chunk_index}

    # All chunks received — assemble the file
    with pending_lock:
        info = pending_uploads.pop(upload_id)

    clip_id = str(uuid.uuid4())
    dest = UPLOAD_DIR / f"{clip_id}{info['ext']}"
    with open(dest, "wb") as out:
        for i in range(info["total_chunks"]):
            chunk_path = CHUNKS_DIR / f"{upload_id}_{i}"
            with open(chunk_path, "rb") as c:
                while data := c.read(1024 * 1024):
                    out.write(data)
            chunk_path.unlink()

    try:
        duration = get_clip_info(str(dest))["duration"]
    except Exception:
        duration = 0.0

    clips[clip_id] = {"name": info["name"], "path": str(dest), "duration": duration}
    return {"status": "complete", "clip_id": clip_id, "name": info["name"], "duration": duration}


class EditRequest(BaseModel):
    clip_ids: list
    instructions: str


def _run_job(job_id: str, plan: dict, clip_map: dict, output_path: str):
    try:
        process_edit_plan(plan, clip_map, output_path)
        with jobs_lock:
            jobs[job_id]["status"] = "done"
            jobs[job_id]["output_path"] = output_path
    except Exception as e:
        with jobs_lock:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = str(e)


@app.post("/edit")
async def edit_video(req: EditRequest, background_tasks: BackgroundTasks):
    missing = [cid for cid in req.clip_ids if cid not in clips]
    if missing:
        raise HTTPException(400, f"Unknown clip IDs: {missing}")

    clip_list = [
        {"name": clips[cid]["name"], "duration": clips[cid]["duration"]}
        for cid in req.clip_ids
    ]

    try:
        plan = parse_instructions(req.instructions, clip_list)
    except Exception as e:
        raise HTTPException(500, f"Failed to parse instructions: {e}")

    clip_map = {clips[cid]["name"]: clips[cid]["path"] for cid in req.clip_ids}
    job_id = str(uuid.uuid4())
    output_path = str(OUTPUT_DIR / f"{job_id}.mp4")

    with jobs_lock:
        jobs[job_id] = {"status": "processing", "plan": plan, "output_path": None, "error": None}

    background_tasks.add_task(_run_job, job_id, plan, clip_map, output_path)
    return {"job_id": job_id, "plan": plan}


@app.get("/status/{job_id}")
def job_status(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return {
        "job_id": job_id,
        "status": job["status"],
        "plan": job.get("plan"),
        "error": job.get("error"),
    }


@app.get("/download/{job_id}")
def download(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] != "done":
        raise HTTPException(400, f"Job status: {job['status']}")
    return FileResponse(job["output_path"], media_type="video/mp4", filename="output.mp4")


app.mount("/", StaticFiles(directory="static", html=True), name="static")
