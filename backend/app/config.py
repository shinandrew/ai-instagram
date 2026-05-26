from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/ai_instagram"
    secret_key: str = "dev-secret-change-me"

    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = "ai-instagram"
    r2_public_url: str = "https://example.r2.dev"

    public_base_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:3000"
    allowed_origins: str = "http://localhost:3000"
    admin_secret: str = "dev-admin-secret"
    nursery_secret: str = "dev-nursery-secret"
    openai_api_key: str = ""
    hf_token: str = ""
    research_api_key: str = ""
    resend_api_key: str = ""
    email_from: str = ""

    twitter_client_id: str = ""
    twitter_client_secret: str = ""
    twitter_bearer_token: str = ""
    twitter_callback_url: str = "http://localhost:8000/api/auth/twitter/callback"

    @property
    def origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]


settings = Settings()
