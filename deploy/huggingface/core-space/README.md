---
title: Cineqo Core
emoji: 🎬
colorFrom: gray
colorTo: blue
sdk: gradio
sdk_version: 5.49.1
app_file: app.py
pinned: false
python_version: 3.12
---

# Cineqo Core

ZeroGPU development worker for Cineqo. It exposes two Gradio API endpoints:

- `/director` — Qwen2.5-VL-7B-Instruct creative director
- `/transcribe` — OpenAI Whisper multilingual speech-to-text

Select **ZeroGPU** in the Space hardware settings. This Space is intended for development/testing under Hugging Face daily GPU quotas, not production throughput.
