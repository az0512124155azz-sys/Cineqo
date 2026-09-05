from __future__ import annotations

import asyncio
import os
import subprocess
import threading
import uuid
from pathlib import Path
from typing import Any, Literal

import httpx
from ddgs import DDGS
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

APP_NAME = "Cineqo Modal Bridge API"
MODAL_URL = os.getenv("CINEQO_MODAL_URL", "").rstrip("/")
MODAL_API_KEY = os.getenv("CINEQO_MODAL_API_KEY", "")
WEB_RESULTS = int(os.getenv("CINEQO_WEB_RESULTS", "8"))
TMP_ROOT = Path(os.getenv("CINEQO_TMP_ROOT", "/tmp/cineqo")).resolve()
TMP_ROOT.mkdir(parents=True, exist_ok=True)

app = FastAPI(title=APP_NAME, version="0.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in os.getenv("CINEQO_CORS_ORIGINS", "*").split(",")],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

video_jobs: dict[str, dict[str, Any]] = {}
job_lock = threading.Lock()


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: list[Message]
    mode: Literal["PLAN", "CREATE"] = "PLAN"
    use_web: bool = True
    language: str = "en"
    artist_name: str | None = None


class ResearchRequest(BaseModel):
    artist_name: str = Field(min_length=1, max_length=160)
    country: str | None = None
    language: str = "en"


def modal_headers() -> dict[str, str]:
    if not MODAL_URL or not MODAL_API_KEY:
        raise HTTPException(status_code=503, detail="Modal backend is not configured")
    return {"Authorization": f"Bearer {MODAL_API_KEY}"}


def search_web(query: str, max_results: int = WEB_RESULTS) -> list[dict[str, str]]:
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        return [
            {
                "title": str(x.get("title", "")),
                "url": str(x.get("href") or x.get("url") or ""),
                "snippet": str(x.get("body") or x.get("snippet") or ""),
            }
            for x in results
        ]
    except Exception:
        return []


def system_prompt(mode: str, language: str, artist_name: str | None) -> str:
    artist = artist_name or "the artist"
    return f"""You are Cineqo's Creative Director for {artist}.
Cineqo never creates songs. It turns already-finished music into cinematic music-video ideas and executable shots.
Mode: {mode}. PLAN = collaborate, research, treatment, storyboard and shot list. CREATE = produce a concise executable Wan 2.2 shot prompt.
Reply in the user's language ({language}) unless explicitly asked otherwise.
Never claim that a render completed unless a real worker result confirms it.
Prioritize cinematic continuity, artist identity, camera language, lighting, edit rhythm and authorized likeness use."""


async def director(messages: list[dict[str, str]], mode: str, language: str, artist_name: str | None) -> str:
    transcript = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages[-20:])
    prompt = system_prompt(mode, language, artist_name) + "\n\nCONVERSATION:\n" + transcript
    try:
        async with httpx.AsyncClient(timeout=900) as client:
            response = await client.post(
                f"{MODAL_URL}/director",
                data={"prompt": prompt},
                headers=modal_headers(),
            )
        response.raise_for_status()
        return str(response.json()["text"])
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Modal Director unavailable: {exc}") from exc


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": APP_NAME,
        "version": "0.3.0",
        "modal_configured": bool(MODAL_URL and MODAL_API_KEY),
    }


@app.get("/api/models/status")
async def models_status() -> dict[str, Any]:
    if not MODAL_URL or not MODAL_API_KEY:
        return {"ready": False, "mode": "modal", "error": "Modal backend is not configured"}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{MODAL_URL}/health")
        response.raise_for_status()
        details = response.json()
        return {"ready": True, "mode": "modal", "models": details.get("models", []), "details": details}
    except Exception as exc:
        return {"ready": False, "mode": "modal", "error": str(exc)}


@app.post("/api/research")
async def research(req: ResearchRequest) -> dict[str, Any]:
    query = f'"{req.artist_name}" {req.country or ""} artist musician music video interview social profiles'.strip()
    sources = search_web(query, 12)
    evidence = "\n".join(f"- {s['title']} | {s['url']} | {s['snippet'][:500]}" for s in sources)
    messages = [{
        "role": "user",
        "content": f"Build a cautious public Artist Profile for {req.artist_name}. Use ONLY this evidence as factual material; clearly mark uncertainty. Cover musical identity, visual identity, public clips/performances, recurring themes, fashion/presentation and useful creative observations.\n\n{evidence or '(no results)'}",
    }]
    summary = await director(messages, "PLAN", req.language, req.artist_name)
    return {"summary": summary, "sources": sources, "query": query}


@app.post("/api/chat")
async def chat(req: ChatRequest) -> dict[str, Any]:
    messages = [m.model_dump() for m in req.messages]
    if req.use_web and messages:
        last = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        if last:
            results = search_web(last)
            if results:
                context = "\n".join(f"- {r['title']} | {r['url']} | {r['snippet'][:350]}" for r in results)
                messages.append({"role": "system", "content": "Current public web context:\n" + context})
    answer = await director(messages, req.mode, req.language, req.artist_name)
    return {"answer": answer, "mode": req.mode, "provider": "modal"}


