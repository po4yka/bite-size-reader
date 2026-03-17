"""Service for expanding search queries with synonyms and related terms.

Backward-compat re-export -- real implementation lives in
app.infrastructure.search.query_expansion_service.
"""

from app.infrastructure.search.query_expansion_service import (
    SYNONYM_MAP,
    ExpandedQuery,
    QueryExpansionService,
)

__all__ = [
    "SYNONYM_MAP",
    "ExpandedQuery",
    "QueryExpansionService",
]
