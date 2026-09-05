from __future__ import annotations

import os
import subprocess
import uuid
from pathlib import Path

import trimesh
from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

ROOT = Path(os.getenv("TRIPOSR_ROOT", "/opt/triposr"))
OUTPUT_ROOT = Path(os.getenv("TRIPOSR_OUTPUT_DIR", "/outputs"))
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Cineqo TripoSR Identity Worker", version="0.2.0")
models: dict[str, dict] = {}


class RefineRequest(BaseModel):
    instruction: str
    model_id: str | None = None


@app.get("/health")
def health():
    return {"ok": True, "source_exists": ROOT.exists(), "engine": "TripoSR", "license": "MIT", "glb_preview": True}


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

    # TripoSR processes the supplied views as a batch. Cineqo keeps every result
    # and exposes the first valid reconstruction as the base identity preview.
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

    preview: str | None = None
    if generated:
        existing_glb = next((p for p in generated if Path(p).suffix.lower() == ".glb"), None)
        if existing_glb:
            preview = existing_glb
        else:
            try:
                scene = trimesh.load(generated[0], force="scene")
                glb_path = work / "preview.glb"
                glb_path.write_bytes(scene.export(file_type="glb"))
                preview = str(glb_path)
                generated.insert(0, preview)
            except Exception:
                preview = generated[0]

    status = "succeeded" if proc.returncode == 0 and generated else "failed"
    result = {
        "id": model_id,
        "status": status,
        "engine": "TripoSR",
        "files": generated,
        "preview": preview,
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
    # TripoSR itself is reconstruction, not text-guided mesh editing. Preserve
    # refinement requests explicitly instead of pretending a mesh edit occurred.
    model_id = req.model_id or (next(reversed(models)) if models else None)
    if not model_id or model_id not in models:
        raise HTTPException(status_code=404, detail="no identity model is available")
    models[model_id].setdefault("refinement_requests", []).append(req.instruction)
    return {
        "model_id": model_id,
        "queued": True,
        "message": "Refinement request saved. TripoSR provides the base reconstruction; arbitrary text-guided geometry editing requires a separate permissive refinement engine.",
    }


@app.get("/models/{model_id}")
def get_model(model_id: str):
    if model_id not in models:
        raise HTTPException(status_code=404, detail="model not found")
    return models[model_id]
