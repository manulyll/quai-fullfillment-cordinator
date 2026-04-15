from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.auth import require_any_role
from app.config import Settings, get_settings
from app.integrations.netsuite import get_shortage_report, list_locations

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
