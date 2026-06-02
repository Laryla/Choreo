.PHONY: install dev sync lint test db-up db-down db-reset

install:
	uv sync

dev:
	uv run uvicorn choreo.gateway.app:app --reload --port 8009

sync:
	uv sync --extra dev

lint:
	uv run ruff check choreo/

test:
	uv run pytest tests/ -v

db-up:
	docker run -d \
		--name choreo-postgres \
		-e POSTGRES_USER=postgres \
		-e POSTGRES_PASSWORD=postgres123 \
		-e POSTGRES_DB=choreo \
		-p 5432:5432 \
		postgres:16

db-down:
	docker stop choreo-postgres && docker rm choreo-postgres

db-reset:
	docker stop choreo-postgres && docker rm choreo-postgres && $(MAKE) db-up
