#!/usr/bin/env bash

# Exit on error, undefined variables, and pipe failures
set -euo pipefail

# =============================================================================
# Configuration
# =============================================================================

readonly SCRIPT_NAME="maintenance"
readonly PYTHON_BIN="${PYTHON_BIN:-python3}"
readonly VENV_BIN="${VENV_BIN:-}"

# Environment flags
readonly FORCE_RELOCK="${FORCE_RELOCK:-0}"
readonly SKIP_SYNC="${SKIP_SYNC:-0}"
readonly RUN_SECURITY="${RUN_SECURITY:-0}"
readonly RUN_TESTS="${RUN_TESTS:-0}"

# Colors for output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly CYAN='\033[0;36m'
readonly NC='\033[0m' # No Color

# =============================================================================
# Helper Functions
# =============================================================================

log_info() {
    echo -e "${BLUE}[${SCRIPT_NAME}]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[${SCRIPT_NAME}]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[${SCRIPT_NAME}]${NC} $1"
}

log_error() {
    echo -e "${RED}[${SCRIPT_NAME}]${NC} $1" >&2
}

log_step() {
    echo -e "${CYAN}[${SCRIPT_NAME}]${NC} $1"
}

check_command() {
    command -v "$1" >/dev/null 2>&1
}

get_git_commit() {
    if git rev-parse --short HEAD 2>/dev/null; then
        return 0
    else
        echo "n/a"
        return 1
    fi
}

get_python_version() {
    if "${PYTHON_BIN}" -V 2>/dev/null; then
        return 0
    else
        echo "not found"
        return 1
    fi
}

# =============================================================================
# Maintenance Functions
# =============================================================================

show_environment_info() {
    log_info "Starting maintenance in cached container"
    log_info "Working directory: $(pwd)"
    log_info "Git commit: $(get_git_commit)"

    # Handle virtual environment
    if [[ -n "${VENV_BIN}" && -x "${VENV_BIN}/python" ]]; then
        log_info "Using virtual environment at ${VENV_BIN}"
        # shellcheck disable=SC1090,SC1091
        source "${VENV_BIN}/bin/activate"
    fi

    log_info "Python version: $(get_python_version)"
}

ensure_uv_available() {
    log_step "[1/7] Ensuring uv package manager is available..."

    if check_command uv; then
        local uv_version
        uv_version=$(uv --version 2>/dev/null || echo "unknown")
        log_info "uv detected: ${uv_version}"
    else
        log_info "Installing uv package manager..."
        if curl -LsSf https://astral.sh/uv/install.sh | sh; then
            export PATH="${HOME}/.local/bin:${PATH}"
            if uv --version >/dev/null 2>&1; then
                log_success "uv installed successfully"
            else
                log_error "uv installation failed - not found on PATH"
                return 1
            fi
        else
            log_error "Failed to download and install uv"
            return 1
        fi
    fi
}

handle_dependency_locks() {
    log_step "[2/7] Checking dependency lockfiles..."

    local relock=0

    # Check if forced relock is requested
    if [[ "${FORCE_RELOCK}" == "1" ]]; then
        log_info "FORCE_RELOCK=1; forcing lockfile recompilation"
        relock=1
    # Check if pyproject.toml is newer than lockfiles
    elif [[ -f "pyproject.toml" ]] && {
        [[ pyproject.toml -nt requirements.txt ]] || [[ pyproject.toml -nt requirements-dev.txt ]]
    }; then
        log_info "pyproject.toml is newer than lockfiles; recompilation needed"
        relock=1
    fi

    if [[ "${relock}" == "1" ]]; then
        log_info "Recompiling lockfiles from pyproject.toml..."

        if [[ ! -f "pyproject.toml" ]]; then
            log_error "pyproject.toml not found"
            return 1
        fi

        if uv pip compile pyproject.toml -o requirements.txt && \
           uv pip compile --extra dev pyproject.toml -o requirements-dev.txt; then
            log_success "Lockfiles recompiled successfully"
        else
            log_error "Failed to recompile lockfiles"
            return 1
        fi
    else
        log_info "Lockfiles appear current; skipping recompilation"
    fi
}

sync_dependencies() {
    log_step "[3/7] Syncing dependencies..."

    if [[ "${SKIP_SYNC}" == "1" ]]; then
        log_warning "SKIP_SYNC=1; skipping dependency synchronization"
        return 0
    fi

    if [[ ! -f "requirements.txt" ]] || [[ ! -f "requirements-dev.txt" ]]; then
        log_error "Required lockfiles not found (requirements.txt, requirements-dev.txt)"
        return 1
    fi

    log_info "Synchronizing dependencies to lockfiles..."
    if uv pip sync requirements.txt requirements-dev.txt; then
        log_success "Dependencies synchronized successfully"
    else
        log_error "Failed to sync dependencies"
        return 1
    fi
}

