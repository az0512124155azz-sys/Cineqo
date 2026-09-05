from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any, Literal

import httpx
from ddgs import DDGS
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

APP_NAME = "Cineqo API"
DIRECTOR_BASE_URL = os.getenv("CINEQO_DIRECTOR_BASE_URL", "http://director:8000/v1").rstrip("/")
DIRECTOR_MODEL = os.getenv("CINEQO_DIRECTOR_MODEL", "Qwen/Qwen3-4B")
DIRECTOR_API_KEY = os.getenv("CINEQO_DIRECTOR_API_KEY", "local-open-model")
WHISPER_URL = os.getenv("CINEQO_WHISPER_URL", "http://whisper:8011").rstrip("/")
WAN_URL = os.getenv("CINEQO_WAN_URL", "http://wan:8012").rstrip("/")
MUSETALK_URL = os.getenv("CINEQO_MUSETALK_URL", "http://musetalk:8013").rstrip("/")
IDENTITY_URL = os.getenv("CINEQO_IDENTITY_URL", "http://identity:8014").rstrip("/")
WEB_RESULTS = int(os.getenv("CINEQO_WEB_RESULTS", "8"))
SHARED_ROOT = Path(os.getenv("CINEQO_SHARED_ROOT", "/shared")).resolve()
UPLOAD_ROOT = SHARED_ROOT / "uploads"
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)

app = FastAPI(title=APP_NAME, version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in os.getenv("CINEQO_CORS_ORIGINS", "*").split(",")],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


class RefineRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=4000)
    model_id: str | None = None


class VideoRequest(BaseModel):
    prompt: str
    image_path: str | None = None
    seconds: int = Field(default=5, ge=1, le=15)
    resolution: str = "1280*704"


class LipSyncRequest(BaseModel):
    video_path: str
    audio_path: str


def _search(query: str, max_results: int = WEB_RESULTS) -> list[dict[str, Any]]:
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        return [
            {
                "title": str(item.get("title", "")),
                "url": str(item.get("href") or item.get("url") or ""),
                "snippet": str(item.get("body") or item.get("snippet") or ""),
            }
            for item in results
        ]
    except Exception:
        return []


def _director_system(mode: str, language: str, artist_name: str | None) -> str:
    artist = artist_name or "the artist"
    return f"""You are Cineqo's Creative Director for {artist}.
Cineqo does not create songs. It turns existing finished music into music-video concepts and production plans.
Operate in {mode} mode. PLAN means collaborate, clarify, research and build treatments/storyboards/shot lists before generation. CREATE means produce an executable cinematic generation prompt and move toward rendering.
Reply in the user's language ({language}) unless asked otherwise.
Never pretend that a model job completed unless a worker result confirms it.
Distinguish public facts from creative inference.
Optimize for cinematic continuity, artist identity consistency, lyric timing, authorized likeness use, lip-sync, camera language, lighting, editing rhythm and exportability.
"""


async def _director_chat(messages: list[dict[str, str]], temperature: float = 0.55, max_tokens: int = 1800) -> str:
    payload = {"model": DIRECTOR_MODEL, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    headers = {"Authorization": f"Bearer {DIRECTOR_API_KEY}"}
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(f"{DIRECTOR_BASE_URL}/chat/completions", json=payload, headers=headers)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Director model unavailable: {exc}") from exc


async def _probe(name: str, url: str) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            response = await client.get(url)
        response.raise_for_status()
        return {"name": name, "ready": True, "details": response.json()}
    except Exception as exc:
        return {"name": name, "ready": False, "error": str(exc)}


def _file_url(path: str) -> str | None:
    try:
        p = Path(path).resolve()
        rel = p.relative_to(SHARED_ROOT)
        return "/api/files/" + str(rel).replace(os.sep, "/")
    except Exception:
        return None


def _decorate_files(data: dict[str, Any]) -> dict[str, Any]:
    files = data.get("files") or []
    data["file_urls"] = [url for url in (_file_url(str(p)) for p in files) if url]
    preview = data.get("preview")
    if preview:
        data["preview_url"] = _file_url(str(preview))
    return data


async def _save_upload(upload: UploadFile, folder: Path) -> str:
    folder.mkdir(parents=True, exist_ok=True)
    suffix = Path(upload.filename or "asset.bin").suffix
    target = folder / f"{uuid.uuid4().hex}{suffix}"
    target.write_bytes(await upload.read())
    return str(target)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "service": APP_NAME, "version": "0.2.0", "director_model": DIRECTOR_MODEL}


