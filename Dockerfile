FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

# kaleido 0.2.1 bundled renderer needs these shared libs
RUN apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 libnss3 libfontconfig1 libx11-xcb1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

CMD ["uv", "run", "python", "main.py"]
