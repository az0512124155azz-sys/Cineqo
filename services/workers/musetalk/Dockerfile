FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip python3-dev build-essential ffmpeg git && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/musetalk
COPY third_party/lipsync/MuseTalk /opt/musetalk
RUN pip3 install --no-cache-dir --upgrade pip setuptools wheel && \
    pip3 install --no-cache-dir torch==2.0.1 torchvision==0.15.2 torchaudio==2.0.2 --index-url https://download.pytorch.org/whl/cu118 && \
    pip3 install --no-cache-dir -r requirements.txt && \
    pip3 install --no-cache-dir -U openmim && \
    mim install mmengine && \
    mim install "mmcv==2.0.1" && \
    mim install "mmdet==3.1.0" && \
    mim install "mmpose==1.1.0" && \
    pip3 install --no-cache-dir fastapi uvicorn[standard]
COPY services/workers/musetalk/app.py /opt/cineqo/app.py
ENV MUSETALK_ROOT=/opt/musetalk MUSETALK_OUTPUT_DIR=/shared/musetalk FFMPEG_PATH=ffmpeg MUSETALK_UNET=/models/musetalkV15/unet.pth MUSETALK_UNET_CONFIG=/models/musetalkV15/musetalk.json
EXPOSE 8013
WORKDIR /opt/cineqo
CMD ["python3","-m","uvicorn","app:app","--host","0.0.0.0","--port","8013"]
