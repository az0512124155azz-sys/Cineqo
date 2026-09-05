FROM nvidia/cuda:12.6.3-cudnn-runtime-ubuntu22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip git ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/wan
COPY third_party/video/Wan2.2 /opt/wan
RUN pip3 install --no-cache-dir -r requirements.txt && pip3 install --no-cache-dir fastapi uvicorn[standard]
COPY services/workers/wan/app.py /opt/cineqo/app.py
ENV WAN_ROOT=/opt/wan WAN_CKPT_DIR=/models/Wan2.2-TI2V-5B WAN_TASK=ti2v-5B WAN_OUTPUT_DIR=/shared/wan
EXPOSE 8012
WORKDIR /opt/cineqo
CMD ["python3","-m","uvicorn","app:app","--host","0.0.0.0","--port","8012"]
