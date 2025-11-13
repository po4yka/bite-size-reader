.PHONY: format lint type test all setup-dev venv pre-commit-install pre-commit-run check-lock

format:
	ruff format .
	isort .

lint:
	ruff check .

type:
	mypy app tests

test:
	python -m unittest discover -s tests -p "test_*.py" -v

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

# ==============================================================================
# Docker targets
# ==============================================================================

.PHONY: docker-build docker-build-no-cache docker-run docker-stop docker-restart
.PHONY: docker-logs docker-shell docker-test docker-clean docker-size docker-deploy

docker-build:
	DOCKER_BUILDKIT=1 docker build --tag bsr:latest --progress=plain .

docker-build-no-cache:
	DOCKER_BUILDKIT=1 docker build --no-cache --tag bsr:latest --progress=plain .

docker-run:
	docker-compose up -d

docker-stop:
	docker-compose down

docker-restart: docker-stop docker-run

docker-logs:
	docker-compose logs -f bsr

docker-logs-tail:
	docker-compose logs --tail=100 -f bsr

docker-shell:
	docker-compose exec bsr sh

docker-shell-root:
	docker-compose exec -u root bsr sh

docker-test:
	DOCKER_BUILDKIT=1 docker build --target builder --tag bsr:test .
	docker run --rm bsr:test uv run pytest

docker-clean:
	docker-compose down -v
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
	@docker-compose ps
	@echo ""
	@docker inspect --format='{{json .State.Health}}' bsr-bot 2>/dev/null | python -m json.tool || echo "Container not running or no health check configured"
