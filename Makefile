.PHONY: format lint type test test-unit test-integration test-all all setup-dev venv pre-commit-install pre-commit-run check-lock check-openapi check-openapi-validate check-file-loc check-layout clean-generated

COMPOSE_FILE := ops/docker/docker-compose.yml
DOCKERFILE_BOT := ops/docker/Dockerfile
DOCKERFILE_API := ops/docker/Dockerfile.api

format:
	ruff format .
	isort .

lint:
	ruff check .
	python tools/scripts/check_file_size.py --max-loc 1500 --baseline tools/scripts/file_size_baseline.json

check-file-loc:
	python tools/scripts/check_file_size.py --max-loc 1500 --baseline tools/scripts/file_size_baseline.json

type:
	uv run --frozen mypy app tests

test:
	pytest tests/ -v

test-unit:
	pytest tests/ -m "not slow and not integration" -v

test-integration:
	pytest tests/ -m "integration" -v

test-all:
	pytest tests/ -v --cov=app --cov-report=term-missing

test-fast:
	pytest tests/ -m "not slow and not integration" -v -x

all: format lint type test

setup-dev:
	uv sync --all-extras --dev
	pre-commit install

venv:
	bash tools/scripts/create_venv.sh

check-layout:
	python tools/scripts/check_root_hygiene.py

clean-generated:
	rm -rf htmlcov
	rm -f .coverage coverage.json coverage.xml debug_fav.log error.log traceback.log
	rm -rf clients/web/coverage clients/web/test-results clients/web/playwright-report
	find clients/web -name '*.tsbuildinfo' -delete
	rm -rf frontend

.PHONY: pre-commit-install
pre-commit-install:
	pre-commit install --install-hooks
	pre-commit autoupdate || true

.PHONY: pre-commit-run
pre-commit-run:
	pre-commit run --all-files

.PHONY: lock-uv
lock-uv:
	uv lock
	uv export --no-dev --format requirements-txt -p 3.13 -o requirements.txt
	uv export --only-group dev --no-hashes --format requirements-txt -p 3.13 -o requirements-dev.txt

check-lock:
	uv lock
	uv export --no-dev --format requirements-txt -p 3.13 -o requirements.txt
	uv export --only-group dev --no-hashes --format requirements-txt -p 3.13 -o requirements-dev.txt
	@git diff --exit-code uv.lock requirements.txt requirements-dev.txt || (echo "Lockfiles are out of date. Run 'make lock-uv' and commit changes." && exit 1)

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
	DOCKER_BUILDKIT=1 docker build -f $(DOCKERFILE_BOT) --tag ratatoskr:latest --progress=plain .

docker-build-no-cache:
	DOCKER_BUILDKIT=1 docker build -f $(DOCKERFILE_BOT) --no-cache --tag ratatoskr:latest --progress=plain .

docker-build-mobile-api:
	DOCKER_BUILDKIT=1 docker compose -f $(COMPOSE_FILE) build mobile-api

docker-build-mobile-api-no-cache:
	DOCKER_BUILDKIT=1 docker compose -f $(COMPOSE_FILE) build --no-cache mobile-api

docker-run:
	docker compose -f $(COMPOSE_FILE) up -d

docker-stop:
	docker compose -f $(COMPOSE_FILE) down

docker-restart: docker-stop docker-run

docker-logs:
	docker compose -f $(COMPOSE_FILE) logs -f ratatoskr

docker-logs-tail:
	docker compose -f $(COMPOSE_FILE) logs --tail=100 -f ratatoskr

docker-logs-mobile-api:
	docker compose -f $(COMPOSE_FILE) logs -f mobile-api

docker-shell:
	docker compose -f $(COMPOSE_FILE) exec ratatoskr sh

docker-shell-root:
	docker compose -f $(COMPOSE_FILE) exec -u root ratatoskr sh

docker-shell-mobile-api:
	docker compose -f $(COMPOSE_FILE) exec mobile-api sh

docker-restart-mobile-api:
	docker compose -f $(COMPOSE_FILE) up -d mobile-api

docker-rebuild-mobile-api: docker-build-mobile-api docker-restart-mobile-api

docker-test:
	DOCKER_BUILDKIT=1 docker build -f $(DOCKERFILE_BOT) --target builder --tag ratatoskr:test .
	docker run --rm ratatoskr:test uv run pytest

docker-clean:
	docker compose -f $(COMPOSE_FILE) down -v
	docker rmi ratatoskr:latest ratatoskr:test 2>/dev/null || true
	docker builder prune -f

docker-size:
	@echo "=== Docker Image Size ==="
	@docker images ratatoskr --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"
	@echo ""
	@echo "=== Layer Analysis ==="
	@docker history ratatoskr:latest --human --format "table {{.Size}}\t{{.CreatedBy}}" | head -15

docker-deploy: docker-build docker-stop docker-run
	@echo "=== Deployment complete ==="
	@echo "Check logs with: make docker-logs"

docker-health:
	@docker compose -f $(COMPOSE_FILE) ps
	@echo ""
	@docker inspect --format='{{json .State.Health}}' ratatoskr-bot 2>/dev/null | python -m json.tool || echo "Container not running or no health check configured"
