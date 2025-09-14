.PHONY: format lint type test all setup-dev venv pre-commit-install check-lock

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
