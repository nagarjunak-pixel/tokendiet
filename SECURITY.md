# Security Policy

## Reporting a Vulnerability

Please report security issues privately by emailing `sendemailtonagarjuna@gmail.com` with subject `[SECURITY] tokendiet`. Do not open public issues with exploit payloads.

## Local-First & Privacy Guarantees
- `tokendiet` runs 100% locally in-process (`clang++ -O3` native kernel + Python CLI/MCP server).
- AST skeletonization parses source via Python's standard-library `ast.parse` without executing target code.
- Live model evaluation (`eval-ollama`) connects strictly to your configured local Ollama daemon (`http://127.0.0.1:11434` by default).
