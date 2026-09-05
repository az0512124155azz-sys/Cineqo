from __future__ import annotations

import asyncio
import os
import threading
import uuid
from pathlib import Path
from typing import Any, Literal

from ddgs import DDGS
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from gradio_client import Client, handle_file
from pydantic import BaseModel, Field

APP_NAME = "Cineqo Free Cloud API"
CORE_SPACE = os.getenv("CINEQO_HF_CORE_SPACE", "").strip()
VIDEO_SPACE = os.getenv("CINEQO_HF_VIDEO_SPACE", "").strip()
HF_TOKEN = os.getenv("CINEQO_HF_TOKEN", "").strip() or None
WEB_RESULTS = int(os.getenv("CINEQO_WEB_RESULTS", "8"))
TMP_ROOT = Path(os.getenv("CINEQO_TMP_ROOT", "/tmp/cineqo")).resolve()
TMP_ROOT.mkdir(parents=True, exist_ok=True)

app = FastAPI(title=APP_NAME, version="0.1.0")
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


def core_client() -> Client:
    if not CORE_SPACE:
        raise HTTPException(status_code=503, detail="CINEQO_HF_CORE_SPACE is not configured")
    return Client(CORE_SPACE, token=HF_TOKEN)


def video_client() -> Client:
    if not VIDEO_SPACE:
        raise HTTPException(status_code=503, detail="CINEQO_HF_VIDEO_SPACE is not configured")
    return Client(VIDEO_SPACE, token=HF_TOKEN)


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

    def call() -> str:
        result = core_client().predict(prompt=prompt, api_name="/director")
        return str(result)

    try:
        return await asyncio.to_thread(call)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Director Space unavailable: {exc}") from exc


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": APP_NAME,
        "core_space_configured": bool(CORE_SPACE),
        "video_space_configured": bool(VIDEO_SPACE),
    }


@app.get("/api/models/status")
async def models_status() -> dict[str, Any]:
    return {
        "ready": bool(CORE_SPACE and VIDEO_SPACE),
        "models": [
            {"name": "director+whisper", "ready": bool(CORE_SPACE), "space": CORE_SPACE or None},
            {"name": "wan2.2", "ready": bool(VIDEO_SPACE), "space": VIDEO_SPACE or None},
        ],
        "mode": "free-cloud",
    }


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
    return {"answer": answer, "mode": req.mode, "provider": "hf-zerogpu"}


@app.post("/api/transcribe")
async def transcribe(audio: UploadFile = File(...)) -> dict[str, Any]:
    target = TMP_ROOT / f"voice-{uuid.uuid4().hex}{Path(audio.filename or 'voice.webm').suffix or '.webm'}"
    target.write_bytes(await audio.read())

    def call() -> Any:
        return core_client().predict(audio=handle_file(str(target)), api_name="/transcribe")

    try:
        result = await asyncio.to_thread(call)
        if isinstance(result, dict):
            return result
        return {"text": str(result)}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Whisper Space unavailable: {exc}") from exc


def run_video_job(job_id: str, prompt: str, image_path: str | None) -> None:
    with job_lock:
        video_jobs[job_id]["status"] = "running"
    try:
        kwargs: dict[str, Any] = {"prompt": prompt}
        if image_path:
            kwargs["image"] = handle_file(image_path)
        else:
            kwargs["image"] = None
        result = video_client().predict(**kwargs, api_name="/generate")
        output_path = str(result)
        with job_lock:
            video_jobs[job_id].update(status="succeeded", files=[output_path], file_urls=[f"/api/free-video/{job_id}"])
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
    if song:
        target = TMP_ROOT / f"song-{uuid.uuid4().hex}{Path(song.filename or 'song.wav').suffix or '.wav'}"
        song_bytes = await song.read()
        target.write_bytes(song_bytes)

        def transcribe_song() -> Any:
            return core_client().predict(audio=handle_file(str(target)), api_name="/transcribe")

        result = await asyncio.to_thread(transcribe_song)
        transcript = result if isinstance(result, dict) else {"text": str(result)}

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
    threading.Thread(target=run_video_job, args=(job_id, generation_prompt, image_path), daemon=True).start()
    return {
        "run_id": uuid.uuid4().hex,
        "generation_prompt": generation_prompt,
        "transcription": transcript,
        "video_job": video_jobs[job_id],
        "free_mode": True,
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
    return {
        "ready": False,
        "free_mode": True,
        "message": "Digital Identity generation is not enabled in the free cloud profile yet. Model-chat editing has been intentionally removed.",
        "image_count": len(images),
    }


@app.post("/api/identity/refine")
async def identity_refine() -> dict[str, Any]:
    return {"queued": False, "message": "3D model editing is disabled by product decision."}
