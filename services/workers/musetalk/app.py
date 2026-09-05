from __future__ import annotations

import os
import subprocess
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

ROOT = Path(os.getenv("MUSETALK_ROOT", "/opt/musetalk"))
OUTPUT_ROOT = Path(os.getenv("MUSETALK_OUTPUT_DIR", "/outputs"))
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg")
UNET = os.getenv("MUSETALK_UNET", "/models/musetalkV15/unet.pth")
UNET_CONFIG = os.getenv("MUSETALK_UNET_CONFIG", "/models/musetalkV15/musetalk.json")
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Cineqo MuseTalk Worker", version="0.1.0")
jobs: dict[str, dict] = {}
lock = threading.Lock()


class JobRequest(BaseModel):
    video_path: str
    audio_path: str


def run_job(job_id: str, req: JobRequest) -> None:
    job_dir = OUTPUT_ROOT / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    config = job_dir / "inference.yaml"
    config.write_text(
        "task_0:\n"
        f'  video_path: "{req.video_path}"\n'
        f'  audio_path: "{req.audio_path}"\n',
        encoding="utf-8",
    )
    cmd = [
        "python3",
        "-m",
        "scripts.inference",
        "--inference_config",
        str(config),
        "--result_dir",
        str(job_dir / "results"),
        "--unet_model_path",
        UNET,
        "--unet_config",
        UNET_CONFIG,
        "--version",
        "v15",
        "--ffmpeg_path",
        FFMPEG_PATH,
        "--use_float16",
    ]
    with lock:
        jobs[job_id].update(status="running", command=cmd)
    try:
        proc = subprocess.run(
            cmd,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=int(os.getenv("MUSETALK_JOB_TIMEOUT", "3600")),
            check=False,
        )
        files = [str(p) for p in job_dir.rglob("*.mp4")]
        with lock:
            jobs[job_id].update(
                status="succeeded" if proc.returncode == 0 else "failed",
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
        "source_exists": ROOT.exists(),
        "unet_exists": Path(UNET).exists(),
        "config_exists": Path(UNET_CONFIG).exists(),
    }


@app.post("/jobs")
def create_job(req: JobRequest):
    if not ROOT.exists():
        raise HTTPException(status_code=503, detail=f"MuseTalk source missing at {ROOT}")
    if not Path(req.video_path).exists() or not Path(req.audio_path).exists():
        raise HTTPException(status_code=400, detail="video_path and audio_path must exist inside the shared worker volume")
    if not Path(UNET).exists() or not Path(UNET_CONFIG).exists():
        raise HTTPException(status_code=503, detail="MuseTalk 1.5 weights are not mounted")
    job_id = uuid.uuid4().hex
    jobs[job_id] = {"id": job_id, "status": "queued"}
    threading.Thread(target=run_job, args=(job_id, req), daemon=True).start()
    return jobs[job_id]


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="job not found")
    return jobs[job_id]
