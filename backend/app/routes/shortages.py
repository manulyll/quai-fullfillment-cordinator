from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.auth import require_any_role
from app.config import Settings, get_settings
from app.integrations.netsuite import get_next_day_orders, get_picking_ticket_html, get_shortage_report, list_locations

router = APIRouter(prefix="/api/shortages", tags=["shortages"])


class ShortageComponent(BaseModel):
    itemId: int
    itemName: str
    orderedQty: float
    onHandQty: float
    remainingStock: float


class ShortageLine(BaseModel):
    itemId: int
    itemName: str
    date: str | None
    orderedQty: float
    onHandQty: float | None = None
    remainingStock: float | None = None
    isKit: bool
    components: list[ShortageComponent] = []


class ShortageOrder(BaseModel):
    soNum: str
    customer: str
    serviceType: str
    status: str = ""
    location: str = ""
    city: str = ""
    date: str | None
    totalOrdered: float
    lines: list[ShortageLine]


class ShortageReportResponse(BaseModel):
    locationId: int | None = None
    startDate: str
    endDate: str
    orders: list[ShortageOrder]
    totalOrders: int
    asOf: str


class LocationOption(BaseModel):
    id: int
    name: str


class LocationOptionsResponse(BaseModel):
    locations: list[LocationOption]


class NextDayOrder(BaseModel):
    soNum: str
    customer: str
    status: str
    isConfirmed: bool
    shipDate: str
    location: str


class NextDayOrdersResponse(BaseModel):
    date: str
    totalOrders: int
    unconfirmedOrders: int
    orders: list[NextDayOrder]
    asOf: str


@router.get("/locations", response_model=LocationOptionsResponse)
async def shortage_locations(
    _: dict[str, Any] = Depends(require_any_role({"admin", "sales_manager", "viewer"})),
    settings: Settings = Depends(get_settings),
) -> LocationOptionsResponse:
    return LocationOptionsResponse(locations=list_locations(settings))


@router.get("/report", response_model=ShortageReportResponse)
async def shortage_report(
    location_id: int | None = Query(default=None, alias="locationId"),
    start_date: date | None = Query(default=None, alias="startDate"),
    end_date: date | None = Query(default=None, alias="endDate"),
    _: dict[str, Any] = Depends(require_any_role({"admin", "sales_manager", "viewer"})),
    settings: Settings = Depends(get_settings),
) -> ShortageReportResponse:
    payload = get_shortage_report(
        settings=settings,
        location_id=location_id,
        start_date=start_date,
        end_date=end_date,
    )
    return ShortageReportResponse(**payload)


@router.get("/next-day", response_model=NextDayOrdersResponse)
async def next_day_orders(
    date_param: date | None = Query(default=None, alias="date"),
    location_id: int | None = Query(default=None, alias="locationId"),
    _: dict[str, Any] = Depends(require_any_role({"admin", "sales_manager", "viewer"})),
    settings: Settings = Depends(get_settings),
) -> NextDayOrdersResponse:
    payload = get_next_day_orders(settings=settings, target_date=date_param, location_id=location_id)
    return NextDayOrdersResponse(**payload)


@router.get("/picking-ticket/{so_num}", response_class=HTMLResponse)
async def picking_ticket(
    so_num: str,
    _: dict[str, Any] = Depends(require_any_role({"admin", "sales_manager", "viewer"})),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    try:
        html = get_picking_ticket_html(settings=settings, so_num=so_num)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return HTMLResponse(content=html)
