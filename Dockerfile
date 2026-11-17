FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends clang g++ curl nodejs npm \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY csrc ./csrc
COPY src ./src
COPY ui ./ui

RUN pip install --no-cache-dir uv && uv sync --frozen --no-dev
RUN cd ui && npm ci && npm run build

EXPOSE 8110
CMD ["uv", "run", "tokendiet", "serve", "--host", "0.0.0.0", "--port", "8110"]
