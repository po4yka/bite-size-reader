# .docs Source of Truth
- Date: 2025-12-07
- Purpose: Centralize architecture, design, testing, and decisions.
- Latest review: `REVIEWS/review_2025-12-07.md` (consolidates batch/error/url analyses; root analysis files removed).

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
| docs/phase2_schema_changes.md | legacy | migrate into `TD_background_processor.md` or new ADR/TD |
| docs/phase3_performance_improvements.md | legacy | condense into RAG/search TDs + ADR if decisions remain |
| docs/rw_lock_implementation.md | legacy | fold into `TD-redis-cache.md` (concurrency controls) |
| docs/database_improvements_final_summary.md | legacy | align with DB section in `TD_background_processor.md` |
| docs/model_optimization_2025.md | legacy | evaluate vs current RAG/search TDs; migrate or retire |
| docs/server_update_guide.md | legacy | move operational steps into CHECKLISTS/ or README |

Notes:
- New documents must use templates in `.docs/TEMPLATES`.
- If a legacy doc is not yet mirrored, reference it here until a .docs version is created.
- Temporary analyses at repo root have been removed; use `REVIEWS/` for future reviews.
