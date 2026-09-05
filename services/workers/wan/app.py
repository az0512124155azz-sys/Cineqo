from __future__ import annotations

import os
import subprocess
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

WAN_ROOT = Path(os.getenv("WAN_ROOT", "/opt/wan"))
WAN_CKPT_DIR = os.getenv("WAN_CKPT_DIR", "/models/Wan2.2-TI2V-5B")
WAN_TASK = os.getenv("WAN_TASK", "ti2v-5B")
WAN_OUTPUT_DIR = Path(os.getenv("WAN_OUTPUT_DIR", "/shared/wan"))
WAN_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Cineqo Wan Worker", version="0.2.0")
jobs: dict[str, dict] = {}
lock = threading.Lock()


class JobRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)
    image_path: str | None = None
    seconds: int = Field(default=5, ge=1, le=15)
    resolution: str = "1280*704"


def run_job(job_id: str, req: JobRequest) -> None:
    job_dir = WAN_OUTPUT_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    output_file = job_dir / "video.mp4"
    cmd = [
        "python3", "generate.py",
        "--task", WAN_TASK,
        "--size", req.resolution,
        "--ckpt_dir", WAN_CKPT_DIR,
        "--offload_model", "True",
        "--convert_model_dtype",
        "--t5_cpu",
        "--save_file", str(output_file),
        "--prompt", req.prompt,
    ]
    if req.image_path:
        image = Path(req.image_path)
        if not image.exists():
            with lock:
                jobs[job_id].update(status="failed", error=f"image_path not found: {image}")
            return
        cmd.extend(["--image", str(image)])

    with lock:
        jobs[job_id].update(status="running", command=cmd, output=str(output_file))
    try:
        proc = subprocess.run(
            cmd,
            cwd=WAN_ROOT,
            capture_output=True,
            text=True,
            timeout=int(os.getenv("WAN_JOB_TIMEOUT", "7200")),
            check=False,
        )
        files = [str(p) for p in job_dir.rglob("*.mp4")]
        with lock:
            jobs[job_id].update(
                status="succeeded" if proc.returncode == 0 and files else "failed",
                returncode=proc.returncode,
                stdout=proc.stdout[-12000:],
                stderr=proc.stderr[-12000:],
                files=files,
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
        "output_dir": str(WAN_OUTPUT_DIR),
        "image_to_video": WAN_TASK == "ti2v-5B",
    }


@app.post("/jobs")
def create_job(req: JobRequest):
    if not WAN_ROOT.exists():
        raise HTTPException(status_code=503, detail=f"Wan source missing at {WAN_ROOT}")
    if not Path(WAN_CKPT_DIR).exists():
        raise HTTPException(status_code=503, detail=f"Wan checkpoint missing at {WAN_CKPT_DIR}")
    job_id = uuid.uuid4().hex
    jobs[job_id] = {"id": job_id, "status": "queued", "prompt": req.prompt, "image_path": req.image_path}
    threading.Thread(target=run_job, args=(job_id, req), daemon=True).start()
    return jobs[job_id]


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="job not found")
    return jobs[job_id]
