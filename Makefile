.PHONY: sync check test ui-build demo eval-ollama serve

sync:
	uv sync --all-extras

check:
	uv run ruff format --check src tests
	uv run ruff check src tests
	uv run mypy src tests

test:
	uv run pytest --cov=tokendiet --cov-report=term-missing --cov-fail-under=95

ui-build:
	cd ui && npm install && npm run build

demo:
	uv run tokendiet demo

eval-ollama:
	uv run tokendiet eval-ollama --live-only

serve:
	uv run tokendiet serve --host 127.0.0.1 --port 8110
