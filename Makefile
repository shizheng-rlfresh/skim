dev:
	uv run textual run --dev "skim:SkimApp"

run:
	uv run skim

lint:
	uv run ruff check src/ tests/
	uv run ruff format --check src/ tests/

fix:
	uv run ruff check --fix src/ tests/
	uv run ruff format src/ tests/

test:
	uv run pytest -v

.PHONY: dev run lint fix test