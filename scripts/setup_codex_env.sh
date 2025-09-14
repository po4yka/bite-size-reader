#!/usr/bin/env bash

# Exit on error, undefined variables, and pipe failures
set -euo pipefail

# =============================================================================
# Configuration
# =============================================================================

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-.venv}"

# Colors for output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m' # No Color

# =============================================================================
# Helper Functions
# =============================================================================

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

check_command() {
    if command -v "$1" >/dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# =============================================================================
# Main Setup Functions
# =============================================================================

setup_virtualenv() {
    log_info "[1/7] Creating virtual environment at ${VENV_DIR}..."

    # Check Python version
    if ! "${PYTHON_BIN}" --version; then
        log_error "Python binary '${PYTHON_BIN}' not found or not working"
        exit 1
    fi

    # Create virtual environment
    "${PYTHON_BIN}" -m venv "${VENV_DIR}"

    # Activate virtual environment
    # shellcheck disable=SC1090,SC1091
    source "${VENV_DIR}/bin/activate"

    log_success "Virtual environment created and activated"
}

upgrade_pip_tools() {
    log_info "[2/7] Upgrading pip tooling..."
    pip install --upgrade pip wheel setuptools
    log_success "Pip tooling upgraded"
}

setup_uv() {
    log_info "[3/7] Setting up uv and compiling dependencies..."

    if check_command uv; then
        log_info "uv already installed"
    else
        log_info "Installing uv..."
        if ! curl -LsSf https://astral.sh/uv/install.sh | sh; then
            log_error "Failed to install uv"
            exit 1
        fi
        export PATH="${HOME}/.local/bin:${PATH}"
    fi

    # Verify uv installation
    if ! uv --version >/dev/null 2>&1; then
        log_error "uv not found on PATH after installation"
        exit 1
    fi

    # Compile requirements
    log_info "Compiling requirements..."
    uv pip compile pyproject.toml -o requirements.txt
    uv pip compile --extra dev pyproject.toml -o requirements-dev.txt

    log_success "Dependencies compiled"
}

install_dependencies() {
    log_info "[4/7] Installing project dependencies..."

    if [[ ! -f "requirements.txt" ]] || [[ ! -f "requirements-dev.txt" ]]; then
        log_error "Requirements files not found. Run dependency compilation first."
        exit 1
    fi

    pip install -r requirements.txt -r requirements-dev.txt
    log_success "Dependencies installed"
}

setup_precommit() {
    log_info "[5/7] Installing pre-commit hooks..."

    if check_command pre-commit; then
        pre-commit install
        log_success "Pre-commit hooks installed"
    else
        log_warning "pre-commit not found, skipping hook installation"
    fi
}

setup_env_file() {
    log_info "[6/7] Preparing environment file..."

    if [[ ! -f ".env" ]]; then
        if [[ -f ".env.example" ]]; then
            cp .env.example .env
            log_success "Created .env from .env.example"
            log_warning "Please fill in required secrets in .env file"
        else
            log_warning ".env.example not found, skipping .env creation"
        fi
    else
        log_info ".env already exists, skipping"
    fi
}

run_verification() {
    log_info "[7/7] Running verification tasks..."

    # Run tests
    if [[ -d "tests" ]]; then
        log_info "Running tests..."
        if python -m unittest discover -s tests -p "test_*.py" -v; then
            log_success "Tests passed"
        else
            log_warning "Some tests failed"
        fi
    else
        log_info "No tests directory found, skipping tests"
    fi

    # Code formatting and linting
    if check_command ruff; then
        log_info "Running ruff..."
        ruff check . --fix || log_warning "Ruff found issues"
    fi

    if check_command isort; then
        log_info "Running isort..."
        isort . --profile black || log_warning "isort found issues"
    fi

    if check_command black; then
        log_info "Running black..."
        black . || log_warning "black found issues"
    fi

    log_success "Verification complete"
}

show_next_steps() {
    cat <<'EOF'

Setup Complete!

Next steps:
1. Review and update .env file with your secrets
2. Run your application or tests
3. Start developing!

Useful commands:
- Activate venv: source .venv/bin/activate
- Run tests: python -m unittest discover
- Format code: black . && isort . --profile black
- Lint code: ruff check .

EOF
}

# =============================================================================
# Main Execution
# =============================================================================

main() {
    log_info "Starting project setup..."

    setup_virtualenv
    upgrade_pip_tools
    setup_uv
    install_dependencies
    setup_precommit
    setup_env_file
    run_verification

    show_next_steps
    log_success "Project setup completed successfully!"
}

# Run main function if script is executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
