from __future__ import annotations

import datetime as dt

import pytest

from app.core.time_utils import UTC
from app.db.models import CollectionCollaborator, CollectionItem, Request, Summary, User
from app.infrastructure.persistence.sqlite.repositories.collection_repository import (
    SqliteCollectionRepositoryAdapter,
)
from tests.integration.helpers import temp_db


@pytest.fixture
def db_and_repo():
    with temp_db() as db:
        yield db, SqliteCollectionRepositoryAdapter(db)


def _create_user(*, telegram_user_id: int, username: str) -> User:
    return User.create(telegram_user_id=telegram_user_id, username=username)


def _create_summary(*, user: User, suffix: str) -> Summary:
    url = f"https://example.com/{suffix}"
    request = Request.create(
        user_id=user.telegram_user_id,
        input_url=url,
        normalized_url=url,
        dedupe_hash=f"hash-{suffix}",
        status="completed",
        type="url",
    )
    return Summary.create(
        request=request.id,
        lang="en",
        json_payload={"summary_250": f"summary-{suffix}"},
    )


@pytest.mark.asyncio
async def test_collection_repository_crud_tree_and_move_operations(db_and_repo) -> None:
    _db, repo = db_and_repo
    owner = _create_user(telegram_user_id=7001, username="owner-collections")

    root_id = await repo.async_create_collection(
        user_id=owner.telegram_user_id,
        name="Root",
        description=None,
        parent_id=None,
        position=1,
    )
    second_root_id = await repo.async_create_collection(
        user_id=owner.telegram_user_id,
        name="Second Root",
        description="second",
        parent_id=None,
        position=2,
    )
    child_id = await repo.async_create_collection(
        user_id=owner.telegram_user_id,
        name="Child",
        description="nested",
        parent_id=root_id,
        position=1,
    )

    listed = await repo.async_list_collections(owner.telegram_user_id, None, limit=10, offset=0)
    assert [item["name"] for item in listed] == ["Root", "Second Root"]

    tree = await repo.async_get_collection_tree(owner.telegram_user_id)
    ids = {item["id"] for item in tree}
    assert {root_id, second_root_id, child_id}.issubset(ids)

    await repo.async_update_collection(child_id, name="Renamed Child", description="updated")
    moved = await repo.async_move_collection(child_id, None, 1)
    assert moved is not None
    assert moved["parent"] is None
    assert moved["position"] == 1

    await repo.async_reorder_collections(
        None,
        [
            {"collection_id": child_id, "position": 1},
            {"collection_id": root_id, "position": 2},
            {"collection_id": second_root_id, "position": 3},
        ],
    )
    renamed = await repo.async_get_collection(child_id)
    assert renamed is not None
    assert renamed["name"] == "Renamed Child"
    assert renamed["item_count"] == 0

    await repo.async_soft_delete_collection(second_root_id)
    assert await repo.async_get_collection(second_root_id) is None
    deleted = await repo.async_get_collection(second_root_id, include_deleted=True)
    assert deleted is not None
    assert deleted["is_deleted"] is True


@pytest.mark.asyncio
async def test_collection_repository_item_and_smart_collection_operations(db_and_repo) -> None:
    _db, repo = db_and_repo
    owner = _create_user(telegram_user_id=7002, username="owner-items")
    source_id = await repo.async_create_collection(
        user_id=owner.telegram_user_id,
        name="Source",
        description=None,
        parent_id=None,
        position=1,
    )
    target_id = await repo.async_create_collection(
        user_id=owner.telegram_user_id,
        name="Target",
        description=None,
        parent_id=None,
        position=2,
    )
    smart_id = await repo.async_create_collection(
        user_id=owner.telegram_user_id,
        name="Smart",
        description=None,
        parent_id=None,
        position=3,
        collection_type="smart",
        query_conditions_json=[{"field": "topic", "op": "contains", "value": "ai"}],
        query_match_mode="all",
    )
    summary_a = _create_summary(user=owner, suffix="a")
    summary_b = _create_summary(user=owner, suffix="b")

    assert await repo.async_add_item(source_id, summary_a.id, 1) is True
    assert await repo.async_add_item(source_id, summary_b.id, 2) is True
    assert await repo.async_get_item_count(source_id) == 2

    await repo.async_reorder_items(
        source_id,
        [
            {"summary_id": summary_b.id, "position": 1},
            {"summary_id": summary_a.id, "position": 2},
        ],
    )
    moved = await repo.async_move_items(source_id, target_id, [summary_a.id], 1)
    assert moved == [summary_a.id]

    inserted = await repo.async_bulk_set_items(target_id, [summary_b.id, summary_a.id])
    assert inserted == 2

    target_items = await repo.async_list_items(target_id, limit=10, offset=0)
    assert len(target_items) == 2

    await repo.async_remove_item(target_id, summary_b.id)
    assert await repo.async_get_item_count(target_id) == 1

    smart_collections = await repo.async_list_smart_collections_for_user(owner.telegram_user_id)
    assert [item["id"] for item in smart_collections] == [smart_id]

    rows = await repo.async_list_user_summaries_with_request(owner.telegram_user_id)
    request_ids = {row["request"]["id"] for row in rows}
    assert len(rows) == 2
    assert request_ids == {summary_a.request_id, summary_b.request_id}


@pytest.mark.asyncio
async def test_collection_repository_acl_and_invite_flow(db_and_repo) -> None:
    _db, repo = db_and_repo
    owner = _create_user(telegram_user_id=7003, username="owner-acl")
    collaborator = _create_user(telegram_user_id=7004, username="collaborator-acl")
    invitee = _create_user(telegram_user_id=7005, username="invitee-acl")
    collection_id = await repo.async_create_collection(
        user_id=owner.telegram_user_id,
        name="Shared",
        description=None,
        parent_id=None,
        position=1,
    )

    assert await repo.async_get_role(collection_id, owner.telegram_user_id) == "owner"
    assert await repo.async_get_role(collection_id, collaborator.telegram_user_id) is None

    await repo.async_add_collaborator(
        collection_id,
        collaborator.telegram_user_id,
        "editor",
        invited_by=owner.telegram_user_id,
    )
    assert await repo.async_get_role(collection_id, collaborator.telegram_user_id) == "editor"

    collaborators = await repo.async_list_collaborators(collection_id)
    assert any(entry["user"] == collaborator.telegram_user_id for entry in collaborators)
    assert (
        CollectionCollaborator.select()
        .where(
            (CollectionCollaborator.collection_id == collection_id)
            & (CollectionCollaborator.user_id == collaborator.telegram_user_id)
        )
        .exists()
    )

    owner_info = await repo.async_get_owner_info(collection_id)
    assert owner_info is not None
    assert owner_info["owner_user"]["telegram_user_id"] == owner.telegram_user_id

    await repo.async_remove_collaborator(collection_id, collaborator.telegram_user_id)
    assert await repo.async_get_role(collection_id, collaborator.telegram_user_id) is None

    invite = await repo.async_create_invite(
        collection_id,
        "viewer",
        dt.datetime.now(UTC) + dt.timedelta(days=1),
    )
    fetched = await repo.async_get_invite_by_token(invite["token"])
    assert fetched is not None
    await repo.async_update_invite(fetched["id"], role="editor")

    accepted = await repo.async_accept_invite(invite["token"], invitee.telegram_user_id)
    assert accepted == {
        "collection_id": collection_id,
        "role": "editor",
        "status": "accepted",
    }
    assert await repo.async_get_role(collection_id, invitee.telegram_user_id) == "editor"
    assert CollectionItem.select().where(CollectionItem.collection_id == collection_id).count() == 0
