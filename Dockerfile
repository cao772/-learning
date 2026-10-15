FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd -u 10001 -m hub && mkdir -p /data /backups /app/.private && chown hub:hub /data /backups /app/.private
COPY hub ./hub
COPY llm-learning.html new-knowledge.html ./
USER hub
ENV HUB_DB=/data/hub.sqlite HUB_SECURE=1 PYTHONUNBUFFERED=1
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz',timeout=3)"
CMD ["gunicorn","--bind","0.0.0.0:8000","--workers","1","--threads","4","--timeout","45","hub.app:create_app()"]
