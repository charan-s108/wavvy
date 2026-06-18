from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str = ""
    hf_token: str = ""  # HuggingFace token — used for Inference API embeddings

    # LiveKit
    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""

    # Deepgram STT
    deepgram_api_key: str = ""

    # Cartesia TTS
    cartesia_api_key:  str = ""
    cartesia_voice_id: str = "f039066f-cdb7-45ed-b51d-1034ae2f04a0"  # Cindy Baker — smooth, welcoming female receptionist
    cartesia_model:    str = "sonic-2"

    database_url: str = "postgresql+asyncpg://wavvy:wavvy@localhost:5433/wavvy"
    chroma_persist_dir: str = "./chroma_db"
    frontend_landing_url: str = "http://localhost:5173"
    frontend_agent_url: str = "http://localhost:5174"
    frontend_admin_url: str = "http://localhost:5175"
    environment: str = "development"
    secret_key: str = "change-in-production"

    # Email (optional — demo confirmation emails)
    smtp_host: str = ""
    smtp_user: str = ""
    smtp_pass: str = ""
    smtp_from: str = ""

    # SIP/PSTN — public URL used as LiveKit webhook target for inbound SIP calls
    public_backend_url: str = "http://localhost:8000"

    # Internal URL workers use to call FastAPI.
    # On HuggingFace both processes share the container — start.sh sets this to :7860.
    # Local dev uses :8000 (uvicorn default).
    backend_internal_url: str = "http://localhost:8000"

    @property
    def allowed_origins(self) -> list[str]:
        origins = [
            self.frontend_landing_url,
            self.frontend_agent_url,
            self.frontend_admin_url,
        ]
        if self.environment == "development":
            origins.append("*")
        return origins


settings = Settings()
