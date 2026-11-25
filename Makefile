.PHONY: dev test seed docker build lint
dev:        ## run API + web app locally (no Docker)
	./scripts/dev.sh
test:       ## backend unit/API tests + frontend type-check/build
	cd backend && .venv/bin/python -m pytest -q
	cd frontend && npm run build
seed:       ## regenerate the sample dataset (deterministic)
	python3 data/scripts/generate_seed.py
champions:  ## refresh champion snapshot from Riot Data Dragon
	python3 data/scripts/fetch_champions.py
docker:     ## run everything with Docker → http://localhost:8080
	docker compose up --build
lint:
	cd frontend && npx oxlint src