@app.post("/api/transcribe")
async def transcribe(audio: UploadFile = File(...)) -> dict[str, Any]:
    data = await audio.read()
    files = {"audio": (audio.filename or "voice.webm", data, audio.content_type or "application/octet-stream")}
    try:
        async with httpx.AsyncClient(timeout=900) as client:
            response = await client.post(f"{MODAL_URL}/transcribe", files=files, headers=modal_headers())
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Modal Whisper unavailable: {exc}") from exc


def mux_song(video_path: str, song_path: str, job_id: str) -> str:
    out = TMP_ROOT / f"cineqo-{job_id}-with-song.mp4"
    cmd = [
        "ffmpeg", "-y", "-i", video_path, "-i", song_path,
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k", "-shortest", str(out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180, check=False)
    if proc.returncode != 0 or not out.is_file():
        raise RuntimeError("FFmpeg audio mux failed: " + proc.stderr[-2000:])
    return str(out)


def run_video_job(job_id: str, prompt: str, image_path: str | None, song_path: str | None) -> None:
    with job_lock:
        video_jobs[job_id]["status"] = "running"
    try:
        data = {"prompt": prompt}
        files = None
        fh = None
        if image_path:
            fh = open(image_path, "rb")
            files = {"image": (Path(image_path).name, fh, "application/octet-stream")}
        try:
            with httpx.Client(timeout=3600) as client:
                response = client.post(f"{MODAL_URL}/generate", data=data, files=files, headers=modal_headers())
            response.raise_for_status()
        finally:
            if fh:
                fh.close()
        output_path = TMP_ROOT / f"cineqo-{job_id}.mp4"
        output_path.write_bytes(response.content)
        final_path = str(output_path)
        if song_path:
            final_path = mux_song(final_path, song_path, job_id)
        with job_lock:
            video_jobs[job_id].update(
                status="succeeded",
                files=[final_path],
                file_urls=[f"/api/free-video/{job_id}"],
                original_song_embedded=bool(song_path),
            )
    except Exception as exc:
        with job_lock:
            video_jobs[job_id].update(status="failed", error=str(exc))


@app.post("/api/create")
async def create(
    prompt: str = Form(...),
    language: str = Form("en"),
    artist_name: str | None = Form(None),
    song: UploadFile | None = File(None),
    reference_image: UploadFile | None = File(None),
) -> dict[str, Any]:
    transcript: dict[str, Any] | None = None
    song_path: str | None = None
    if song:
        song_path = str(TMP_ROOT / f"song-{uuid.uuid4().hex}{Path(song.filename or 'song.wav').suffix or '.wav'}")
        song_bytes = await song.read()
        Path(song_path).write_bytes(song_bytes)
        files = {"audio": (song.filename or "song.wav", song_bytes, song.content_type or "application/octet-stream")}
        async with httpx.AsyncClient(timeout=900) as client:
            response = await client.post(f"{MODAL_URL}/transcribe", files=files, headers=modal_headers())
        response.raise_for_status()
        transcript = response.json()

    image_path: str | None = None
    if reference_image:
        image_path = str(TMP_ROOT / f"image-{uuid.uuid4().hex}{Path(reference_image.filename or 'image.jpg').suffix or '.jpg'}")
        Path(image_path).write_bytes(await reference_image.read())

    lyric_context = ""
    if transcript and transcript.get("text"):
        lyric_context = "\nSong transcription/context:\n" + str(transcript["text"])[:10000]
    generation_prompt = await director(
        [{"role": "user", "content": f"Create ONE executable Wan 2.2 cinematic shot prompt from this request. Include subject, setting, action, camera, lens feel, lighting, color and movement. No commentary.\nRequest: {prompt}{lyric_context}"}],
        "CREATE",
        language,
        artist_name,
    )

    job_id = uuid.uuid4().hex
    video_jobs[job_id] = {"id": job_id, "status": "queued", "prompt": generation_prompt}
    threading.Thread(target=run_video_job, args=(job_id, generation_prompt, image_path, song_path), daemon=True).start()
    return {
        "run_id": uuid.uuid4().hex,
        "generation_prompt": generation_prompt,
        "transcription": transcript,
        "video_job": video_jobs[job_id],
        "free_mode": True,
        "song_will_be_embedded": bool(song_path),
    }


@app.get("/api/video/jobs/{job_id}")
async def video_job(job_id: str) -> dict[str, Any]:
    if job_id not in video_jobs:
        raise HTTPException(status_code=404, detail="job not found")
    return video_jobs[job_id]


@app.get("/api/free-video/{job_id}")
async def free_video(job_id: str):
    job = video_jobs.get(job_id)
    if not job or job.get("status") != "succeeded" or not job.get("files"):
        raise HTTPException(status_code=404, detail="video not ready")
    path = Path(str(job["files"][0]))
    if not path.is_file():
        raise HTTPException(status_code=404, detail="temporary video expired")
    return FileResponse(path, media_type="video/mp4", filename=f"cineqo-{job_id}.mp4")


@app.post("/api/identity/prepare")
async def identity_prepare(images: list[UploadFile] = File(...)) -> dict[str, Any]:
    return {"ready": False, "free_mode": True, "message": "Digital Identity is deferred in the free profile.", "image_count": len(images)}


@app.post("/api/identity/refine")
async def identity_refine() -> dict[str, Any]:
    return {"queued": False, "message": "3D model editing is disabled by product decision."}
