# .docs Source of Truth
- Date: 2025-12-06
- Purpose: Centralize architecture, design, testing, and decisions.

## Structure
- ADR/: Architecture decision records.
- CHECKLISTS/: Operational and review checklists.
- PROPOSALS/: High-level proposals.
- REQUIREMENTS/: Product and system requirements.
- REVIEWS/: Review reports.
- TECH_DESIGNS/: Technical designs.
- TESTING/: Test plans and execution notes.
- TEMPLATES/: Standard templates for new docs.

## Migration Mapping (docs/ → .docs/)
| Legacy doc | Status | Target in .docs |
| --- | --- | --- |
| docs/MOBILE_API_SPEC.md | in-use | TECH_DESIGNS/TD_mobile_api_improvements.md |
| docs/MOBILE_API_IMPROVEMENTS.md | in-use | TECH_DESIGNS/TD_mobile_api_improvements.md |
| docs/multi_agent_architecture.md | in-use | TECH_DESIGNS/TD_background_processor.md (references) |
| docs/HEXAGONAL_ARCHITECTURE_QUICKSTART.md | in-use | TECH_DESIGNS/TD_background_processor.md (references) |
| docs/SOLID_IMPROVEMENTS.md | in-use | TECH_DESIGNS/TD_response_contracts.md (references) |

Notes:
- New documents must use templates in `.docs/TEMPLATES`.
- If a legacy doc is not yet mirrored, reference it here until a .docs version is created.
