FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY services/api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY services/api/app ./app
EXPOSE 8000
CMD ["uvicorn","app.combined:app","--host","0.0.0.0","--port","8000"]
