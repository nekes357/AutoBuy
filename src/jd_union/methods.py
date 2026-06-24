"""JD Union (京东联盟) API method names.

Base URL: https://router.jd.com/api
Auth: MD5-signed query params (JOS style), no OAuth session for goods queries.
"""

GOODS_QUERY = "jd.union.open.goods.query"
GOODS_BIGFIELD_QUERY = "jd.union.open.goods.bigfield.query"

# bigfield.query "fields" enum values: which large fields to include in detail.
BIGFIELD_WARE_QD = "wareQD"      # product QA descriptions
BIGFIELD_WDESC = "wdesc"          # full HTML description
BIGFIELD_VIDEO = "videoInfo"      # short videos for the SKU

DEFAULT_BIGFIELDS = f"{BIGFIELD_WARE_QD},{BIGFIELD_WDESC}"
