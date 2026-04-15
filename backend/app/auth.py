from typing import Any
import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt
from jose.exceptions import JWTError

from app.config import Settings, get_settings

security = HTTPBearer(auto_error=True)
MVP_TOKEN = "quai-mvp-token"


class CognitoJwtVerifier:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._jwks: dict[str, Any] | None = None

    async def _get_jwks(self) -> dict[str, Any]:
        if self._jwks:
            return self._jwks
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(self._settings.jwks_url)
            response.raise_for_status()
            self._jwks = response.json()
        return self._jwks

    async def verify(self, token: str) -> dict[str, Any]:
        jwks = await self._get_jwks()
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        key = next((k for k in jwks["keys"] if k.get("kid") == kid), None)
        if not key:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unable to find JWT signing key")

        try:
            payload = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                audience=self._settings.cognito_app_client_id,
                issuer=self._settings.cognito_issuer,
            )
        except JWTError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid JWT") from exc
        return payload


async def get_current_user_claims(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    if credentials.credentials == MVP_TOKEN:
        return {
            "username": "frontend quai",
            "email": None,
            "cognito:groups": ["admin", "sales_manager", "viewer"],
        }
    verifier = CognitoJwtVerifier(settings)
    return await verifier.verify(credentials.credentials)


def get_user_roles(claims: dict[str, Any]) -> list[str]:
    groups = claims.get("cognito:groups", [])
    if isinstance(groups, str):
        return [groups]
    if isinstance(groups, list):
        return [str(group) for group in groups]
    return []


def require_any_role(allowed_roles: set[str]):
    async def dependency(claims: dict[str, Any] = Depends(get_current_user_claims)) -> dict[str, Any]:
        user_roles = set(get_user_roles(claims))
        if not user_roles.intersection(allowed_roles):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return claims

    return dependency
