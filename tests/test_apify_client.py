"""Tests for the Apify Taobao client (zen-studio/taobao-seller-products-scraper)."""

from __future__ import annotations

import httpx
import pytest
import respx

from src.tmall.apify_client import APIFY_API, ApifyTaobaoClient

ACTOR = "zen-studio/taobao-seller-products-scraper"
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
    "itemId": "612286553782",
    "title": "Зарядный кабель USB-C",
    "shopName": "real_taobao_shop",
    "shopId": "442584533",
    "price": 49.90,
    "discountPrice": 39.90,
    "mainPictureUrl": "https://img.alicdn.com/bao/uploaded/1.jpg",
    "url": "https://item.taobao.com/item.htm?id=612286553782",
    "soldCount30Day": 150,
    "categoryId": "50012345",
}

SHOP_ITEMS = [
    {
        "itemId": "100001",
        "title": "Товар 1",
        "shopName": "shop_nick",
        "shopId": "778899",
        "price": 10.00,
        "mainPictureUrl": "https://img.example/1.jpg",
        "url": "https://item.taobao.com/item.htm?id=100001",
    },
    {
        "itemId": "100002",
        "title": "Товар 2",
        "shopName": "shop_nick",
        "shopId": "778899",
        "price": 20.00,
        "discountPrice": 15.00,
        "mainPictureUrl": "https://img.example/2.jpg",
        "url": "https://item.taobao.com/item.htm?id=100002",
    },
    {
        "itemId": "100003",
        "titleOriginal": "Товар 3",
        "shopName": "shop_nick",
        "shopId": "778899",
        "price": 30.00,
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
    assert item.price == "39.9"  # discountPrice preferred
    assert item.pic_url == "https://img.alicdn.com/bao/uploaded/1.jpg"


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
async def test_map_item_prefers_discount_price():
    raw = {"itemId": "1", "price": 100, "discountPrice": 80, "shopName": "s"}
    mapped = ApifyTaobaoClient._map_item(raw)
    assert mapped["price"] == "80"


@pytest.mark.asyncio
async def test_map_item_falls_back_to_price():
    raw = {"itemId": "2", "price": 50, "shopName": "s"}
    mapped = ApifyTaobaoClient._map_item(raw)
    assert mapped["price"] == "50"


@pytest.mark.asyncio
async def test_map_item_zen_studio_fields():
    """Fields from zen-studio actor output are mapped correctly."""
    raw = {
        "itemId": "777",
        "title": "Zen item",
        "shopName": "zen_seller",
        "shopId": "12345",
        "price": 55,
        "mainPictureUrl": "https://pic.example/a.jpg",
        "url": "https://item.taobao.com/item.htm?id=777",
        "categoryId": "9999",
    }
    mapped = ApifyTaobaoClient._map_item(raw)
    assert mapped["num_iid"] == "777"
    assert mapped["nick"] == "zen_seller"
    assert mapped["pic_url"] == "https://pic.example/a.jpg"
    assert mapped["detail_url"] == "https://item.taobao.com/item.htm?id=777"
    assert mapped["cid"] == "9999"


@pytest.mark.asyncio
async def test_get_shop_returns_info_from_cache():
    with respx.mock:
        respx.post(_actor_url()).respond(200, json=SHOP_ITEMS)
        async with httpx.AsyncClient() as http:
            client = ApifyTaobaoClient(_settings(), http)
            await client.get_shop_items("shop_nick", page_no=1)
            env = await client.get_shop("shop_nick")

    shop = env.shop()
    assert shop is not None
    assert shop.nick == "shop_nick"
    assert shop.title == "shop_nick"
    assert str(shop.sid) == "778899"


@pytest.mark.asyncio
async def test_get_shop_without_cache_returns_minimal():
    async with httpx.AsyncClient() as http:
        client = ApifyTaobaoClient(_settings(), http)
        env = await client.get_shop("some_nick")
    shop = env.shop()
    assert shop is not None
    assert shop.nick == "some_nick"
