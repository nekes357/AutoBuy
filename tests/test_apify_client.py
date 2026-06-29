"""Tests for the Apify Taobao client."""

from __future__ import annotations

import httpx
import pytest
import respx

from src.tmall.apify_client import APIFY_API, ApifyTaobaoClient

ACTOR = "epctex/taobao-scraper"
TOKEN = "test-apify-token"


def _settings():
    from src.config import Settings

    return Settings(
        tmall_mode="apify",
        apify_api_token=TOKEN,
        apify_taobao_actor=ACTOR,
    )


def _actor_url():
    return f"{APIFY_API}/acts/{ACTOR}/run-sync-get-dataset-items"


ITEM_PAYLOAD = {
    "id": "612286553782",
    "title": "Зарядный кабель USB-C",
    "sellerNick": "real_taobao_shop",
    "price": "39.90",
    "imageUrl": "https://img.alicdn.com/bao/uploaded/1.jpg",
    "url": "https://item.taobao.com/item.htm?id=612286553782",
    "stock": 150,
    "categoryId": "50012345",
}

SHOP_ITEMS = [
    {
        "id": "100001",
        "title": "Товар 1",
        "sellerNick": "shop_nick",
        "price": "10.00",
        "stock": 50,
    },
    {
        "id": "100002",
        "title": "Товар 2",
        "sellerNick": "shop_nick",
        "price": "20.00",
        "stock": 30,
    },
    {
        "id": "100003",
        "title": "Товар 3",
        "shopName": "shop_nick",
        "price": "30.00",
        "quantity": 10,
    },
]


@pytest.mark.asyncio
async def test_get_item_maps_fields():
    with respx.mock:
        respx.post(_actor_url()).respond(200, json=[ITEM_PAYLOAD])
        async with httpx.AsyncClient() as http:
            client = ApifyTaobaoClient(_settings(), http)
            env = await client.get_item("612286553782")

    item = env.item()
    assert item is not None
    assert str(item.num_iid) == "612286553782"
    assert item.nick == "real_taobao_shop"
    assert item.price == "39.90"
    assert item.pic_url == "https://img.alicdn.com/bao/uploaded/1.jpg"
    assert item.num == 150


@pytest.mark.asyncio
async def test_get_item_empty_result():
    with respx.mock:
        respx.post(_actor_url()).respond(200, json=[])
        async with httpx.AsyncClient() as http:
            client = ApifyTaobaoClient(_settings(), http)
            env = await client.get_item("999999")

    assert env.item() is None


@pytest.mark.asyncio
async def test_get_shop_items_pagination():
    with respx.mock:
        respx.post(_actor_url()).respond(200, json=SHOP_ITEMS)
        async with httpx.AsyncClient() as http:
            client = ApifyTaobaoClient(_settings(), http)

            env1 = await client.get_shop_items("shop_nick", page_no=1, page_size=2)
            items1 = env1.items()
            assert len(items1) == 2
            assert env1.total_results() == 3

            env2 = await client.get_shop_items("shop_nick", page_no=2, page_size=2)
            items2 = env2.items()
            assert len(items2) == 1

            env3 = await client.get_shop_items("shop_nick", page_no=3, page_size=2)
            assert env3.items() == []


@pytest.mark.asyncio
async def test_get_shop_items_caches_actor_call():
    """Actor is called only once; subsequent pages are served from cache."""
    call_count = 0

    def side_effect(request):
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json=SHOP_ITEMS)

    with respx.mock:
        respx.post(_actor_url()).mock(side_effect=side_effect)
        async with httpx.AsyncClient() as http:
            client = ApifyTaobaoClient(_settings(), http)
            await client.get_shop_items("shop_nick", page_no=1)
            await client.get_shop_items("shop_nick", page_no=2)

    assert call_count == 1


@pytest.mark.asyncio
async def test_map_item_alternative_field_names():
    """Fields like shopName/quantity/itemId are mapped correctly."""
    raw = {
        "itemId": "777",
        "title": "Alt fields",
        "shopName": "alt_seller",
        "price": 55,
        "mainPic": "https://pic.example/a.jpg",
        "quantity": 42,
    }
    mapped = ApifyTaobaoClient._map_item(raw)
    assert mapped["num_iid"] == "777"
    assert mapped["nick"] == "alt_seller"
    assert mapped["pic_url"] == "https://pic.example/a.jpg"
    assert mapped["num"] == 42


@pytest.mark.asyncio
async def test_get_shop_returns_minimal_envelope():
    async with httpx.AsyncClient() as http:
        client = ApifyTaobaoClient(_settings(), http)
        env = await client.get_shop("some_nick")
    shop = env.shop()
    assert shop is not None
    assert shop.nick == "some_nick"
