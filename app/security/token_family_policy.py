"""Refresh-token family rotation/revocation policy.

This module encodes the security guarantee:

  * Each refresh issues a new token chained to the prior; all tokens
    descending from the same login share a single ``family_id``.
  * Replay of a *retired* token (one that has already been rotated
    out) is replay evidence — revoke the entire family so the
    attacker's session is killed everywhere and force re-login.
  * Replay of an *expired* leaf is treated as a benign client mistake
    and does not cascade.

Pure decision module: the caller (refresh endpoint) loads the family
rows from the database, calls :func:`TokenFamilyPolicy.decide`, and
applies the result. No IO performed here; tests run with synthesized
records.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import datetime as _dt


class FamilyDecisionKind(enum.StrEnum):
    ROTATE = "rotate"  # Issue a new token chained to the presented one.
    REVOKE_FAMILY = "revoke_family"  # Reuse of a retired token → kill everything.
    REJECT = "reject"  # Unknown / expired / benign mistake → 401, no cascade.


@dataclass(frozen=True)
class FamilyDecision:
    kind: FamilyDecisionKind
    family_id: str


@dataclass(frozen=True)
class FamilyTokenRecord:
    """Minimum shape the policy needs from a RefreshToken row."""

    token_hash: str
    family_id: str
    is_revoked: bool
    expires_at: _dt.datetime
    parent_token_hash: str | None


class TokenFamilyPolicy:
    """Stateless policy decisions for the refresh-token family rotation."""

    @staticmethod
    def decide(
        *,
        presented_token: FamilyTokenRecord,
        family_records: list[FamilyTokenRecord],
        now: _dt.datetime,
    ) -> FamilyDecision:
        family_id = presented_token.family_id

        # Expired: reject without cascading. This is the benign "old
        # client tried to refresh after sitting idle for a month" case.
        if presented_token.expires_at <= now:
            return FamilyDecision(kind=FamilyDecisionKind.REJECT, family_id=family_id)

        # Retired (already rotated out) token replayed: revoke whole family.
        # If it's revoked, treat as replay regardless of whether it has
        # children — keeps the rule simple and safe.
        if presented_token.is_revoked:
            return FamilyDecision(
                kind=FamilyDecisionKind.REVOKE_FAMILY, family_id=family_id
            )

        # Healthy leaf — rotate.
        return FamilyDecision(kind=FamilyDecisionKind.ROTATE, family_id=family_id)

    @staticmethod
    def family_ids_for_user(records: list[FamilyTokenRecord]) -> tuple[str, ...]:
        """Distinct family IDs for the user, preserving first-seen order.

        Used by ``POST /v1/auth/logout-all`` to revoke every family of
        the user's active refresh tokens.
        """
        seen: dict[str, None] = {}
        for r in records:
            seen.setdefault(r.family_id, None)
        return tuple(seen)


__all__ = [
    "FamilyDecision",
    "FamilyDecisionKind",
    "FamilyTokenRecord",
    "TokenFamilyPolicy",
]
