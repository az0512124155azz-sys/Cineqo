#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

mkdir -p \
  models/wan/Wan2.2-TI2V-5B \
  models/musetalk/musetalkV15 \
  models/musetalk/syncnet \
  models/musetalk/dwpose \
  models/musetalk/face-parse-bisent \
  models/musetalk/sd-vae \
  models/musetalk/whisper \
  models/hf \
  models/whisper-cache \
  models/triposr-cache \
  runtime/shared

python3 -m pip install --upgrade "huggingface_hub[cli]" gdown

if command -v hf >/dev/null 2>&1; then
  HFCLI=hf
else
  HFCLI=huggingface-cli
fi

# Wan 2.2 TI2V-5B: text-to-video + image-to-video.
$HFCLI download Wan-AI/Wan2.2-TI2V-5B --local-dir models/wan/Wan2.2-TI2V-5B

# MuseTalk 1.5 and its required inference components.
$HFCLI download TMElyralab/MuseTalk --local-dir models/musetalk --include "musetalkV15/musetalk.json" "musetalkV15/unet.pth"
$HFCLI download stabilityai/sd-vae-ft-mse --local-dir models/musetalk/sd-vae --include "config.json" "diffusion_pytorch_model.bin"
$HFCLI download openai/whisper-tiny --local-dir models/musetalk/whisper --include "config.json" "pytorch_model.bin" "preprocessor_config.json"
$HFCLI download yzd-v/DWPose --local-dir models/musetalk/dwpose --include "dw-ll_ucoco_384.pth"
$HFCLI download ByteDance/LatentSync --local-dir models/musetalk/syncnet --include "latentsync_syncnet.pt"
gdown --id 154JgKpzCPW82qINcVieuPH3fZ2e0P812 -O models/musetalk/face-parse-bisent/79999_iter.pth
curl -fL https://download.pytorch.org/models/resnet18-5c106cde.pth -o models/musetalk/face-parse-bisent/resnet18-5c106cde.pth

# Qwen3, OpenAI Whisper and TripoSR model files are downloaded by their
# respective runtimes into the persistent model-cache directories on first boot.

echo "Cineqo model assets are ready."
echo "Start everything with: docker compose --profile gpu up -d --build"
