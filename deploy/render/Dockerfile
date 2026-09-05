FROM python:3.12-slim
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends nginx supervisor ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/cineqo
COPY services/api/requirements.txt /opt/cineqo/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY services/api/app /opt/cineqo/api
COPY services/api/free_main.py /opt/cineqo/api/free_main.py
COPY services/api/modal_main.py /opt/cineqo/api/modal_main.py
COPY apps/web /usr/share/nginx/html
COPY deploy/render/nginx.conf /etc/nginx/sites-available/default
COPY deploy/render/supervisord.conf /etc/supervisor/conf.d/cineqo.conf
EXPOSE 10000
CMD ["/usr/bin/supervisord","-c","/etc/supervisor/supervisord.conf"]
