from __future__ import annotations

import os
import tempfile
from functools import lru_cache

import whisper
from fastapi import FastAPI, File, UploadFile

MODEL_NAME = os.getenv("WHISPER_MODEL", "small")
DEVICE = os.getenv("WHISPER_DEVICE", "cuda")

app = FastAPI(title="Cineqo Whisper Worker", version="0.1.0")


@lru_cache(maxsize=1)
def model():
    return whisper.load_model(MODEL_NAME, device=DEVICE)


@app.get("/health")
def health():
    return {"ok": True, "model": MODEL_NAME, "device": DEVICE}


@app.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    suffix = os.path.splitext(audio.filename or "voice.webm")[1] or ".webm"
    data = await audio.read()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        path = tmp.name
    try:
        result = model().transcribe(path, task="transcribe", fp16=DEVICE.startswith("cuda"))
        segments = [
            {
                "start": float(seg.get("start", 0)),
                "end": float(seg.get("end", 0)),
                "text": str(seg.get("text", "")).strip(),
            }
            for seg in result.get("segments", [])
        ]
        return {
            "text": str(result.get("text", "")).strip(),
            "language": result.get("language"),
            "segments": segments,
            "model": MODEL_NAME,
        }
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
