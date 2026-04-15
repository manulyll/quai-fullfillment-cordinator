from typing import Any
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import get_current_user_claims, get_user_roles

router = APIRouter(prefix="/api", tags=["me"])


class MeResponse(BaseModel):
    username: str
    email: str | None = None
    roles: list[str]


@router.get("/me", response_model=MeResponse)
async def get_me(claims: dict[str, Any] = Depends(get_current_user_claims)) -> MeResponse:
    return MeResponse(
        username=str(claims.get("cognito:username") or claims.get("username") or claims.get("sub")),
        email=claims.get("email"),
        roles=get_user_roles(claims),
    )
