"""JD VOP REST endpoints.

Paths confirmed from the open-source PHP wrapper https://github.com/zmq3821/jd_biz
(see src/request/OrderRequest.php). They are listed here in one place so they
can be patched centrally if the real VOP cabinet exposes slightly different
routes for our app.
"""

from __future__ import annotations

# Authorization (TBD: exact path, will be confirmed when JD credentials are issued).
GET_ACCESS_TOKEN = "/api/getAccessToken"

# Order list / state queries.
CHECK_NEW_ORDER = "/api/checkOrder/checkNewOrder"
CHECK_DELIVERED_ORDER = "/api/checkOrder/checkDlokOrder"
CHECK_REFUSE_ORDER = "/api/checkOrder/checkRefuseOrder"
CHECK_COMPLETE_ORDER = "/api/checkOrder/checkCompleteOrder"

# Order details.
SELECT_JD_ORDER = "/api/order/selectJdOrder"
SELECT_JD_ORDER_BY_THIRD = "/api/order/selectJdOrderIdByThirdOrder"
ORDER_TRACK = "/api/order/orderTrack"
