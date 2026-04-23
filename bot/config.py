from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix='MYINSTANTS_',
        env_file=_REPO_ROOT / '.env',
        env_file_encoding='utf-8',
        extra='ignore',
        case_sensitive=False,
    )

    bot_token: SecretStr = Field(..., description='Discord bot token.')
    environment: Literal['dev', 'prod'] = Field(
        default='dev', alias='MYINSTANTS_ENV'
    )
    dev_guild_id: int | None = Field(
        default=None,
        description='If set, sync slash commands only to this guild.',
    )
    sync_global: bool = Field(
        default=False,
        description='Sync commands globally even when dev_guild_id is set.',
    )

    idle_timeout_seconds: int = Field(default=180, ge=10, le=3600)
    skip_vote_threshold: int = Field(default=3, ge=1, le=20)
    queue_page_size: int = Field(default=10, ge=1, le=25)
    default_volume: float = Field(default=0.5, ge=0.0, le=1.0)
    loop_max_iterations: int = Field(default=20, ge=1, le=1000)
    fallback_thumbnail_url: str = (
        'https://images-na.ssl-images-amazon.com/images/I/61LNAo2K9RL.png'
    )

    search_result_limit: int = Field(default=25, ge=1, le=100)
    myinstants_timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0)
    myinstants_connect_timeout_seconds: float = Field(
        default=5.0, ge=1.0, le=30.0
    )
    myinstants_rate_limit_per_sec: float = Field(default=5.0, ge=0.1, le=50.0)
    cache_search_ttl_seconds: int = Field(default=600, ge=0, le=86400)
    cache_details_ttl_seconds: int = Field(default=3600, ge=0, le=86400)

    database_url: str = Field(
        default='sqlite+aiosqlite:///./data/bot.db',
        description='Async SQLAlchemy URL. Use aiosqlite driver for SQLite.',
    )
    pii_hash_key: SecretStr | None = Field(
        default=None,
        description='HMAC-SHA256 key for PII hashing. Required in prod.',
    )
    history_retention_days: int = Field(default=180, ge=1, le=3650)

    log_format: Literal['pretty', 'json'] = 'pretty'
    log_level: str = Field(default='INFO')
    sentry_dsn: SecretStr | None = None
    sentry_traces_sample_rate: float = Field(default=0.0, ge=0.0, le=1.0)

    heartbeat_file: Path = Field(
        default=Path('/tmp/myinstants-heartbeat'),  # noqa: S108
        description='Path updated periodically; read by healthcheck.',
    )

    @field_validator('log_level')
    @classmethod
    def _normalise_log_level(cls, value: str) -> str:
        normalised = value.upper()
        allowed = {'TRACE', 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}
        if normalised not in allowed:
            raise ValueError(
                f'log_level must be one of {sorted(allowed)}, got {value!r}'
            )
        return normalised

    @property
    def is_production(self) -> bool:
        return self.environment == 'prod'

    def require_pii_hash_key(self) -> SecretStr:
        if self.pii_hash_key is None:
            if self.is_production:
                raise RuntimeError(
                    'MYINSTANTS_PII_HASH_KEY is required in production.'
                )
            return SecretStr('dev-insecure-pii-hash-key-do-not-use-in-prod')
        return self.pii_hash_key


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]
