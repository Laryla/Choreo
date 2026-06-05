from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Tuple, Type

import yaml
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

_CONFIG_YAML = Path(__file__).parents[1] / "config.yaml"


def _resolve_env_vars(obj: Any) -> Any:
    """递归将 $ENV_VAR 替换为对应环境变量的值（密钥存 .env，yaml 里写 $KEY_NAME）。"""
    if isinstance(obj, str) and obj.startswith("$"):
        return os.getenv(obj[1:], "")
    if isinstance(obj, dict):
        return {k: _resolve_env_vars(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_env_vars(item) for item in obj]
    return obj


class _YamlConfigSource(PydanticBaseSettingsSource):
    """从 config.yaml 加载配置，优先级低于 .env / 环境变量。"""

    def __init__(self, settings_cls: Type[BaseSettings]) -> None:
        super().__init__(settings_cls)
        try:
            raw = yaml.safe_load(_CONFIG_YAML.read_text(encoding="utf-8")) or {}
        except Exception:
            raw = {}
        self._data: dict[str, Any] = _resolve_env_vars(raw)

    def get_field_value(self, field: Any, field_name: str) -> Tuple[Any, str, bool]:
        key = field_name.lower()
        val = self._data.get(key)
        return val, key, val is not None

    def __call__(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for field_name in self.settings_cls.model_fields:
            key = field_name.lower()
            if key in self._data:
                result[field_name] = self._data[key]
        return result


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_nested_delimiter="__",
    )

    # ── 数据库（密钥，建议放 .env）────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/choreo"

    @property
    def DATABASE_URL_PSYCOPG(self) -> str:
        return self.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

    # ── LangSmith（密钥，建议放 .env）────────────────────────────────
    LANGSMITH_API_KEY: str = ""
    LANGSMITH_PROJECT: str = "choreo-dev"
    LANGSMITH_TRACING: bool = False

    # ── 飞书 Bot 密钥（建议放 .env）──────────────────────────────────
    FEISHU_APP_ID: str = ""
    FEISHU_APP_SECRET: str = ""
    FEISHU_WEBHOOK_URL: str = ""
    FEISHU_NOTIFY_CHAT_ID: str = ""
    FEISHU_TRANSPORT: str = "websocket"
    FEISHU_ENCRYPT_KEY: str = ""
    FEISHU_VERIFICATION_TOKEN: str = ""
    FEISHU_BOT_OPEN_ID: str = ""
    FEISHU_ENABLED: bool = False

    # ── SMTP 密钥（建议放 .env）──────────────────────────────────────
    SMTP_HOST: str = ""
    SMTP_PORT: int = 465
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""

    # ── Auth（密钥，建议放 .env）──────────────────────────────────────
    AUTH_MODE: str = "jwt"  # "jwt" = 正常鉴权；"all" = 本地开发无需登录
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    BACKEND_URL: str = "http://localhost:8000"
    FRONTEND_URL: str = "http://localhost:5173"
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""

    # ── Web search（密钥，建议放 .env）───────────────────────────────
    TAVILY_API_KEY: str = ""

    # ── 从 config.yaml 读取的配置项（以下默认值在 yaml 里覆盖）──────
    LOG_LEVEL: str = "INFO"
    ACTIVE_MODEL: str = "deepseek-chat"
    ACTIVE_SANDBOX: str = "local-dev"
    SKILLS_DIR: str = "../skills"
    OUTPUT_DIR: str = "../sandbox/output"

    CHOREO_MAX_LLM_CALLS: int = 100
    CHOREO_SANDBOX_TIMEOUT: int = 120
    CHOREO_SANDBOX_WORKDIR: str = "./sandbox"
    KNOWLEDGE_BASE_DIR: str = "./knowledge"

    # 复杂结构（yaml 原样映射为 list/dict）
    MODELS: list = []
    SANDBOXES: list = []
    PLATFORMS: list = []
    CURATOR: dict = {}
    KNOWLEDGE_SOURCES: list = []
    ACTIVITY_PROFILE: dict = {}

    # ── 上下文压缩──────────────────────────────────────────────────
    REVIEW_MODEL: str = ""  # 技能审核用模型，空则与 active_model 相同

    CONTEXT_COMPRESSION_ENABLED: bool = True
    CONTEXT_COMPRESSION_TRIGGER_MESSAGES: int = 60
    CONTEXT_COMPRESSION_TRIGGER_TOKENS: int = 60000
    CONTEXT_COMPRESSION_KEEP_MESSAGES: int = 20

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,               # 最高优先（代码里显式传参）
            env_settings,                # 环境变量（密钥）
            dotenv_settings,             # .env 文件（密钥）
            _YamlConfigSource(settings_cls),  # config.yaml（主配置）
            file_secret_settings,        # secrets 目录（最低）
        )


settings = Settings()
