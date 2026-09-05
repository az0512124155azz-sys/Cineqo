from __future__ import annotations

import os
from typing import Any, Literal

import httpx
from ddgs import DDGS
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

APP_NAME = "Cineqo API"
DIRECTOR_BASE_URL = os.getenv("CINEQO_DIRECTOR_BASE_URL", "http://director:8000/v1").rstrip("/")
DIRECTOR_MODEL = os.getenv("CINEQO_DIRECTOR_MODEL", "Qwen/Qwen3-4B")
DIRECTOR_API_KEY = os.getenv("CINEQO_DIRECTOR_API_KEY", "local-open-model")
WHISPER_URL = os.getenv("CINEQO_WHISPER_URL", "http://whisper:8011").rstrip("/")
WAN_URL = os.getenv("CINEQO_WAN_URL", "http://wan:8012").rstrip("/")
MUSETALK_URL = os.getenv("CINEQO_MUSETALK_URL", "http://musetalk:8013").rstrip("/")
IDENTITY_URL = os.getenv("CINEQO_IDENTITY_URL", "").rstrip("/")
WEB_RESULTS = int(os.getenv("CINEQO_WEB_RESULTS", "8"))

app = FastAPI(title=APP_NAME, version="0.1.0")
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


class VideoRequest(BaseModel):
    prompt: str
    image_url: str | None = None
    seconds: int = Field(default=5, ge=1, le=15)
    resolution: str = "1280*720"


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
Operate in {mode} mode. PLAN means collaborate, clarify, research and build treatment/storyboard/shot lists before generation. CREATE means move efficiently toward executable shots while still asking for any essential missing constraints.
Reply in the user's language ({language}) unless asked otherwise.
Never pretend that a model job completed unless a tool/worker result confirms it.
When web research context is provided, distinguish verified public facts from creative inference.
Optimize for cinematic continuity, artist identity consistency, lyric timing, safe/authorized likeness use, lip-sync requirements, camera language, lighting, editing rhythm and exportability.
"""


async def _director_chat(messages: list[dict[str, str]], temperature: float = 0.55) -> str:
    payload = {
        "model": DIRECTOR_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 1800,
    }
    headers = {"Authorization": f"Bearer {DIRECTOR_API_KEY}"}
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(f"{DIRECTOR_BASE_URL}/chat/completions", json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Director model unavailable: {exc}") from exc


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": APP_NAME,
        "director_model": DIRECTOR_MODEL,
        "director_url": DIRECTOR_BASE_URL,
        "workers": {
            "whisper": WHISPER_URL,
            "wan": WAN_URL,
            "musetalk": MUSETALK_URL,
            "identity": IDENTITY_URL or None,
        },
    }


@app.post("/api/research")
async def research(req: ResearchRequest) -> dict[str, Any]:
    suffix = " ".join(x for x in [req.country, "artist musician music video interview social profiles"] if x)
    query = f'"{req.artist_name}" {suffix}'.strip()
    sources = _search(query, 12)
    source_text = "\n".join(
        f"- {x['title']} | {x['url']} | {x['snippet'][:500]}" for x in sources
    )
    prompt = f"""Build a cautious public Artist Profile for {req.artist_name}.
Country hint: {req.country or 'unknown'}.
Use ONLY the search results below as factual evidence. If evidence is sparse or ambiguous, say so clearly.
Return a compact profile covering: identity confidence, musical identity, visual identity, known public videos/performances, recurring themes, fashion/presentation, audience signals, useful creative observations, and a short source list.

SEARCH RESULTS:\n{source_text or '(no results)'}"""
    answer = await _director_chat([
        {"role": "system", "content": _director_system("PLAN", req.language, req.artist_name)},
        {"role": "user", "content": prompt},
    ], temperature=0.25)
    return {"summary": answer, "sources": sources, "query": query}


@app.post("/api/chat")
async def chat(req: ChatRequest) -> dict[str, Any]:
    messages: list[dict[str, str]] = [
        {"role": "system", "content": _director_system(req.mode, req.language, req.artist_name)}
    ]
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
    if not IDENTITY_URL:
        return {
            "ready": False,
            "message": "Image coverage accepted. The open-source 3D identity worker is not enabled yet; it remains isolated until its complete dependency/weight licensing is verified.",
            "image_count": len(images),
        }
    multipart = []
    for image in images:
        multipart.append(("images", (image.filename or "image.jpg", await image.read(), image.content_type or "image/jpeg")))
    async with httpx.AsyncClient(timeout=1800) as client:
        response = await client.post(f"{IDENTITY_URL}/build", files=multipart)
    response.raise_for_status()
    return response.json()


@app.post("/api/identity/refine")
async def identity_refine(req: RefineRequest) -> dict[str, Any]:
    if not IDENTITY_URL:
        return {"queued": False, "message": "Refinement instruction saved; identity worker is not enabled yet."}
    async with httpx.AsyncClient(timeout=1800) as client:
        response = await client.post(f"{IDENTITY_URL}/refine", json=req.model_dump())
    response.raise_for_status()
    return response.json()


@app.post("/api/video/generate")
async def video_generate(req: VideoRequest) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{WAN_URL}/jobs", json=req.model_dump())
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Wan worker unavailable: {exc}") from exc


@app.post("/api/lipsync")
async def lipsync(req: LipSyncRequest) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{MUSETALK_URL}/jobs", json=req.model_dump())
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"MuseTalk worker unavailable: {exc}") from exc
