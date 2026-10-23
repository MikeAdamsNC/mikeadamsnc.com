FROM python:3.13-slim
WORKDIR /srv
COPY web/requirements.txt web/requirements.txt
RUN pip install --no-cache-dir -r web/requirements.txt
COPY web web
COPY content content
COPY brand/logo brand/logo
COPY brand/icon brand/icon
COPY brand/fonts brand/fonts
ENV PORT=8080
CMD exec uvicorn web.app:app --host 0.0.0.0 --port ${PORT} --proxy-headers
