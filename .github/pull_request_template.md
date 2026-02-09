# Pull Request

## Description

<!-- Briefly describe what this PR does and why -->

## Type of Change

<!-- Mark the relevant option with an [x] -->

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update
- [ ] Refactoring (no functional changes, no API changes)
- [ ] Build/CI changes
- [ ] Performance improvement
- [ ] Test coverage improvement

## Related Issues

<!-- Link to related issues, if any -->
<!-- Example: Fixes #123, Closes #456 -->

## Changes Made

<!-- Provide a detailed list of changes -->

-
-
-

## Testing

<!-- Describe the testing you've done -->

- [ ] Unit tests pass locally (`pytest tests/`)
- [ ] Integration tests pass (if applicable)
- [ ] Linting passes (`make lint`)
- [ ] Type checking passes (`make type`)
- [ ] Formatting is correct (`make format`)

## Documentation

<!-- Documentation checklist - complete if applicable -->

### Code Documentation

- [ ] Added/updated docstrings for new/modified functions
- [ ] Added/updated type hints
- [ ] Added/updated inline comments for complex logic

### User Documentation

**Required for new features or API changes:**

- [ ] Updated README.md (if user-facing changes)
- [ ] Updated SPEC.md (if data model or API contract changes)
- [ ] Updated environment_variables.md (if new env vars added)
- [ ] Added/updated how-to guide in `docs/how-to/` (for new features)
- [ ] Updated relevant reference docs in `docs/reference/`
- [ ] Updated Mobile API spec (if API changes)

**Required for architecture changes:**

- [ ] Created/updated Architecture Decision Record (ADR) in `docs/adr/`
- [ ] Updated architectural diagrams (if applicable)
- [ ] Updated explanation docs in `docs/explanation/` (if design philosophy changes)

**Required for bug fixes:**

- [ ] Updated TROUBLESHOOTING.md (if fix addresses common issue)
- [ ] Updated FAQ.md (if fix answers frequent question)

**Changelog:**

- [ ] Added entry to CHANGELOG.md under `[Unreleased]` section
  - [ ] Categorized correctly (Added, Changed, Deprecated, Removed, Fixed, Security)
  - [ ] Included contributor acknowledgment (if applicable)

## Database Changes

<!-- Complete if this PR modifies the database schema -->

- [ ] Migration script created in `app/cli/migrations/`
- [ ] Migration tested with existing data
- [ ] Rollback procedure documented
- [ ] Data model diagram updated (if applicable)
- [ ] Updated docs/reference/data-model.md

## Breaking Changes

<!-- If this PR introduces breaking changes, describe them and the migration path -->

**Breaking changes:**

-

**Migration path:**

-

## Deployment Notes

<!-- Any special instructions for deploying this change? -->

-

## Screenshots/Videos

<!-- If applicable, add screenshots or videos to help explain your changes -->

## Checklist

- [ ] My code follows the project's code style guidelines
- [ ] I have performed a self-review of my code
- [ ] I have commented my code, particularly in hard-to-understand areas
- [ ] I have made corresponding changes to the documentation
- [ ] My changes generate no new warnings or errors
- [ ] I have added tests that prove my fix is effective or that my feature works
- [ ] New and existing unit tests pass locally with my changes
- [ ] Any dependent changes have been merged and published in downstream modules
- [ ] I have checked my code and corrected any misspellings

## Additional Notes

<!-- Any additional information that reviewers should know -->
