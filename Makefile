.PHONY: format lint type test test-unit test-integration test-all all setup-dev venv pre-commit-install pre-commit-run check-lock check-openapi check-openapi-validate

format:
	ruff format .
	isort .

lint:
	ruff check .

type:
	mypy app tests

test:
	pytest tests/ -v

test-unit:
	pytest tests/ -m "not slow and not integration" -v -n auto

test-integration:
	pytest tests/ -m "integration" -v

test-all:
	pytest tests/ -v --cov=app --cov-report=term-missing

test-fast:
	pytest tests/ -m "not slow and not integration" -v -n auto -x

all: format lint type test

setup-dev:
	uv sync --all-extras --dev
	pre-commit install

venv:
	bash scripts/create_venv.sh

.PHONY: pre-commit-install
pre-commit-install:
	pre-commit install --install-hooks
	pre-commit autoupdate || true

.PHONY: pre-commit-run
pre-commit-run:
	pre-commit run --all-files

.PHONY: lock-uv lock-piptools
lock-uv:
	uv pip compile pyproject.toml -o requirements.txt
	uv pip compile --extra dev pyproject.toml -o requirements-dev.txt

lock-piptools:
	pip install pip-tools
	pip-compile pyproject.toml --output-file requirements.txt
	pip-compile pyproject.toml --extra dev --output-file requirements-dev.txt

check-lock:
	uv pip compile pyproject.toml -o requirements.txt
	uv pip compile --extra dev pyproject.toml -o requirements-dev.txt
	@git diff --exit-code requirements.txt requirements-dev.txt || (echo "Lockfiles are out of date. Run 'make lock-uv' and commit changes." && exit 1)

check-openapi: ## Run OpenAPI spec sync checks
	pytest tests/api/test_openapi_sync.py -v

check-openapi-validate: ## Validate OpenAPI spec syntax
	openapi-spec-validator docs/openapi/mobile_api.yaml
	openapi-spec-validator docs/openapi/mobile_api.json

# ==============================================================================
# Docker targets
# ==============================================================================

.PHONY: docker-build docker-build-no-cache docker-run docker-stop docker-restart
.PHONY: docker-logs docker-shell docker-test docker-clean docker-size docker-deploy
.PHONY: docker-build-mobile-api docker-build-mobile-api-no-cache docker-restart-mobile-api
.PHONY: docker-rebuild-mobile-api docker-logs-mobile-api docker-shell-mobile-api

docker-build:
	DOCKER_BUILDKIT=1 docker build --tag bsr:latest --progress=plain .

docker-build-no-cache:
	DOCKER_BUILDKIT=1 docker build --no-cache --tag bsr:latest --progress=plain .

docker-build-mobile-api:
	DOCKER_BUILDKIT=1 docker compose build mobile-api

docker-build-mobile-api-no-cache:
	DOCKER_BUILDKIT=1 docker compose build --no-cache mobile-api

docker-run:
	docker compose up -d

docker-stop:
	docker compose down

docker-restart: docker-stop docker-run

docker-logs:
	docker compose logs -f bsr

docker-logs-tail:
	docker compose logs --tail=100 -f bsr

docker-logs-mobile-api:
	docker compose logs -f mobile-api

docker-shell:
	docker compose exec bsr sh

docker-shell-root:
	docker compose exec -u root bsr sh

docker-shell-mobile-api:
	docker compose exec mobile-api sh

docker-restart-mobile-api:
	docker compose up -d mobile-api

docker-rebuild-mobile-api: docker-build-mobile-api docker-restart-mobile-api

docker-test:
	DOCKER_BUILDKIT=1 docker build --target builder --tag bsr:test .
	docker run --rm bsr:test uv run pytest

docker-clean:
	docker compose down -v
	docker rmi bsr:latest bsr:test 2>/dev/null || true
	docker builder prune -f

docker-size:
	@echo "=== Docker Image Size ==="
	@docker images bsr --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"
	@echo ""
	@echo "=== Layer Analysis ==="
	@docker history bsr:latest --human --format "table {{.Size}}\t{{.CreatedBy}}" | head -15

docker-deploy: docker-build docker-stop docker-run
	@echo "=== Deployment complete ==="
	@echo "Check logs with: make docker-logs"

docker-health:
	@docker compose ps
	@echo ""
	@docker inspect --format='{{json .State.Health}}' bsr-bot 2>/dev/null | python -m json.tool || echo "Container not running or no health check configured"
