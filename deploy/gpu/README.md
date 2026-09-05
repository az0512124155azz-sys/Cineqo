# Cineqo GPU server deployment

Cineqo is designed to run its open AI stack behind one public web gateway. The simplest first production deployment is one Ubuntu GPU VM with Docker Compose and one persistent filesystem.

## Recommended first server

Use a **1x NVIDIA RTX A6000 48 GB** Lambda Cloud instance (or an equivalent full Ubuntu GPU VM with at least 48 GB VRAM).

Why 48 GB: Cineqo runs a multimodal 7B Director plus Wan 2.2 TI2V-5B, MuseTalk, Whisper and TripoSR. Wan can run on a 24 GB GPU with offload, but 48 GB gives much more room for a single-node integrated deployment.

Recommended minimums:

- Ubuntu LTS
- NVIDIA GPU with 48 GB VRAM
- 80+ GB system RAM
- 250+ GB disk; 500 GB is preferable for model caches and generated video
- public IPv4 address

## 1. Create the VM

In Lambda Cloud:

1. Add your SSH public key to the workspace.
2. Launch a **1x RTX A6000 48 GB** instance.
3. Copy the public IP from the Instances page.
4. Connect from your computer:

```bash
ssh -i ~/.ssh/YOUR_KEY ubuntu@YOUR_SERVER_IP
```

Lambda GPU instances already include the NVIDIA software stack, but verify the GPU first:

```bash
nvidia-smi
```

## 2. Install Docker Engine

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git python3 python3-venv gnupg
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
. /etc/os-release
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${UBUNTU_CODENAME:-$VERSION_CODENAME} stable" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker "$USER"
```

Log out and SSH back in so the Docker group is active.

## 3. Install and configure NVIDIA Container Toolkit

```bash
sudo apt-get update
sudo apt-get install -y --no-install-recommends ca-certificates curl gnupg2
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

Verify that Docker can see the GPU:

```bash
docker run --rm --gpus all nvidia/cuda:12.6.3-base-ubuntu22.04 nvidia-smi
```

Do not continue until this command shows the NVIDIA GPU.

## 4. Clone Cineqo

```bash
git clone https://github.com/az0512124155azz-sys/Cineqo.git
cd Cineqo
cp .env.example .env
```

The default runtime uses only approved open components:

- Qwen/Qwen2.5-VL-7B-Instruct — multimodal Director, planning and uploaded clip/reference analysis
- OpenAI Whisper — chat microphone speech-to-text and song transcription
- Wan 2.2 TI2V-5B — text-to-video and image-to-video
- MuseTalk 1.5 — lip sync
- TripoSR — base Digital Identity 3D reconstruction

## 5. Download the large model assets

```bash
chmod +x deploy/gpu/bootstrap.sh
./deploy/gpu/bootstrap.sh
```

The script downloads Wan 2.2 TI2V-5B and the complete MuseTalk 1.5 bundle. Qwen2.5-VL-7B, Whisper and TripoSR populate their persistent caches automatically on first boot.

## 6. Start every service

```bash
docker compose --profile gpu up -d --build
```

The first build/start can take a long time because CUDA images, Python packages and model weights are large.

Watch the startup:

```bash
docker compose --profile gpu logs -f director whisper wan musetalk identity api web
```

Press `Ctrl+C` to stop following logs; the containers keep running.

## 7. Verify all AI engines

Only the web gateway is published to the host, on port 8080. Internal AI ports are not public.

```bash
chmod +x deploy/gpu/verify.sh
./deploy/gpu/verify.sh
```

Or manually:

```bash
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/api/models/status
```

`/api/models/status` must report every engine ready:

- director — Qwen2.5-VL-7B-Instruct via vLLM
- whisper — OpenAI Whisper
- wan — Wan 2.2 TI2V-5B
- musetalk — MuseTalk 1.5
- identity — TripoSR

Do not move on to public deployment until the result says all engines are ready.

## 8. Open the app for a private server test

Temporarily allow inbound TCP port **8080** in the cloud firewall and browse to:

```text
http://YOUR_SERVER_IP:8080
```

Test this complete sequence before configuring a domain:

1. onboarding research
2. upload artist clips and references; wait for Qwen visual analysis
3. upload identity photos; wait for TripoSR
4. inspect the generated GLB in the 3D viewer
5. use the microphone and confirm Whisper inserts text in the composer
6. PLAN mode chat
7. CREATE mode with a short prompt and no song
8. CREATE mode with a song and confirm Wan completes followed by MuseTalk

## 9. Public HTTPS / cloud layer

For a stable public deployment, point a domain or subdomain such as `app.example.com` at the GPU VM and put HTTPS in front of port 8080. Caddy or Cloudflare Tunnel are both suitable.

Only the web gateway should be Internet-facing. The Director, Whisper, Wan, MuseTalk, TripoSR and raw API containers stay on the private Docker network.

Once the HTTPS hostname is final, set:

```env
CINEQO_CORS_ORIGINS=https://app.example.com
```

Then restart:

```bash
docker compose --profile gpu up -d
```

## 10. Persistence and backups

Do not delete these directories:

```text
models/
runtime/shared/
```

`models/` stores downloaded weights and caches. `runtime/shared/` stores uploads, sampled reference frames, generated 3D models, generated videos and lip-sync outputs.

For a real launch, back up `runtime/shared/` or migrate generated user assets to object storage before enabling account authentication.

## 11. What is genuinely connected now

- Artist web research -> Director
- uploaded artist/reference videos -> sampled frames -> multimodal Director -> Visual DNA
- microphone -> Whisper -> composer text
- song -> Whisper -> Director context
- PLAN -> Director + optional public web research
- CREATE -> Director prompt -> Wan 2.2 -> MuseTalk when a song is attached
- identity photos -> TripoSR -> GLB preview -> review screen

One limitation remains explicit: TripoSR creates the base 3D reconstruction but is **not** a text-guided arbitrary mesh editor. Cineqo currently records/routs model-chat refinement requests rather than pretending TripoSR edited geometry. A separate permissively licensed 3D refinement engine is required before that one feature can truthfully be called complete.

## 12. Authentication comes after HTTPS

Google / Apple / email remain intentionally disabled as real authentication until the final HTTPS domain is stable. OAuth callback URLs and session security should be configured only after the public hostname is fixed.
