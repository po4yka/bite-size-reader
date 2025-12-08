"""
Tests for collections management endpoints (direct calls).
"""

import pytest

from app.api.models.requests import (
    CollectionCreateRequest,
    CollectionItemCreateRequest,
    CollectionUpdateRequest,
)
from app.api.routers import collections
from app.db.models import Collection, CollectionItem


@pytest.mark.asyncio
async def test_create_collection(db, user_factory):
    user = user_factory(username="col_user")
    user_context = {"user_id": user.telegram_user_id}

    body = CollectionCreateRequest(name="My Favs", description="Desc")
    response = await collections.create_collection(body=body, user=user_context)

    assert response["success"] is True
    data = response["data"]
    assert data["name"] == "My Favs"
    assert "id" in data


@pytest.mark.asyncio
async def test_get_collections(db, user_factory):
    user = user_factory(username="col_user_list")
    user_context = {"user_id": user.telegram_user_id}

    # Create via DB or router
    await collections.create_collection(CollectionCreateRequest(name="C1"), user=user_context)
    await collections.create_collection(CollectionCreateRequest(name="C2"), user=user_context)

    response = await collections.get_collections(user=user_context)
    data = response["data"]["collections"]
    assert len(data) >= 2
    names = [c["name"] for c in data]
    assert "C1" in names
    assert "C2" in names


@pytest.mark.asyncio
async def test_update_collection(db, user_factory):
    user = user_factory(username="col_user_update")
    user_context = {"user_id": user.telegram_user_id}

    create_resp = await collections.create_collection(
        CollectionCreateRequest(name="Orig"), user=user_context
    )
    cid = create_resp["data"]["id"]

    response = await collections.update_collection(
        collection_id=cid,
        body=CollectionUpdateRequest(name="New", description="NewD"),
        user=user_context,
    )
    assert response["data"]["name"] == "New"
    assert response["data"]["description"] == "NewD"


@pytest.mark.asyncio
async def test_delete_collection(db, user_factory):
    user = user_factory(username="col_user_del")
    user_context = {"user_id": user.telegram_user_id}

    create_resp = await collections.create_collection(
        CollectionCreateRequest(name="ToDel"), user=user_context
    )
    cid = create_resp["data"]["id"]

    await collections.delete_collection(collection_id=cid, user=user_context)

    # Verify deletion
    assert not Collection.select().where(Collection.id == cid).exists()


@pytest.mark.asyncio
async def test_add_remove_item(db, user_factory, summary_factory):
    user = user_factory(username="col_user_item")
    user_context = {"user_id": user.telegram_user_id}

    # Create collection
    create_resp = await collections.create_collection(
        CollectionCreateRequest(name="Items"), user=user_context
    )
    cid = create_resp["data"]["id"]

    # Create summary
    summary = summary_factory(user=user)

    # Add item
    await collections.add_collection_item(
        collection_id=cid,
        body=CollectionItemCreateRequest(summary_id=summary.id),
        user=user_context,
    )

    assert (
        CollectionItem.select()
        .where((CollectionItem.collection_id == cid) & (CollectionItem.summary_id == summary.id))
        .exists()
    )

    # Remove item
    await collections.remove_collection_item(
        collection_id=cid, summary_id=summary.id, user=user_context
    )

    assert (
        not CollectionItem.select()
        .where((CollectionItem.collection_id == cid) & (CollectionItem.summary_id == summary.id))
        .exists()
    )
