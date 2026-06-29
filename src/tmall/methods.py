"""Taobao Open Platform API method names.

Base URL: https://gw.api.taobao.com/router/rest
All calls are POST with form-encoded signed params.
"""

ITEM_GET = "taobao.item.get"
ITEMS_LIST_GET = "taobao.items.list.get"
ITEMS_SEARCH = "taobao.items.search"
ITEM_CATS_GET = "taobao.itemcats.get"
SHOP_GET = "taobao.shop.get"

# Fields requested from taobao.shop.get.
DEFAULT_SHOP_FIELDS = "sid,cid,title,nick,desc,pic_path,created,modified"

# Fields to request for each item (covers everything needed for the CDEK feed).
DEFAULT_ITEM_FIELDS = (
    "num_iid,title,nick,type,desc,skus,detail_url,pic_url,"
    "item_imgs,price,num,props_name,cid,modified"
)