@app.get("/api/models/status")
async def models_status() -> dict[str, Any]:
    probes = [
        await _probe("director", f"{DIRECTOR_BASE_URL}/models"),
        await _probe("whisper", f"{WHISPER_URL}/health"),
        await _probe("wan", f"{WAN_URL}/health"),
        await _probe("musetalk", f"{MUSETALK_URL}/health"),
        await _probe("identity", f"{IDENTITY_URL}/health"),
    ]
    return {"ready": all(p["ready"] for p in probes), "models": probes}


@app.post("/api/research")
async def research(req: ResearchRequest) -> dict[str, Any]:
    suffix = " ".join(x for x in [req.country, "artist musician music video interview social profiles"] if x)
    query = f'"{req.artist_name}" {suffix}'.strip()
    sources = _search(query, 12)
    source_text = "\n".join(f"- {x['title']} | {x['url']} | {x['snippet'][:500]}" for x in sources)
    prompt = f"""Build a cautious public Artist Profile for {req.artist_name}.
Country hint: {req.country or 'unknown'}.
Use ONLY the search results below as factual evidence. If evidence is sparse or ambiguous, say so clearly.
Cover identity confidence, musical identity, visual identity, public videos/performances, recurring themes, fashion/presentation, audience signals and creative observations.

SEARCH RESULTS:\n{source_text or '(no results)'}"""
    answer = await _director_chat([
        {"role": "system", "content": _director_system("PLAN", req.language, req.artist_name)},
        {"role": "user", "content": prompt},
    ], temperature=0.25)
    return {"summary": answer, "sources": sources, "query": query}


@app.post("/api/chat")
async def chat(req: ChatRequest) -> dict[str, Any]:
    messages: list[dict[str, str]] = [{"role": "system", "content": _director_system(req.mode, req.language, req.artist_name)}]
    if req.use_web and req.messages:
        last_user = next((m.content for m in reversed(req.messages) if m.role == "user"), "")
        if last_user:
            results = _search(last_user, WEB_RESULTS)
            if results:
                context = "\n".join(f"- {r['title']} | {r['url']} | {r['snippet'][:400]}" for r in results)
                messages.append({"role": "system", "content": f"Current public web research context:\n{context}"})
    messages.extend(m.model_dump() for m in req.messages[-20:])
    answer = await _director_chat(messages)
    return {"answer": answer, "model": DIRECTOR_MODEL, "mode": req.mode}


@app.post("/api/transcribe")
async def transcribe(audio: UploadFile = File(...)) -> dict[str, Any]:
    data = await audio.read()
    files = {"audio": (audio.filename or "voice.webm", data, audio.content_type or "application/octet-stream")}
    try:
        async with httpx.AsyncClient(timeout=600) as client:
            response = await client.post(f"{WHISPER_URL}/transcribe", files=files)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Whisper worker unavailable: {exc}") from exc


@app.post("/api/identity/prepare")
async def identity_prepare(images: list[UploadFile] = File(...)) -> dict[str, Any]:
    if len(images) < 3:
        raise HTTPException(status_code=400, detail="At least 3 images are required")
    multipart = []
    for image in images[:10]:
        multipart.append(("images", (image.filename or "image.jpg", await image.read(), image.content_type or "image/jpeg")))
    try:
        async with httpx.AsyncClient(timeout=1800) as client:
            response = await client.post(f"{IDENTITY_URL}/build", files=multipart)
        response.raise_for_status()
        return _decorate_files(response.json())
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Identity worker unavailable: {exc}") from exc