run_code_quality_checks() {
    log_step "[4/7] Running code quality checks..."

    local ruff_available=false

    if check_command ruff; then
        ruff_available=true
        log_info "Running ruff linting and formatting (best-effort)..."

        # Run linting with fixes
        if ruff check . --fix; then
            log_success "Ruff linting completed successfully"
        else
            log_warning "Ruff linting found issues (non-fatal)"
        fi

        # Run formatting
        if ruff format .; then
            log_success "Ruff formatting completed successfully"
        else
            log_warning "Ruff formatting encountered issues (non-fatal)"
        fi
    else
        log_warning "ruff not available; skipping code quality checks"
    fi

    if [[ "${ruff_available}" == "true" ]]; then
        log_success "Code quality checks completed"
    fi
}

run_security_audit() {
    log_step "[5/7] Security audit..."

    if [[ "${RUN_SECURITY}" != "1" ]]; then
        log_info "RUN_SECURITY not set; skipping security audit"
        return 0
    fi

    if ! check_command pip-audit; then
        log_warning "pip-audit not available; skipping security audit"
        return 0
    fi

    if [[ ! -f "requirements.txt" ]] || [[ ! -f "requirements-dev.txt" ]]; then
        log_warning "Lockfiles not found; skipping security audit"
        return 0
    fi

    log_info "Running pip-audit security scan (requires network)..."
    if pip-audit -r requirements.txt -r requirements-dev.txt --strict; then
        log_success "Security audit passed"
    else
        log_warning "Security audit found issues (non-fatal)"
    fi
}

run_database_migration() {
    log_step "[6/7] Running database migration..."

    log_info "Executing database migration..."

    if "${PYTHON_BIN}" - <<'EOF'
import sys
import os

try:
    from app.config import load_config
    from app.db.database import Database

    cfg = load_config()
    db_path = os.getenv("DB_PATH", cfg.runtime.db_path)

    database = Database(db_path)
    database.migrate()

    print(f"[maint] Database migrated successfully at: {db_path}")

except ImportError as e:
    print(f"[maint] Import error: {e}", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"[maint] Migration error: {e}", file=sys.stderr)
    sys.exit(1)
EOF
    then
        log_success "Database migration completed"
    else
        log_error "Database migration failed"
        return 1
    fi
}

run_tests() {
    log_step "[7/7] Running tests..."

    if [[ "${RUN_TESTS}" != "1" ]]; then
        log_info "RUN_TESTS not set; skipping unit tests"
        return 0
    fi

    if [[ ! -d "tests" ]]; then
        log_warning "Tests directory not found; skipping unit tests"
        return 0
    fi

    log_info "Running unit tests..."
    if "${PYTHON_BIN}" -m unittest discover -s tests -p "test_*.py" -v; then
        log_success "Unit tests passed"
    else
        log_warning "Some unit tests failed (non-fatal)"
    fi
}

show_completion_summary() {
    cat <<EOF

🎉 Maintenance Complete!

Summary of operations:
- Environment verified
- uv package manager ensured
- Dependencies ${SKIP_SYNC:+sync skipped}${SKIP_SYNC:-synchronized}
- Code quality checks run
- Security audit ${RUN_SECURITY:+completed}${RUN_SECURITY:-skipped}
- Database migration completed
- Tests ${RUN_TESTS:+executed}${RUN_TESTS:-skipped}

Environment flags used:
- FORCE_RELOCK=${FORCE_RELOCK}
- SKIP_SYNC=${SKIP_SYNC}
- RUN_SECURITY=${RUN_SECURITY}
- RUN_TESTS=${RUN_TESTS}

EOF
}

# =============================================================================
# Main Execution
# =============================================================================

main() {
    local exit_code=0

    show_environment_info

    # Run maintenance steps
    ensure_uv_available || exit_code=1
    handle_dependency_locks || exit_code=1
    sync_dependencies || exit_code=1
    run_code_quality_checks || true  # Non-fatal
    run_security_audit || true       # Non-fatal
    run_database_migration || exit_code=1
    run_tests || true                 # Non-fatal

    if [[ ${exit_code} -eq 0 ]]; then
        show_completion_summary
        log_success "Maintenance completed successfully!"
    else
        log_error "Maintenance completed with errors!"
    fi

    return ${exit_code}
}

# Run main function if script is executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
