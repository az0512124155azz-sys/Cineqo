from __future__ import annotations

import base64
import os
import subprocess
import uuid
from pathlib import Path
from typing import Any

import httpx
from fastapi import File, Form, HTTPException, UploadFile

from .main import (
    APP_NAME,
    DIRECTOR_API_KEY,
    DIRECTOR_BASE_URL,
    DIRECTOR_MODEL,
    SHARED_ROOT,
    _director_chat,
    app,
)

REFERENCE_ROOT = SHARED_ROOT / "reference-analysis"
REFERENCE_ROOT.mkdir(parents=True, exist_ok=True)


def _data_url(path: Path) -> str:
    suffix = path.suffix.lower()
    mime = "image/png" if suffix == ".png" else "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def _extract_frames(video: Path, output: Path) -> list[Path]:
    output.mkdir(parents=True, exist_ok=True)
    pattern = output / "frame-%02d.jpg"
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(video),
        "-vf", "fps=1/5,scale='min(768,iw)':-2",
        "-frames:v", "3", str(pattern),
    ]
    subprocess.run(cmd, check=True, timeout=180)
    return sorted(output.glob("frame-*.jpg"))[:3]


async def _analyze_frames(frames: list[Path], label: str, language: str) -> str:
    if not frames:
        return "No usable visual frames were extracted."
    content: list[dict[str, Any]] = [{
        "type": "text",
        "text": (
            f"Analyze this {label} for Cineqo, a music-video creative director. "
            "Describe visual style, camera language, lighting, color palette, locations, wardrobe, "
            "performance style, editing/motion cues, recurring motifs, realism level, and what should "
            f"or should not influence a new original music video. Reply compactly in {language}."
        ),
    }]
    content.extend({"type": "image_url", "image_url": {"url": _data_url(frame)}} for frame in frames)
    payload = {
        "model": DIRECTOR_MODEL,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.2,
        "max_tokens": 650,
    }
    headers = {"Authorization": f"Bearer {DIRECTOR_API_KEY}"}
    async with httpx.AsyncClient(timeout=300) as client:
        response = await client.post(f"{DIRECTOR_BASE_URL}/chat/completions", json=payload, headers=headers)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


@app.post("/api/references/analyze")
async def analyze_references(
    mine: list[UploadFile] = File(default=[]),
    references: list[UploadFile] = File(default=[]),
    language: str = Form("en"),
) -> dict[str, Any]:
    if len(mine) > 10 or len(references) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 artist clips and 10 reference clips")
    if not mine and not references:
        return {"summary": "No clips supplied.", "items": []}

    run = REFERENCE_ROOT / uuid.uuid4().hex
    run.mkdir(parents=True, exist_ok=True)
    items: list[dict[str, str]] = []

    async def process(upload: UploadFile, kind: str, index: int) -> None:
        suffix = Path(upload.filename or "clip.mp4").suffix or ".mp4"
        source = run / f"{kind}-{index:02d}{suffix}"
        source.write_bytes(await upload.read())
        try:
            if (upload.content_type or "").startswith("image/") or suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
                frames = [source]
            else:
                frames = _extract_frames(source, run / f"frames-{kind}-{index:02d}")
            analysis = await _analyze_frames(frames, "artist's own clip" if kind == "mine" else "reference clip", language)
        except Exception as exc:
            analysis = f"Visual analysis failed for this clip: {exc}"
        items.append({"kind": kind, "filename": upload.filename or source.name, "analysis": analysis})

    for i, upload in enumerate(mine):
        await process(upload, "mine", i)
    for i, upload in enumerate(references):
        await process(upload, "reference", i)

    evidence = "\n\n".join(f"[{x['kind']}] {x['filename']}\n{x['analysis']}" for x in items)
    summary = await _director_chat([
        {"role": "system", "content": "You are Cineqo's visual-style analyst. Never copy a reference work; extract transferable preferences only."},
        {"role": "user", "content": f"Create an Artist Visual DNA profile from these clip analyses. Separate traits observed in the artist's own work from preferences inferred from references. Include visual rules to use, elements to avoid copying, camera, lighting, palette, wardrobe, performance, editing rhythm, locations and motifs. Reply in {language}.\n\n{evidence[:28000]}"},
    ], temperature=0.25, max_tokens=1200)
    return {"summary": summary, "items": items, "director_model": DIRECTOR_MODEL}


@app.get("/api/runtime")
async def runtime() -> dict[str, str]:
    return {"service": APP_NAME, "director": DIRECTOR_MODEL, "multimodal": "true"}