@app.post("/api/identity/refine")
async def identity_refine(req: RefineRequest) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=1800) as client:
            response = await client.post(f"{IDENTITY_URL}/refine", json=req.model_dump())
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Identity worker unavailable: {exc}") from exc


@app.get("/api/identity/models/{model_id}")
async def identity_model(model_id: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(f"{IDENTITY_URL}/models/{model_id}")
    response.raise_for_status()
    return _decorate_files(response.json())


@app.post("/api/video/generate")
async def video_generate(req: VideoRequest) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{WAN_URL}/jobs", json=req.model_dump())
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Wan worker unavailable: {exc}") from exc


@app.get("/api/video/jobs/{job_id}")
async def video_job(job_id: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(f"{WAN_URL}/jobs/{job_id}")
    response.raise_for_status()
    return _decorate_files(response.json())


@app.post("/api/lipsync")
async def lipsync(req: LipSyncRequest) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{MUSETALK_URL}/jobs", json=req.model_dump())
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"MuseTalk worker unavailable: {exc}") from exc


@app.get("/api/lipsync/jobs/{job_id}")
async def lipsync_job(job_id: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(f"{MUSETALK_URL}/jobs/{job_id}")
    response.raise_for_status()
    return _decorate_files(response.json())


@app.post("/api/create")
async def create(
    prompt: str = Form(...),
    language: str = Form("en"),
    artist_name: str | None = Form(None),
    song: UploadFile | None = File(None),
    reference_image: UploadFile | None = File(None),
) -> dict[str, Any]:
    run_id = uuid.uuid4().hex
    folder = UPLOAD_ROOT / run_id
    song_path: str | None = None
    image_path: str | None = None
    transcript: dict[str, Any] | None = None

    if song:
        song_bytes = await song.read()
        song.filename = song.filename or "song.wav"
        song_path = str(folder / song.filename)
        folder.mkdir(parents=True, exist_ok=True)
        Path(song_path).write_bytes(song_bytes)
        files = {"audio": (song.filename, song_bytes, song.content_type or "application/octet-stream")}
        async with httpx.AsyncClient(timeout=600) as client:
            response = await client.post(f"{WHISPER_URL}/transcribe", files=files)
        response.raise_for_status()
        transcript = response.json()

    if reference_image:
        image_path = await _save_upload(reference_image, folder)

    lyric_context = ""
    if transcript and transcript.get("text"):
        lyric_context = f"\nSong transcription for timing/context:\n{transcript['text'][:12000]}"
    generation_prompt = await _director_chat([
        {"role": "system", "content": _director_system("CREATE", language, artist_name)},
        {"role": "user", "content": f"Turn this request into ONE detailed executable Wan 2.2 cinematic shot prompt. Include subject, setting, action, camera, lens feel, lighting, color, motion and continuity. Do not include commentary.\nUser request: {prompt}{lyric_context}"},
    ], temperature=0.35, max_tokens=900)

    payload = {"prompt": generation_prompt, "image_path": image_path, "seconds": 5, "resolution": "1280*704"}
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(f"{WAN_URL}/jobs", json=payload)
    response.raise_for_status()
    wan_job = response.json()
    return {
        "run_id": run_id,
        "director_model": DIRECTOR_MODEL,
        "generation_prompt": generation_prompt,
        "transcription": transcript,
        "song_path": song_path,
        "reference_image_path": image_path,
        "video_job": wan_job,
        "next": "poll /api/video/jobs/{id}; if a song was supplied, submit the generated video path and song_path to /api/lipsync",
    }


@app.get("/api/files/{relative_path:path}")
async def files(relative_path: str):
    target = (SHARED_ROOT / relative_path).resolve()
    try:
        target.relative_to(SHARED_ROOT)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid path") from exc
    if not target.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(target)
