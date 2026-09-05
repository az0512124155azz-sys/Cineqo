import json
import tempfile
from pathlib import Path

import gradio as gr
import spaces
import torch
import whisper
from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

MODEL_ID = "Qwen/Qwen2.5-VL-7B-Instruct"

processor = AutoProcessor.from_pretrained(MODEL_ID)
model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
    MODEL_ID,
    torch_dtype=torch.bfloat16,
    device_map="cuda",
)
whisper_model = whisper.load_model("small", device="cuda")


@spaces.GPU(duration=90)
def director(prompt: str) -> str:
    messages = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = processor(text=[text], padding=True, return_tensors="pt").to("cuda")
    with torch.inference_mode():
        generated = model.generate(**inputs, max_new_tokens=900, do_sample=True, temperature=0.45)
    trimmed = [out[len(inp):] for inp, out in zip(inputs.input_ids, generated)]
    return processor.batch_decode(trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False)[0]


@spaces.GPU(duration=75)
def transcribe(audio: str):
    result = whisper_model.transcribe(audio, fp16=True)
    return {
        "text": result.get("text", "").strip(),
        "language": result.get("language"),
        "segments": [
            {"start": x.get("start"), "end": x.get("end"), "text": x.get("text", "").strip()}
            for x in result.get("segments", [])
        ],
    }


with gr.Blocks(title="Cineqo Core") as demo:
    gr.Markdown("# Cineqo Core\nQwen Director + Whisper for the free-cloud development profile.")
    with gr.Tab("Director"):
        p = gr.Textbox(lines=12, label="Prompt")
        o = gr.Textbox(lines=16, label="Response")
        gr.Button("Run Director").click(director, inputs=p, outputs=o, api_name="director")
    with gr.Tab("Whisper"):
        a = gr.Audio(type="filepath", label="Audio")
        j = gr.JSON(label="Transcription")
        gr.Button("Transcribe").click(transcribe, inputs=a, outputs=j, api_name="transcribe")


demo.queue().launch()
