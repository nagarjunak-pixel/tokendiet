# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed
- Packaging: the C++20 kernel source moved from `csrc/` to `src/tokendiet/_csrc/` so it ships
  inside the wheel and sdist; the loader now resolves it relative to the installed package, so the
  native kernel compiles after `pip install` (previously an installed wheel silently used the
  Python fallback).
- `pyproject.toml`: added keywords, classifiers, project URLs, `py.typed` marker and an explicit
  sdist include list in preparation for a PyPI release.
- Docs: plainer project description, a "Scope & Limitations" section and an "Install" section.

## [1.0.0] - 2026-11-17

### Added
- Order-preserving 0/1 knapsack log pruner with mandatory error-anchor retention and anchor "halo"
  propagation; C++20 kernel (`clang++ -O3`, loaded via `ctypes`) with a pure-Python reference
  implementation and differential Hypothesis tests.
- Python AST skeletonizer that elides unfocused function bodies and re-validates output with
  `ast.parse`.
- Cross-turn block deduplication for repeated `read_file` payloads using `[@tokendiet:ref]`
  back-pointers.
- Rule-based cascade model router (local / balanced / frontier tiers) with retry and
  formal/security escalation guards.
- `tokendiet` CLI (`demo`, `prune`, `skeleton`, `eval-ollama`, `serve`, `mcp-stdio`), MCP stdio
  server exposing four tools, FastAPI API and React workbench UI.
- Six-task live audit against a local `qwen3.5:4b` model via Ollama
  (`benchmarks/real_qwen_tokendiet.json`).

[Unreleased]: https://github.com/nagarjunak-pixel/tokendiet/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/nagarjunak-pixel/tokendiet/releases/tag/v1.0.0
