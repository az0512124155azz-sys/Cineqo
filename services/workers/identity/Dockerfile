FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip git build-essential ninja-build && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/triposr
COPY third_party/3d/TripoSR /opt/triposr
RUN pip3 install --no-cache-dir --upgrade pip setuptools wheel && pip3 install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cu121 && pip3 install --no-cache-dir -r requirements.txt && pip3 install --no-cache-dir fastapi uvicorn[standard] python-multipart
COPY services/workers/identity/app.py /opt/cineqo/app.py
ENV TRIPOSR_ROOT=/opt/triposr TRIPOSR_OUTPUT_DIR=/outputs
EXPOSE 8014
WORKDIR /opt/cineqo
CMD ["python3","-m","uvicorn","app:app","--host","0.0.0.0","--port","8014"]
