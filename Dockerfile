# La app (la versión que montar.py trajo a ./app) lista para el servidor: PostgreSQL y FFmpeg para lo que
# corre aquí; las IA no se instalan (trabajan en el equipo de cada persona).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY app/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt "psycopg[binary]>=3.2"
COPY app/ /app/

RUN useradd -m -u 1000 marketing && mkdir -p /datos && chown -R marketing:marketing /app /datos
USER marketing
VOLUME /datos
EXPOSE 8800
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8800/api/health', timeout=5)" || exit 1
CMD ["python", "app.py"]
