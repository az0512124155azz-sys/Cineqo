# Cineqo free-cloud development deployment

This profile is for getting the real Cineqo flow online at $0 for development/testing.

Architecture:

1. **Render Free** hosts the Cineqo website and FastAPI bridge together.
2. **Hugging Face ZeroGPU Space #1** runs Qwen2.5-VL-7B-Instruct + Whisper.
3. **Hugging Face ZeroGPU Space #2** runs Wan 2.2 TI2V-5B for short development shots.

The free profile intentionally does **not** claim production throughput. Hugging Face Free ZeroGPU has a daily GPU quota, so this setup is for validating the real end-to-end product before moving video generation to dedicated GPU compute.

## A. Create the Core Space

Create a new Hugging Face Space named, for example, `cineqo-core`:

- SDK: Gradio
- Hardware: ZeroGPU
- Python: 3.12

Copy these repository files into the root of that Space:

- `deploy/huggingface/core-space/app.py` -> `app.py`
- `deploy/huggingface/core-space/requirements.txt` -> `requirements.txt`
- `deploy/huggingface/core-space/README.md` -> `README.md`

Wait until the Space status is **Running** and both API endpoints appear in **Use via API**:

- `/director`
- `/transcribe`

## B. Create the Video Space

Create another Space named, for example, `cineqo-video`:

- SDK: Gradio
- Hardware: ZeroGPU
- Python: 3.12

Copy:

- `deploy/huggingface/video-space/app.py` -> `app.py`
- `deploy/huggingface/video-space/requirements.txt` -> `requirements.txt`
- `deploy/huggingface/video-space/README.md` -> `README.md`

Wait until `/generate` is visible under **Use via API**.

## C. Create a Hugging Face token

Create a read token that can access both Spaces. Do not commit it to GitHub.

## D. Deploy Render

In Render choose **New -> Blueprint** and connect:

`az0512124155azz-sys/Cineqo`

Render reads the root `render.yaml`.

Set these secret environment variables when prompted:

```text
CINEQO_HF_CORE_SPACE=YOUR_HF_USERNAME/cineqo-core
CINEQO_HF_VIDEO_SPACE=YOUR_HF_USERNAME/cineqo-video
CINEQO_HF_TOKEN=hf_...
```

The Render service hosts both the web UI and API, so no Vercel deployment is required for the first working version.

## E. Verify

Open:

```text
https://YOUR-RENDER-SERVICE.onrender.com/health
https://YOUR-RENDER-SERVICE.onrender.com/api/models/status
```

Expected status:

- `core_space_configured: true`
- `video_space_configured: true`
- `/api/models/status` -> `ready: true`

Then test in the actual Cineqo UI:

1. artist research
2. PLAN chat
3. microphone -> Whisper -> composer text
4. CREATE with a short text prompt
5. wait for the Wan job
6. open the returned MP4

## Current free-profile limits

- ZeroGPU free usage is quota-limited, so short shots are used for development.
- Render Free sleeps after inactivity and uses an ephemeral filesystem.
- Google / Apple / email authentication remains disabled until the final public HTTPS domain and persistent user storage are selected.
- 3D model chat editing was intentionally removed. Digital Identity generation is not enabled in the free profile yet.
