import tempfile
from pathlib import Path

import gradio as gr
import spaces
import torch
from diffusers import AutoencoderKLWan, WanPipeline
from diffusers.utils import export_to_video, load_image

MODEL_ID = "Wan-AI/Wan2.2-TI2V-5B-Diffusers"

vae = AutoencoderKLWan.from_pretrained(MODEL_ID, subfolder="vae", torch_dtype=torch.float32)
pipe = WanPipeline.from_pretrained(MODEL_ID, vae=vae, torch_dtype=torch.bfloat16)
pipe.to("cuda")

NEGATIVE = (
    "overexposed, static, blurry details, subtitles, low quality, jpeg artifacts, ugly, "
    "deformed hands, deformed face, fused fingers, duplicated limbs, still image, messy background"
)


@spaces.GPU(duration=300)
def generate(prompt: str, image: str | None = None):
    # Free-cloud development profile: short shots keep ZeroGPU usage within the free daily quota.
    kwargs = {
        "prompt": prompt,
        "negative_prompt": NEGATIVE,
        "height": 704,
        "width": 1280,
        "num_frames": 33,
        "guidance_scale": 5.0,
        "num_inference_steps": 12,
    }
    # Wan 2.2 TI2V supports image conditioning. Diffusers exposes the image through the pipeline
    # when supported by the installed main-branch implementation. If no image is supplied, this is T2V.
    if image:
        kwargs["image"] = load_image(image)
    frames = pipe(**kwargs).frames[0]
    out = Path(tempfile.mkdtemp(prefix="cineqo-wan-")) / "shot.mp4"
    export_to_video(frames, str(out), fps=16)
    return str(out)


with gr.Blocks(title="Cineqo Video") as demo:
    gr.Markdown("# Cineqo Video\nWan 2.2 TI2V-5B short-shot worker for the free-cloud development profile.")
    p = gr.Textbox(lines=8, label="Cinematic prompt")
    i = gr.Image(type="filepath", label="Optional reference image")
    v = gr.Video(label="Generated shot")
    gr.Button("Generate").click(generate, inputs=[p, i], outputs=v, api_name="generate")


demo.queue().launch()
