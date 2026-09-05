FROM nvidia/cuda:12.6.3-cudnn-runtime-ubuntu22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip ffmpeg git && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/cineqo
COPY third_party/audio/whisper /opt/whisper
RUN pip3 install --no-cache-dir fastapi uvicorn[standard] python-multipart && pip3 install --no-cache-dir -e /opt/whisper
COPY services/workers/whisper/app.py /opt/cineqo/app.py
ENV WHISPER_MODEL=small WHISPER_DEVICE=cuda
EXPOSE 8011
CMD ["python3","-m","uvicorn","app:app","--host","0.0.0.0","--port","8011"]
