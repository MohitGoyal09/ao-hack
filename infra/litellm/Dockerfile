FROM python:3.12-slim

RUN pip install --no-cache-dir "litellm[proxy]==1.84.0"

WORKDIR /app
COPY config.yaml ./config.yaml

EXPOSE 4000
CMD ["litellm", "--config", "/app/config.yaml", "--port", "4000"]
