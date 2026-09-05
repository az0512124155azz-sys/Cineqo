# Cineqo GPU server deployment

This server runs every open AI model used by Cineqo behind one API and one shared runtime volume.

## Recommended server

Use a Linux NVIDIA GPU server with **48 GB VRAM** for the simplest all-in-one deployment. A 24 GB card can run Wan 2.2 TI2V-5B with offload, but running Wan, Qwen Director, MuseTalk, Whisper and TripoSR together is much more reliable on 48 GB.

Recommended starting class: NVIDIA A40 / RTX A6000 / L40 / RTX 6000 Ada, Ubuntu 22.04+, 50+ GB system RAM, 150+ GB persistent disk.

## 1. Install host prerequisites

The host needs:

- NVIDIA driver
- Docker Engine + Docker Compose v2
- NVIDIA Container Toolkit
- Git
- Python 3 + pip

Verify before continuing:

```bash
nvidia-smi
docker --version
docker compose version
docker run --rm --gpus all nvidia/cuda:12.6.3-base-ubuntu22.04 nvidia-smi
```

## 2. Clone Cineqo

```bash
git clone https://github.com/az0512124155azz-sys/Cineqo.git
cd Cineqo
cp .env.example .env
```

## 3. Download model weights

```bash
chmod +x deploy/gpu/bootstrap.sh
./deploy/gpu/bootstrap.sh
```

This downloads Wan 2.2 TI2V-5B and the complete MuseTalk inference bundle. Qwen3-4B, Whisper and TripoSR populate their persistent caches at first start.

## 4. Start the full stack

```bash
docker compose --profile gpu up -d --build
```

Watch first boot:

```bash
docker compose --profile gpu logs -f director whisper wan musetalk identity api
```

Qwen, Whisper and TripoSR may download model files on the first launch.

## 5. Verify every model

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/models/status
```

`/api/models/status` should report all five engines ready:

- director — Qwen3-4B through vLLM
- whisper — speech-to-text / voice input
- wan — Wan 2.2 TI2V-5B video generation
- musetalk — lip sync
- identity — TripoSR base 3D reconstruction

## 6. Network exposure

Only expose the Cineqo web/API entry point publicly. Do **not** expose ports 8001 or 8011-8014 to the public Internet in production.

For an all-in-one server, publish the web container on port 8080 and put HTTPS in front of it using your cloud provider proxy, Caddy or Cloudflare Tunnel.

The internal model services communicate on the Docker network.

## 7. Persistent folders

Do not delete these directories between restarts:

```text
models/
runtime/shared/
```

`models/` contains downloaded weights/caches. `runtime/shared/` contains uploaded media and intermediate/final generated assets.

## 8. What CREATE mode now does

When the UI is in CREATE mode:

1. The Director turns the request into a cinematic generation prompt.
2. If a song is attached, Whisper transcribes it for lyrical/timing context.
3. Wan 2.2 generates the video. An attached image is used as image-to-video conditioning.
4. If a song is attached, MuseTalk is automatically started after the Wan job succeeds.
5. The browser polls job status and exposes the finished output through the API.

PLAN mode continues to use the Director + optional DuckDuckGo public web research without starting expensive video generation.

## 9. Digital Identity

Uploaded artist photos are sent to the TripoSR identity worker and the generated model is returned to the Cineqo review flow. The current TripoSR adapter creates the base reconstruction. Text chat refinement requests are stored/routed by the identity API, but TripoSR itself is not a text-guided mesh editor; a stronger permissively licensed refinement engine is still required before claiming arbitrary chat-based mesh editing is fully implemented.

## 10. Authentication

Google / Apple / email buttons intentionally remain demo-only until the public HTTPS deployment is stable. OAuth callback URLs should be configured only after the final production domain exists.
