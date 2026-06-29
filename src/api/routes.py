from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from src.api.deps import db_session, require_api_key, settings_dep
from src.config import Settings
from src.jd_union.catalog_check import (
    check_products,
    load_check_from_db,
    load_product_bytes,
    report_to_csv,
)
from src.models import (
    CatalogWatchlistEntry,
    JdOrder,
    JdUnionCatalogCheck,
    JdUnionProduct,
    SyncLog,
    TmallItem,
)
from src.sync import run_sync
from src.sync_taobao_shop import list_shop_items, run_shop_sync
from src.sync_tmall import run_tmall_sync
from src.sync_union import run_union_sync

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/sync/run", dependencies=[Depends(require_api_key)])
async def sync_run(
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    session: Session = Depends(db_session),
    settings: Settings = Depends(settings_dep),
) -> dict[str, Any]:
    until = until or datetime.now(UTC)
    since = since or (until - timedelta(minutes=settings.sync_lookback_minutes))
    sync_log = await run_sync(session, since=since, until=until, settings=settings)
    return {
        "id": sync_log.id,
        "correlation_id": sync_log.correlation_id,
        "fetched": sync_log.fetched_count,
        "new": sync_log.new_count,
        "errors": sync_log.error_count,
        "since": since.isoformat(),
        "until": until.isoformat(),
    }


@router.get("/sync/logs", dependencies=[Depends(require_api_key)])
def sync_logs(limit: int = 20, session: Session = Depends(db_session)) -> list[dict[str, Any]]:
    rows = session.execute(select(SyncLog).order_by(desc(SyncLog.id)).limit(limit)).scalars().all()
    return [
        {
            "id": r.id,
            "correlation_id": r.correlation_id,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "since": r.since.isoformat() if r.since else None,
            "until": r.until.isoformat() if r.until else None,
            "fetched": r.fetched_count,
            "new": r.new_count,
            "errors": r.error_count,
        }
        for r in rows
    ]


@router.get("/orders", dependencies=[Depends(require_api_key)])
def list_orders(
    status: str | None = None,
    limit: int = 50,
    session: Session = Depends(db_session),
) -> list[dict[str, Any]]:
    stmt = select(JdOrder).order_by(desc(JdOrder.fetched_at)).limit(limit)
    if status:
        stmt = stmt.where(JdOrder.status == status)
    rows = session.execute(stmt).scalars().all()
    return [
        {
            "jd_order_id": r.jd_order_id,
            "status": r.status,
            "recipient_name": r.recipient_name,
            "recipient_phone": r.recipient_phone,
            "total_cny": r.total_cny,
            "total_rub": r.total_rub,
            "fetched_at": r.fetched_at.isoformat() if r.fetched_at else None,
        }
        for r in rows
    ]


@router.get("/orders/{jd_order_id}", dependencies=[Depends(require_api_key)])
def order_detail(jd_order_id: str, session: Session = Depends(db_session)) -> dict[str, Any]:
    row = session.get(JdOrder, jd_order_id)
    if row is None:
        raise HTTPException(status_code=404, detail="order not found")
    return {
        "jd_order_id": row.jd_order_id,
        "status": row.status,
        "recipient_name": row.recipient_name,
        "recipient_phone": row.recipient_phone,
        "total_cny": row.total_cny,
        "total_rub": row.total_rub,
        "fetched_at": row.fetched_at.isoformat() if row.fetched_at else None,
        "raw_payload": row.raw_payload,
    }


# ---------------------------------------------------------------------------
# Taobao shop sync — pull a seller's whole catalogue from item/shop links
# ---------------------------------------------------------------------------

@router.post("/shop/sync", dependencies=[Depends(require_api_key)])
async def shop_sync(
    url: str | None = Query(default=None, description="Single Taobao item/shop URL"),
    file: UploadFile | None = File(default=None),
    session: Session = Depends(db_session),
    settings: Settings = Depends(settings_dep),
) -> dict[str, Any]:
    """Sync the full catalogue of every seller referenced by `url` or an
    uploaded file of links (xlsx/csv). Items land in tmall_items tagged with
    seller_nick."""
    urls = [url] if url else None
    file_bytes = await file.read() if file is not None else None
    if not urls and not file_bytes:
        raise HTTPException(status_code=400, detail="provide url= or a file")

    report = await run_shop_sync(
        session,
        file_bytes=file_bytes,
        filename=file.filename if file is not None else None,
        urls=urls,
        settings=settings,
    )
    return report.summary()


