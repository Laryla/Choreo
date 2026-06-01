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
    FEISHU_NOTIFY_CHAT_ID: str = ""  # 通知推送目标 chat_id（私聊或群聊）

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

    # Web search（可选）
    TAVILY_API_KEY: str = ""   # 设置后自动切换到 Tavily；需同时 uv add tavily-python

    # 飞书 Bot（平台接入）
    FEISHU_TRANSPORT: str = "websocket"          # websocket | webhook
    FEISHU_ENCRYPT_KEY: str = ""                  # webhook 模式：加密 key
    FEISHU_VERIFICATION_TOKEN: str = ""           # webhook 模式：校验 token
    FEISHU_BOT_OPEN_ID: str = ""                  # 群聊 @mention 过滤用
    FEISHU_ENABLED: bool = False                  # 显式开启才启动


settings = Settings()
