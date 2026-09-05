from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

ROOT = Path(os.getenv("TRIPOSR_ROOT", "/opt/triposr"))
OUTPUT_ROOT = Path(os.getenv("TRIPOSR_OUTPUT_DIR", "/outputs"))
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Cineqo TripoSR Identity Worker", version="0.1.0")
models: dict[str, dict] = {}


class RefineRequest(BaseModel):
    instruction: str
    model_id: str | None = None


@app.get("/health")
def health():
    return {"ok": True, "source_exists": ROOT.exists(), "engine": "TripoSR", "license": "MIT"}


@app.post("/build")
async def build(images: list[UploadFile] = File(...)):
    if not images:
        raise HTTPException(status_code=400, detail="at least one image is required")
    if not ROOT.exists():
        raise HTTPException(status_code=503, detail=f"TripoSR source missing at {ROOT}")

    model_id = uuid.uuid4().hex
    work = OUTPUT_ROOT / model_id
    inputs = work / "inputs"
    out = work / "model"
    inputs.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)

    paths: list[str] = []
    for index, image in enumerate(images[:10]):
        suffix = Path(image.filename or "image.png").suffix or ".png"
        path = inputs / f"image-{index:02d}{suffix}"
        path.write_bytes(await image.read())
        paths.append(str(path))

    # TripoSR supports multiple image paths. They are treated as a batch; the
    # first result is the initial Cineqo preview while the additional outputs
    # remain available for consistency comparison in later refinement stages.
    cmd = ["python3", "run.py", *paths, "--output-dir", str(out), "--bake-texture"]
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=int(os.getenv("TRIPOSR_JOB_TIMEOUT", "1800")),
        check=False,
    )
    generated = [str(p) for p in out.rglob("*") if p.is_file() and p.suffix.lower() in {".obj", ".glb", ".gltf", ".ply"}]
    status = "succeeded" if proc.returncode == 0 and generated else "failed"
    result = {
        "id": model_id,
        "status": status,
        "engine": "TripoSR",
        "files": generated,
        "preview": generated[0] if generated else None,
        "stdout": proc.stdout[-8000:],
        "stderr": proc.stderr[-8000:],
        "input_count": len(paths),
    }
    models[model_id] = result
    if status != "succeeded":
        raise HTTPException(status_code=500, detail=result)
    return result


@app.post("/refine")
def refine(req: RefineRequest):
    # TripoSR itself is reconstruction, not text-guided mesh editing. Keep the
    # instruction in the model record so Cineqo can route it to the next
    # permissively licensed refinement engine without pretending an edit ran.
    model_id = req.model_id or (next(reversed(models)) if models else None)
    if not model_id or model_id not in models:
        raise HTTPException(status_code=404, detail="no identity model is available")
    models[model_id].setdefault("refinement_requests", []).append(req.instruction)
    return {
        "model_id": model_id,
        "queued": True,
        "message": "Refinement request saved. TripoSR provides the base mesh; text-guided mesh refinement is a separate adapter.",
    }


@app.get("/models/{model_id}")
def get_model(model_id: str):
    if model_id not in models:
        raise HTTPException(status_code=404, detail="model not found")
    return models[model_id]