@router.get("/shop/items", dependencies=[Depends(require_api_key)])
def shop_items(
    seller: str = Query(..., description="seller_nick to list items for"),
    limit: int = 200,
    session: Session = Depends(db_session),
) -> list[dict[str, Any]]:
    rows = list_shop_items(session, seller, limit=limit)
    return [
        {
            "num_iid": r.num_iid,
            "title": r.title,
            "seller_nick": r.seller_nick,
            "price_cny": r.price_cny,
            "price_rub": r.price_rub,
            "stock": r.stock,
            "pic_url": r.pic_url,
            "detail_url": r.detail_url,
            "category_id": r.category_id,
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Tmall feed endpoints
# ---------------------------------------------------------------------------

@router.post("/feed/sync", dependencies=[Depends(require_api_key)])
async def feed_sync(
    item_ids: str | None = Query(default=None, description="Comma-separated num_iid list"),
    query: str | None = Query(default=None, description="Search keyword"),
    session: Session = Depends(db_session),
    settings: Settings = Depends(settings_dep),
) -> dict[str, Any]:
    """Trigger Tmall catalog sync. Pass item_ids OR query."""
    ids: list[str] | None = [i.strip() for i in item_ids.split(",")] if item_ids else None
    sync_log = await run_tmall_sync(session, item_ids=ids, query=query, settings=settings)
    return {
        "id": sync_log.id,
        "correlation_id": sync_log.correlation_id,
        "fetched": sync_log.fetched_count,
        "new": sync_log.new_count,
        "errors": sync_log.error_count,
    }


@router.get("/feed", dependencies=[Depends(require_api_key)])
def feed_list(
    limit: int = 50,
    category_id: str | None = None,
    session: Session = Depends(db_session),
) -> list[dict[str, Any]]:
    """CDEK product feed — list of Tmall items in normalized format."""
    stmt = select(TmallItem).order_by(desc(TmallItem.updated_at)).limit(limit)
    if category_id:
        stmt = stmt.where(TmallItem.category_id == category_id)
    rows = session.execute(stmt).scalars().all()
    return [_tmall_to_feed(r) for r in rows]


@router.get("/feed/{num_iid}", dependencies=[Depends(require_api_key)])
def feed_item(num_iid: str, session: Session = Depends(db_session)) -> dict[str, Any]:
    row = session.get(TmallItem, num_iid)
    if row is None:
        raise HTTPException(status_code=404, detail="item not found")
    return _tmall_to_feed(row)


def _tmall_to_feed(row: TmallItem) -> dict[str, Any]:
    """Normalize TmallItem to the CDEK feed schema."""
    raw = row.raw_payload or {}
    imgs = raw.get("item_imgs", {})
    img_list = imgs.get("item_img", []) if isinstance(imgs, dict) else []
    if isinstance(img_list, dict):
        img_list = [img_list]
    images = [i.get("url") for i in img_list if isinstance(i, dict) and i.get("url")]

    skus_raw = raw.get("skus", {})
    sku_list = skus_raw.get("sku", []) if isinstance(skus_raw, dict) else []
    if isinstance(sku_list, dict):
        sku_list = [sku_list]

    return {
        "source": "tmall",
        "item_id": row.num_iid,
        "title": row.title,
        "price": row.price_cny,
        "price_rub": row.price_rub,
        "currency": "CNY",
        "main_image": row.pic_url,
        "images": images,
        "url": row.detail_url,
        "category_id": row.category_id,
        "in_stock": (row.stock or 0) > 0,
        "stock_count": row.stock,
        "variants": sku_list,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }



# ---------------------------------------------------------------------------
# Catalog watchlist CRUD
# ---------------------------------------------------------------------------

@router.get("/catalog/watchlist", dependencies=[Depends(require_api_key)])
def watchlist_list(session: Session = Depends(db_session)) -> list[dict[str, Any]]:
    rows = (
        session.execute(select(CatalogWatchlistEntry).order_by(CatalogWatchlistEntry.id))
        .scalars()
        .all()
    )
    return [_entry_to_dict(r) for r in rows]


@router.post("/catalog/watchlist", dependencies=[Depends(require_api_key)])
def watchlist_add(body: dict[str, Any], session: Session = Depends(db_session)) -> dict[str, Any]:
    entry = CatalogWatchlistEntry(
        source=body.get("source", "tmall"),
        category_name=body["category_name"],
        category_id=body.get("category_id"),
        query=body.get("query"),
        enabled=body.get("enabled", True),
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return _entry_to_dict(entry)


@router.patch("/catalog/watchlist/{entry_id}", dependencies=[Depends(require_api_key)])
def watchlist_update(
    entry_id: int, body: dict[str, Any], session: Session = Depends(db_session)
) -> dict[str, Any]:
    entry = session.get(CatalogWatchlistEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="entry not found")
    for field in ("category_name", "category_id", "query", "enabled", "source"):
        if field in body:
            setattr(entry, field, body[field])
    session.commit()
    return _entry_to_dict(entry)


@router.delete("/catalog/watchlist/{entry_id}", dependencies=[Depends(require_api_key)])
def watchlist_delete(entry_id: int, session: Session = Depends(db_session)) -> dict[str, str]:
    entry = session.get(CatalogWatchlistEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="entry not found")
    session.delete(entry)
    session.commit()
    return {"status": "deleted"}


def _entry_to_dict(e: CatalogWatchlistEntry) -> dict[str, Any]:
    return {
        "id": e.id,
        "source": e.source,
        "category_name": e.category_name,
        "category_id": e.category_id,
        "query": e.query,
        "enabled": e.enabled,
        "item_count": e.item_count,
        "last_synced_at": e.last_synced_at.isoformat() if e.last_synced_at else None,
        "last_error": e.last_error,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


# ---------------------------------------------------------------------------
# Status page
# ---------------------------------------------------------------------------

@router.get("/status", response_class=HTMLResponse)
def status_page(session: Session = Depends(db_session)) -> str:
    watchlist = (
        session.execute(select(CatalogWatchlistEntry).order_by(CatalogWatchlistEntry.id))
        .scalars()
        .all()
    )
    recent_syncs = (
        session.execute(select(SyncLog).order_by(desc(SyncLog.id)).limit(10)).scalars().all()
    )
    tmall_total = session.execute(select(func.count()).select_from(TmallItem)).scalar() or 0
    jd_total = session.execute(select(func.count()).select_from(JdOrder)).scalar() or 0
    now = datetime.now(UTC).strftime("%d.%m.%Y %H:%M UTC")

    def _row(e: CatalogWatchlistEntry) -> str:
        status = "⏸ пауза" if not e.enabled else ("🔴 ошибка" if e.last_error else "🟢 ОК")
        synced = e.last_synced_at.strftime("%d.%m %H:%M") if e.last_synced_at else "—"
        return (
            f"<tr>"
            f"<td>{e.category_name}</td>"
            f"<td>{e.source.upper()}</td>"
            f"<td>{e.item_count:,}</td>"
            f"<td>{synced}</td>"
            f"<td>{status}</td>"
            f"<td style='color:#999;font-size:12px'>{e.last_error or ''}</td>"
            f"</tr>"
        )

    def _sync_row(s: SyncLog) -> str:
        ok = s.error_count == 0
        started = s.started_at.strftime("%d.%m %H:%M") if s.started_at else "—"
        return (
            f"<tr>"
            f"<td>{started}</td>"
            f"<td>{s.source.upper()}</td>"
            f"<td>{s.fetched_count}</td>"
            f"<td>{s.new_count}</td>"
            f"<td style='color:{'green' if ok else 'red'}'>{s.error_count}</td>"
            f"</tr>"
        )

    watchlist_rows = "".join(_row(e) for e in watchlist) or (
        "<tr><td colspan='6'>Список пуст — добавьте категории</td></tr>"
    )
    sync_rows = "".join(_sync_row(s) for s in recent_syncs) or (
        "<tr><td colspan='5'>Синхронизаций ещё не было</td></tr>"
    )

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="60">
<title>FeedBridge — статус</title>
<style>
  body {{ font-family: -apple-system, sans-serif; max-width: 960px;
         margin: 40px auto; padding: 0 20px; color: #222; }}
  h1 {{ font-size: 22px; margin-bottom: 4px; }}
  .meta {{ color: #888; font-size: 13px; margin-bottom: 32px; }}
  .cards {{ display: flex; gap: 16px; margin-bottom: 32px; flex-wrap: wrap; }}
  .card {{ background: #f5f5f5; border-radius: 8px; padding: 16px 24px; min-width: 140px; }}
  .card .num {{ font-size: 28px; font-weight: 700; }}
  .card .label {{ font-size: 13px; color: #666; }}
  h2 {{ font-size: 16px; margin: 28px 0 10px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
  th {{ text-align: left; padding: 8px 10px; background: #f0f0f0; font-weight: 600; }}
  td {{ padding: 8px 10px; border-bottom: 1px solid #eee; }}
  tr:hover td {{ background: #fafafa; }}
</style>
</head>
<body>
<h1>FeedBridge</h1>
<div class="meta">Обновлено: {now} &nbsp;·&nbsp; страница обновляется каждые 60 сек</div>

<div class="cards">
  <div class="card"><div class="num">{tmall_total:,}</div>
    <div class="label">товаров Tmall</div></div>
  <div class="card"><div class="num">{jd_total:,}</div><div class="label">заказов JD</div></div>
  <div class="card"><div class="num">{len(watchlist)}</div>
    <div class="label">категорий в слежении</div></div>
</div>

<h2>Категории в слежении</h2>
<table>
  <thead><tr><th>Категория</th><th>Источник</th><th>Товаров</th><th>Обновлено</th><th>Статус</th><th>Ошибка</th></tr></thead>
  <tbody>{watchlist_rows}</tbody>
</table>

<h2>Последние синхронизации</h2>
<table>
  <thead><tr><th>Время</th><th>Источник</th><th>Обработано</th><th>Новых</th><th>Ошибок</th></tr></thead>
  <tbody>{sync_rows}</tbody>
</table>
</body>
</html>"""


# ---------------------------------------------------------------------------

@router.api_route("/jd/callback", methods=["GET", "POST", "HEAD"])
async def jd_callback(request: Request) -> dict[str, Any]:
    """Whitelisted endpoint for JD VOP. Logs and returns 200.

    JD's exact ping/callback contract is TBD until app registration; this stub
    is sufficient to register the URL and unblock issuance of production keys.
    """
    import structlog

    log = structlog.get_logger(__name__)
    body: Any = None
    if request.method != "GET":
        try:
            body = await request.json()
        except Exception:
            body = (await request.body()).decode("utf-8", errors="replace")
    log.info("jd.callback", method=request.method, query=dict(request.query_params), body=body)
    return {"status": "ok"}


@router.post("/union/sync", dependencies=[Depends(require_api_key)])
async def union_sync(
    keyword: str = Query(..., min_length=1),
    with_bigfield: bool = Query(default=True),
    session: Session = Depends(db_session),
    settings: Settings = Depends(settings_dep),
) -> dict[str, Any]:
    """Search JD Union by keyword and persist results to jd_union_products."""
    sync_log = await run_union_sync(
        session,
        keyword=keyword,
        with_bigfield=with_bigfield,
        settings=settings,
    )
    return {
        "id": sync_log.id,
        "correlation_id": sync_log.correlation_id,
        "fetched": sync_log.fetched_count,
        "new": sync_log.new_count,
        "errors": sync_log.error_count,
        "keyword": keyword,
    }


@router.post("/union/check", dependencies=[Depends(require_api_key)])
async def union_check(
    file: UploadFile = File(...),
    format: str = Query(default="json", pattern="^(json|csv)$"),
    session: Session = Depends(db_session),
    settings: Settings = Depends(settings_dep),
):
    """Check a product catalog file (xlsx/csv) against JD Union.

    Persists the run and per-row results to the DB so it can be re-fetched via
    GET /union/checks/{id}. Pass ?format=csv to download the report as CSV.
    """
    data = await file.read()
    try:
        rows = load_product_bytes(data, file.filename or "upload.csv")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"could not parse file: {exc}") from exc

    report = await check_products(
        rows,
        session=session,
        settings=settings,
        source_filename=file.filename,
    )

    if format == "csv":
        return PlainTextResponse(
            report_to_csv(report),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=union_check.csv"},
        )
    return {"summary": report.summary(), "results": [r.as_dict() for r in report.results]}


@router.get("/union/checks", dependencies=[Depends(require_api_key)])
def union_check_list(
    limit: int = 50, session: Session = Depends(db_session)
) -> list[dict[str, Any]]:
    rows = (
        session.execute(
            select(JdUnionCatalogCheck)
            .order_by(desc(JdUnionCatalogCheck.id))
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": r.id,
            "source_filename": r.source_filename,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "total": r.total,
            "with_sku": r.with_sku,
            "found": r.found,
            "not_found": r.not_found,
            "no_sku": r.no_sku,
        }
        for r in rows
    ]


@router.get("/union/checks/{check_id}", dependencies=[Depends(require_api_key)])
def union_check_detail(
    check_id: int,
    format: str = Query(default="json", pattern="^(json|csv)$"),
    session: Session = Depends(db_session),
):
    """Replay a stored check: summary + per-row results, optionally as CSV."""
    report = load_check_from_db(session, check_id)
    if report is None:
        raise HTTPException(status_code=404, detail="check not found")
    if format == "csv":
        return PlainTextResponse(
            report_to_csv(report),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=union_check_{check_id}.csv"
            },
        )
    return {"summary": report.summary(), "results": [r.as_dict() for r in report.results]}


@router.get("/union/products", dependencies=[Depends(require_api_key)])
def list_union_products(
    limit: int = 50,
    session: Session = Depends(db_session),
) -> list[dict[str, Any]]:
    rows = (
        session.execute(
            select(JdUnionProduct)
            .order_by(desc(JdUnionProduct.fetched_at))
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [
        {
            "sku_id": r.sku_id,
            "sku_name": r.sku_name,
            "price_cny": r.price_cny,
            "price_rub": r.price_rub,
            "brand_name": r.brand_name,
            "shop_name": r.shop_name,
            "category_name": r.category_name,
            "commission": r.commission,
            "commission_share": r.commission_share,
            "in_order_count_30d": r.in_order_count_30d,
            "material_url": r.material_url,
            "main_image_url": r.main_image_url,
        }
        for r in rows
    ]


@router.get("/union/products/{sku_id}", dependencies=[Depends(require_api_key)])
def union_product_detail(sku_id: str, session: Session = Depends(db_session)) -> dict[str, Any]:
    row = session.get(JdUnionProduct, sku_id)
    if row is None:
        raise HTTPException(status_code=404, detail="union product not found")
    return {
        "sku_id": row.sku_id,
        "sku_name": row.sku_name,
        "price_cny": row.price_cny,
        "price_rub": row.price_rub,
        "lowest_price_cny": row.lowest_price_cny,
        "brand_name": row.brand_name,
        "shop_id": row.shop_id,
        "shop_name": row.shop_name,
        "category_id": row.category_id,
        "category_name": row.category_name,
        "material_url": row.material_url,
        "main_image_url": row.main_image_url,
        "commission": row.commission,
        "commission_share": row.commission_share,
        "in_order_count_30d": row.in_order_count_30d,
        "ware_qd": row.ware_qd,
        "wdesc": row.wdesc,
        "fetched_at": row.fetched_at.isoformat() if row.fetched_at else None,
        "raw_payload": row.raw_payload,
    }
