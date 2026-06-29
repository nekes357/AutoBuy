"""Tests for Taobao/Tmall URL parsing."""

from __future__ import annotations

from src.tmall.links import extract_item_id, extract_shop_ref, parse_ref


def test_extract_item_id():
    url = "https://item.taobao.com/item.htm?_u=q207&id=612286553782&spm=a1z09"
    assert extract_item_id(url) == "612286553782"
    assert extract_item_id("https://detail.tmall.com/item.htm?id=55&x=1") == "55"
    assert extract_item_id("https://shop.taobao.com") is None
    assert extract_item_id(None) is None


def test_extract_shop_ref_numeric_subdomain():
    nick, shop_id = extract_shop_ref("https://shop123456.taobao.com")
    assert nick is None
    assert shop_id == "123456"


def test_extract_shop_ref_custom_subdomain():
    nick, shop_id = extract_shop_ref("https://mybrand.tmall.com/index.htm")
    assert nick == "mybrand"
    assert shop_id is None

    nick, _ = extract_shop_ref("https://cool-shop.world.taobao.com")
    assert nick == "cool-shop"


def test_extract_shop_ref_view_shop():
    nick, shop_id = extract_shop_ref(
        "https://store.taobao.com/shop/view_shop.htm?user_number_id=998877"
    )
    assert nick is None
    assert shop_id == "998877"


def test_extract_shop_ref_ignores_item_host():
    # An item host is not a shop nick.
    nick, shop_id = extract_shop_ref("https://item.taobao.com/item.htm?id=123")
    assert nick is None
    assert shop_id is None


def test_parse_ref_combines():
    ref = parse_ref("https://item.taobao.com/item.htm?id=612286553782")
    assert ref.item_id == "612286553782"
    assert ref.shop_nick is None
