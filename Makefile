.PHONY: up down build logs seed events train retrain score backup bootstrap clean

# --- Core lifecycle ---
up:
	docker compose up -d

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f

# --- One-off scripts (run inside container) ---
seed:
	docker compose run --rm scripts python scripts/seed_db.py

events:
	docker compose run --rm scripts python scripts/generate_events.py

train:
	docker compose run --rm scripts python scripts/train.py --set-active

retrain:
	docker compose run --rm scripts python scripts/retrain.py

score:
	docker compose run --rm scripts python scripts/batch_score.py

backup:
	docker compose run --rm scripts bash scripts/backup_db.sh

# --- Bootstrap (full setup from scratch) ---
bootstrap: build
	docker compose up -d postgres
	@echo "Waiting for Postgres to be healthy..."
	@until docker compose exec postgres pg_isready -U postgres -q 2>/dev/null; do sleep 1; done
	docker compose run --rm scripts alembic upgrade head
	docker compose run --rm scripts python scripts/seed_db.py
	docker compose run --rm scripts python scripts/generate_events.py
	docker compose run --rm scripts python scripts/train.py --set-active
	docker compose up -d
	@echo ""
	@echo "Stack is running. API available at http://localhost:80"
	@echo "Create an API key:  docker compose run --rm scripts python scripts/manage_keys.py create --name dev"

# --- Cleanup ---
clean:
	docker compose down -v
