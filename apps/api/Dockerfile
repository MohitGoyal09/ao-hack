FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

COPY src/ ./src/
COPY main.py ./

# ingestion.data_root() defaults to parents[4] of src/covenant/ingestion.py,
# which does not exist under /app; docker-compose bind-mounts ../../data/raw here.
# ponytail: COPY the 14 MB fixtures instead if the image must run without compose
# (needs a repo-root build context plus a .dockerignore for apps/web/node_modules).
ENV COVENANT_DATA_ROOT=/app/data/raw

EXPOSE 8123

CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8123"]
