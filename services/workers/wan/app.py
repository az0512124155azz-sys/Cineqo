from __future__ import annotations

import os
import subprocess
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

WAN_ROOT = Path(os.getenv("WAN_ROOT", "/opt/wan"))
WAN_CKPT_DIR = os.getenv("WAN_CKPT_DIR", "/models/Wan2.2-T2V-A14B")
WAN_TASK = os.getenv("WAN_TASK", "t2v-A14B")
WAN_OUTPUT_DIR = Path(os.getenv("WAN_OUTPUT_DIR", "/outputs"))
WAN_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Cineqo Wan Worker", version="0.1.0")
jobs: dict[str, dict] = {}
lock = threading.Lock()


class JobRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)
    image_url: str | None = None
    seconds: int = Field(default=5, ge=1, le=15)
    resolution: str = "1280*720"


def run_job(job_id: str, req: JobRequest) -> None:
    job_dir = WAN_OUTPUT_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "python3",
        "generate.py",
        "--task",
        WAN_TASK,
        "--size",
        req.resolution,
        "--ckpt_dir",
        WAN_CKPT_DIR,
        "--offload_model",
        "True",
        "--convert_model_dtype",
        "--prompt",
        req.prompt,
    ]
    if req.image_url:
        # Image-to-video is deliberately not guessed here. Use a WAN_TASK/image
        # configuration whose upstream CLI has been explicitly verified before
        # enabling it in production.
        with lock:
            jobs[job_id] = {
                "id": job_id,
                "status": "failed",
                "error": "image_url requires the verified Wan image-to-video adapter",
            }
        return
    with lock:
        jobs[job_id]["status"] = "running"
        jobs[job_id]["command"] = cmd
    try:
        proc = subprocess.run(
            cmd,
            cwd=WAN_ROOT,
            capture_output=True,
            text=True,
            timeout=int(os.getenv("WAN_JOB_TIMEOUT", "7200")),
            check=False,
        )
        files = [str(p) for p in WAN_ROOT.rglob("*.mp4") if p.stat().st_mtime >= job_dir.stat().st_mtime]
        with lock:
            jobs[job_id].update(
                status="succeeded" if proc.returncode == 0 else "failed",
                returncode=proc.returncode,
                stdout=proc.stdout[-12000:],
                stderr=proc.stderr[-12000:],
                files=files[-20:],
            )
    except Exception as exc:
        with lock:
            jobs[job_id].update(status="failed", error=str(exc))


@app.get("/health")
def health():
    return {
        "ok": True,
        "task": WAN_TASK,
        "checkpoint": WAN_CKPT_DIR,
        "checkpoint_exists": Path(WAN_CKPT_DIR).exists(),
    }


@app.post("/jobs")
def create_job(req: JobRequest):
    if not WAN_ROOT.exists():
        raise HTTPException(status_code=503, detail=f"Wan source missing at {WAN_ROOT}")
    if not Path(WAN_CKPT_DIR).exists():
        raise HTTPException(status_code=503, detail=f"Wan checkpoint missing at {WAN_CKPT_DIR}")
    job_id = uuid.uuid4().hex
    jobs[job_id] = {"id": job_id, "status": "queued", "prompt": req.prompt}
    threading.Thread(target=run_job, args=(job_id, req), daemon=True).start()
    return jobs[job_id]


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="job not found")
    return jobs[job_id]
