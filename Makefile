.PHONY: format lint type test all setup-dev venv

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
	pip install -r requirements.txt -r requirements-dev.txt
	pre-commit install

venv:
	bash scripts/create_venv.sh

.PHONY: lock-uv lock-piptools
lock-uv:
	uv pip compile --python-version 3.11 pyproject.toml -o requirements.txt
	uv pip compile --extra dev --python-version 3.11 pyproject.toml -o requirements-dev.txt

lock-piptools:
	pip install pip-tools
	pip-compile pyproject.toml --output-file requirements.txt
	pip-compile pyproject.toml --extra dev --output-file requirements-dev.txt
