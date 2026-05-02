from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_ttl_minutes: int = 60

    # Postgres connection string. DigitalOcean Managed DB injects this
    # automatically via ${db.DATABASE_URL}; locally docker-compose sets it.
    database_url: str = "postgresql://cfo:cfo@localhost:5432/cfo"

    model_conductor: str = "claude-opus-4-5"
    model_specialist: str = "claude-sonnet-4-5"
    model_haiku: str = "claude-haiku-4-5"

    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def llm_mode(self) -> str:
        return "live" if self.anthropic_api_key else "mock"


settings = Settings()
