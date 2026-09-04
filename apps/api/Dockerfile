FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

COPY src/ ./src/
COPY main.py ./

EXPOSE 8123

CMD ["uv", "run", "main.py"]
