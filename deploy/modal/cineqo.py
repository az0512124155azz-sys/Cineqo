import base64
import io
import os
import tempfile
from pathlib import Path
from typing import Any

import modal

APP_NAME = "cineqo-gpu"
MODEL_VOLUME = modal.Volume.from_name("cineqo-models", create_if_missing=True)
MODEL_DIR = "/models"

app = modal.App(APP_NAME)

qwen_image = (
    modal.Image.debian_slim(python_version="3.12")
    .uv_pip_install(
        "torch==2.7.1",
        "torchvision==0.22.1",
        "transformers>=4.51,<5",
        "accelerate>=1.6,<2",
        "qwen-vl-utils>=0.0.11",
        "safetensors>=0.5",
    )
    .env({"HF_HOME": MODEL_DIR})
)

whisper_image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("ffmpeg")
    .uv_pip_install(
        "torch==2.7.1",
        "openai-whisper>=20250625",
    )
    .env({"XDG_CACHE_HOME": MODEL_DIR})
)

wan_image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("ffmpeg")
    .uv_pip_install(
        "torch==2.7.1",
        "torchvision==0.22.1",
        "diffusers>=0.35,<0.36",
        "transformers>=4.51,<5",
        "accelerate>=1.6,<2",
        "safetensors>=0.5",
        "sentencepiece>=0.2",
        "imageio>=2.37",
        "imageio-ffmpeg>=0.6",
        "pillow>=11",
    )
    .env({"HF_HOME": MODEL_DIR})
)

api_image = modal.Image.debian_slim(python_version="3.12").uv_pip_install(
    "fastapi>=0.116,<1",
    "python-multipart>=0.0.20,<1",
)


@app.cls(
    image=qwen_image,
    gpu="A10G",
    timeout=900,
    scaledown_window=60,
    volumes={MODEL_DIR: MODEL_VOLUME},
)
class Director:
    @modal.enter()
    def load(self) -> None:
        import torch
        from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

        model_id = "Qwen/Qwen2.5-VL-7B-Instruct"
        self.processor = AutoProcessor.from_pretrained(model_id, cache_dir=MODEL_DIR)
        self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            model_id,
            torch_dtype=torch.bfloat16,
            device_map="auto",
            cache_dir=MODEL_DIR,
        )
        MODEL_VOLUME.commit()

    @modal.method()
    def chat(self, prompt: str, max_new_tokens: int = 900) -> str:
        messages = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
        text = self.processor.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        inputs = self.processor(text=[text], return_tensors="pt", padding=True).to(self.model.device)
        generated = self.model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=True, temperature=0.5)
        generated = generated[:, inputs.input_ids.shape[1]:]
        return self.processor.batch_decode(generated, skip_special_tokens=True)[0].strip()


@app.cls(
    image=whisper_image,
    gpu="T4",
    timeout=900,
    scaledown_window=30,
    volumes={MODEL_DIR: MODEL_VOLUME},
)
class Whisper:
    @modal.enter()
    def load(self) -> None:
        import whisper

        self.model = whisper.load_model("small", download_root=f"{MODEL_DIR}/whisper", device="cuda")
        MODEL_VOLUME.commit()

    @modal.method()
    def transcribe(self, audio_bytes: bytes, suffix: str = ".webm") -> dict[str, Any]:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(audio_bytes)
            path = f.name
        try:
            result = self.model.transcribe(path)
            return {"text": str(result.get("text", "")).strip(), "language": result.get("language")}
        finally:
            Path(path).unlink(missing_ok=True)


@app.cls(
    image=wan_image,
    gpu="A10G",
    timeout=3600,
    scaledown_window=60,
    volumes={MODEL_DIR: MODEL_VOLUME},
    ephemeral_disk=524288,
)
class Wan:
    @modal.enter()
    def load(self) -> None:
        import torch
        from diffusers import DiffusionPipeline

        model_id = "Wan-AI/Wan2.2-TI2V-5B-Diffusers"
        self.pipe = DiffusionPipeline.from_pretrained(
            model_id,
            torch_dtype=torch.bfloat16,
            cache_dir=MODEL_DIR,
        )
        self.pipe.enable_model_cpu_offload()
        MODEL_VOLUME.commit()

    @modal.method()
    def generate(self, prompt: str, image_bytes: bytes | None = None) -> bytes:
        from diffusers.utils import export_to_video
        from PIL import Image

        kwargs: dict[str, Any] = {
            "prompt": prompt,
            "num_frames": 33,
            "height": 384,
            "width": 672,
            "num_inference_steps": 14,
            "guidance_scale": 5.0,
        }
        if image_bytes:
            kwargs["image"] = Image.open(io.BytesIO(image_bytes)).convert("RGB")

        output = self.pipe(**kwargs)
        frames = output.frames[0]
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            output_path = f.name
        try:
            export_to_video(frames, output_path, fps=24)
            return Path(output_path).read_bytes()
        finally:
            Path(output_path).unlink(missing_ok=True)


def _authorized(auth_header: str | None) -> bool:
    expected = os.environ.get("CINEQO_MODAL_API_KEY", "")
    if not expected:
        return False
    return auth_header == f"Bearer {expected}"


@app.function(
    image=api_image,
    timeout=3600,
    secrets=[modal.Secret.from_name("cineqo-api")],
)
@modal.asgi_app()
def web():
    from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
    from fastapi.responses import Response

    api = FastAPI(title="Cineqo Modal GPU API")

    def guard(authorization: str | None) -> None:
        if not _authorized(authorization):
            raise HTTPException(status_code=401, detail="Unauthorized")

    @api.get("/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "service": APP_NAME, "models": ["qwen2.5-vl-7b", "whisper-small", "wan2.2-ti2v-5b"]}

    @api.post("/director")
    async def director(prompt: str = Form(...), authorization: str | None = Header(None)) -> dict[str, str]:
        guard(authorization)
        return {"text": await Director().chat.remote.aio(prompt)}

    @api.post("/transcribe")
    async def transcribe(audio: UploadFile = File(...), authorization: str | None = Header(None)) -> dict[str, Any]:
        guard(authorization)
        data = await audio.read()
        suffix = Path(audio.filename or "voice.webm").suffix or ".webm"
        return await Whisper().transcribe.remote.aio(data, suffix)

    @api.post("/generate")
    async def generate(
        prompt: str = Form(...),
        image: UploadFile | None = File(None),
        authorization: str | None = Header(None),
    ) -> Response:
        guard(authorization)
        image_bytes = await image.read() if image else None
        video = await Wan().generate.remote.aio(prompt, image_bytes)
        return Response(content=video, media_type="video/mp4", headers={"Content-Disposition": "attachment; filename=cineqo-shot.mp4"})

    return api


@app.local_entrypoint()
def main() -> None:
    print("Deploy with: modal deploy deploy/modal/cineqo.py")
