from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "netsuite-dashboard-backend"
    aws_region: str = Field(default="us-east-1", alias="AWS_REGION")
    cognito_user_pool_id: str = Field(alias="COGNITO_USER_POOL_ID")
    cognito_app_client_id: str = Field(alias="COGNITO_APP_CLIENT_ID")
    cognito_region: str = Field(default="us-east-1", alias="COGNITO_REGION")
    netsuite_secret_name: Optional[str] = Field(default=None, alias="NETSUITE_SECRET_NAME")
    netsuite_client: Optional[str] = Field(default=None, alias="NETSUITE_CLIENT")
    netsuite_secret: Optional[str] = Field(default=None, alias="NETSUITE_SECRET")
    netsuite_token_id: Optional[str] = Field(default=None, alias="NETSUITE_TOKEN_ID")
    netsuite_token_secret: Optional[str] = Field(default=None, alias="NETSUITE_TOKEN_SECRET")
    netsuite_realm: Optional[str] = Field(default=None, alias="NETSUITE_REALM")
    netsuite_query_page_size: int = Field(default=1000, alias="NETSUITE_QUERY_PAGE_SIZE")
    netsuite_ddb_cache_enabled: bool = Field(default=False, alias="NETSUITE_DDB_CACHE_ENABLED")
    netsuite_ddb_cache_table: Optional[str] = Field(default=None, alias="NETSUITE_DDB_CACHE_TABLE")
    netsuite_query_cache_ttl_seconds: int = Field(default=1800, alias="NETSUITE_QUERY_CACHE_TTL_SECONDS")
    netsuite_ddb_cache_max_payload_bytes: int = Field(default=350000, alias="NETSUITE_DDB_CACHE_MAX_PAYLOAD_BYTES")

    @property
    def cognito_issuer(self) -> str:
        return f"https://cognito-idp.{self.cognito_region}.amazonaws.com/{self.cognito_user_pool_id}"

    @property
    def jwks_url(self) -> str:
        return f"{self.cognito_issuer}/.well-known/jwks.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()
