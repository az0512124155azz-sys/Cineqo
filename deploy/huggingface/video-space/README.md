---
title: Cineqo Video
emoji: 🎥
colorFrom: gray
colorTo: black
sdk: gradio
sdk_version: 5.49.1
app_file: app.py
pinned: false
python_version: 3.12
---

# Cineqo Video

ZeroGPU development worker for Cineqo using **Wan-AI/Wan2.2-TI2V-5B-Diffusers**.

API endpoint:

- `/generate` — creates one short development shot and returns an MP4 file.

Select **ZeroGPU** in the Space hardware settings. The free profile intentionally uses fewer frames and inference steps because a free Hugging Face account has a limited daily ZeroGPU quota. Production quality/length should later move to dedicated GPU compute.
