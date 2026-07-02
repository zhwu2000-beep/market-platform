# Market Platform

Long-term AI investment research platform built with Python 3.14 and uv.

## Development

Install dependencies:

```bash
uv sync
```

Copy environment variables:

```bash
Copy-Item .env.example .env
```

Run checks:

```bash
uv run pytest
uv run ruff check .
uv run mypy src
```

## Architecture

See [docs/architecture.md](docs/architecture.md).
