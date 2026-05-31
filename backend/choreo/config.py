from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/choreo"
    CHOREO_MAX_LLM_CALLS: int = 100

    @property
    def DATABASE_URL_PSYCOPG(self) -> str:
        """psycopg 格式连接串（用于 LangGraph checkpointer）"""
        return self.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

    # LangSmith
    LANGSMITH_API_KEY: str = ""
    LANGSMITH_PROJECT: str = "choreo-dev"
    LANGSMITH_TRACING: bool = False

    # 飞书
    FEISHU_WEBHOOK_URL: str = ""

    # SMTP
    SMTP_HOST: str = ""
    SMTP_PORT: int = 465
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""

    # 沙箱
    CHOREO_SANDBOX_TIMEOUT: int = 120
    CHOREO_SANDBOX_WORKDIR: str = "./sandbox"

    # Auth
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    BACKEND_URL: str = "http://localhost:8000"
    FRONTEND_URL: str = "http://localhost:5173"

    # GitHub OAuth
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""

    # 飞书 OAuth
    FEISHU_APP_ID: str = ""
    FEISHU_APP_SECRET: str = ""


settings = Settings()
