"""Tests for the token-family rotation/revocation policy.

The policy module encodes the security guarantee from the task spec:

  * Each refresh issues a new token chained to the prior; the chain
    of tokens that descended from the same login event forms a
    "family" (one ``family_id`` shared across rows).
  * Presenting a token that has already been retired (rotated out)
    is replay evidence — the policy returns "revoke entire family"
    so the attacker's session is killed everywhere.
  * Presenting an unknown or expired token returns "reject" without
    cascading.
  * Logout-all is a separate operation that revokes every family
    owned by the user.

This is a pure decision module: the caller (refresh endpoint) reads
the family rows from the DB, asks the policy what to do, and applies
the result. No IO here.
"""

from __future__ import annotations

import datetime as _dt

from app.security.token_family_policy import (
    FamilyDecision,
    FamilyDecisionKind,
    FamilyTokenRecord,
    TokenFamilyPolicy,
)


def _now() -> _dt.datetime:
    return _dt.datetime(2026, 5, 17, 12, 0, 0, tzinfo=_dt.UTC)


def _rec(
    *,
    token_hash: str,
    family_id: str,
    is_revoked: bool = False,
    expires_at: _dt.datetime | None = None,
    parent_token_hash: str | None = None,
) -> FamilyTokenRecord:
    return FamilyTokenRecord(
        token_hash=token_hash,
        family_id=family_id,
        is_revoked=is_revoked,
        expires_at=expires_at or (_now() + _dt.timedelta(days=30)),
        parent_token_hash=parent_token_hash,
    )


class TestFirstFamilyToken:
    def test_first_token_in_family_rotates_cleanly(self) -> None:
        # The presented token is the leaf of the family (no children).
        tok = _rec(token_hash="t1", family_id="fam-1")
        decision = TokenFamilyPolicy.decide(presented_token=tok, family_records=[tok], now=_now())
        assert decision == FamilyDecision(kind=FamilyDecisionKind.ROTATE, family_id="fam-1")


class TestReplayDetection:
    def test_retired_token_reuse_revokes_whole_family(self) -> None:
        # Two tokens in family fam-2: t1 (retired) and t2 (current).
        # Attacker presents the retired t1 -> revoke family.
        t1 = _rec(token_hash="t1", family_id="fam-2", is_revoked=True)
        t2 = _rec(token_hash="t2", family_id="fam-2", parent_token_hash="t1")
        decision = TokenFamilyPolicy.decide(presented_token=t1, family_records=[t1, t2], now=_now())
        assert decision.kind is FamilyDecisionKind.REVOKE_FAMILY
        assert decision.family_id == "fam-2"

    def test_already_revoked_current_leaf_does_not_rotate(self) -> None:
        # A revoked leaf with no descendants should still reject (not rotate).
        tok = _rec(token_hash="t1", family_id="fam-3", is_revoked=True)
        decision = TokenFamilyPolicy.decide(presented_token=tok, family_records=[tok], now=_now())
        assert decision.kind is FamilyDecisionKind.REVOKE_FAMILY


class TestExpiry:
    def test_expired_token_is_rejected_without_cascade(self) -> None:
        tok = _rec(
            token_hash="t1",
            family_id="fam-4",
            expires_at=_now() - _dt.timedelta(hours=1),
        )
        decision = TokenFamilyPolicy.decide(presented_token=tok, family_records=[tok], now=_now())
        assert decision == FamilyDecision(kind=FamilyDecisionKind.REJECT, family_id="fam-4")

    def test_expired_token_in_already_rotated_family_does_not_revoke(self) -> None:
        # User let an old token sit until it expired; their new token is
        # still valid. Don't punish them by revoking the family.
        t1 = _rec(
            token_hash="t1",
            family_id="fam-5",
            is_revoked=True,
            expires_at=_now() - _dt.timedelta(days=1),
        )
        t2 = _rec(
            token_hash="t2",
            family_id="fam-5",
            parent_token_hash="t1",
        )
        # Old token presented past its expiry: REJECT, do not cascade.
        decision = TokenFamilyPolicy.decide(presented_token=t1, family_records=[t1, t2], now=_now())
        assert decision.kind is FamilyDecisionKind.REJECT


class TestConcurrentRefresh:
    def test_rotation_picks_the_youngest_unrevoked_descendant(self) -> None:
        # Edge case: two concurrent refresh attempts from the same client.
        # The policy should treat a refresh whose token is the latest
        # (not retired) as a normal rotation, regardless of siblings.
        t1 = _rec(token_hash="t1", family_id="fam-6", is_revoked=True)
        t2 = _rec(token_hash="t2", family_id="fam-6", parent_token_hash="t1")
        # Present t2 — current leaf, not revoked → rotate.
        decision = TokenFamilyPolicy.decide(presented_token=t2, family_records=[t1, t2], now=_now())
        assert decision.kind is FamilyDecisionKind.ROTATE
        assert decision.family_id == "fam-6"


class TestLogoutAll:
    def test_logout_all_returns_distinct_family_ids(self) -> None:
        records = [
            _rec(token_hash="a", family_id="fam-7"),
            _rec(token_hash="b", family_id="fam-7"),
            _rec(token_hash="c", family_id="fam-8"),
        ]
        families = TokenFamilyPolicy.family_ids_for_user(records)
        assert set(families) == {"fam-7", "fam-8"}

    def test_logout_all_empty_input(self) -> None:
        assert TokenFamilyPolicy.family_ids_for_user([]) == ()
