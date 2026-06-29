"""Parse Taobao/Tmall URLs into the bits we can act on.

Two things we extract:
  * item id   — from item.taobao.com / detail.tmall.com item pages
  * shop ref  — a seller nickname or numeric shop id, from shop URLs

A row in the input file may carry either an item link (we resolve its seller
later via item.get) or a direct shop link (we use the nick straight away).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

# item.taobao.com/item.htm?id=612286553782 / detail.tmall.com/item.htm?id=...
_ITEM_ID_RE = re.compile(r"[?&]id=(\d+)")

# Shop subdomains: shop123456.taobao.com  (numeric id baked into host)
_SHOP_HOST_ID_RE = re.compile(r"shop(\d+)\.(?:taobao|tmall)\.com", re.IGNORECASE)

# Custom-named shop subdomains: myshop.taobao.com / brand.tmall.com / x.world.taobao.com
_SHOP_HOST_NICK_RE = re.compile(
    r"https?://([a-z0-9][a-z0-9\-]*)\.(?:world\.)?(?:taobao|tmall)\.com",
    re.IGNORECASE,
)

# Hosts that are item/listing pages, never a shop nickname.
_NON_SHOP_HOSTS = {"item", "detail", "world", "store", "s", "www", "main", "list"}


@dataclass
class TaobaoRef:
    """What a single URL resolved to. Any field may be None."""

    item_id: str | None = None
    shop_nick: str | None = None
    shop_id: str | None = None


def extract_item_id(url: str | None) -> str | None:
    if not url:
        return None
    m = _ITEM_ID_RE.search(url)
    return m.group(1) if m else None


def extract_shop_ref(url: str | None) -> tuple[str | None, str | None]:
    """Return (shop_nick, shop_id) from a shop URL, either may be None."""
    if not url:
        return None, None

    # shop12345.taobao.com -> numeric shop id
    m = _SHOP_HOST_ID_RE.search(url)
    if m:
        return None, m.group(1)

    # store.taobao.com/shop/view_shop.htm?user_number_id=12345
    parsed = urlparse(url if "://" in url else f"https://{url}")
    qs = parse_qs(parsed.query)
    for key in ("user_number_id", "shop_id", "sid"):
        if key in qs and qs[key]:
            return None, qs[key][0]
    if "nick" in qs and qs["nick"]:
        return qs["nick"][0], None

    # brand.tmall.com / myshop.taobao.com -> the subdomain is the nick,
    # unless it's a generic host like item/detail/world/store.
    m = _SHOP_HOST_NICK_RE.match(url if "://" in url else f"https://{url}")
    if m and m.group(1).lower() not in _NON_SHOP_HOSTS:
        return m.group(1), None

    return None, None


def parse_ref(url: str | None) -> TaobaoRef:
    """Best-effort: pull item id and/or shop ref out of one URL."""
    item_id = extract_item_id(url)
    nick, shop_id = extract_shop_ref(url)
    return TaobaoRef(item_id=item_id, shop_nick=nick, shop_id=shop_id)
