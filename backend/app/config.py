from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./procurementpro.db"
    secret_key: str = "change-me"
    session_days: int = 365  # "sign in once": a device stays signed in this long
    storage_dir: str = "./storage"
    max_upload_mb: int = 25
    max_files_per_upload: int = 20
    # AI: "off" (heuristic parsers only) | "local" | "external"
    ai_mode: str = "off"
    ai_base_url: str = "http://localhost:11434/v1"  # any OpenAI-compatible server (Ollama, vLLM, ...)
    ai_model: str = "qwen2.5:7b-instruct"
    ai_api_key: str = ""
    # Admin must explicitly allow sending documents to a non-local provider.
    ai_external_allowed: bool = False
    ocr_langs: str = "rus+eng+uzb"
    stt_url: str = ""  # OpenAI-compatible /audio/transcriptions endpoint, optional
    # Phone sign-in from outside the office network needs the admin to approve the new device.
    lan_only_instant_login: bool = True
    trusted_networks: str = ""  # extra CIDRs treated as "office", comma-separated, e.g. a VPN: 100.64.0.0/10
    # Telegram notifications to the team (optional). Create a bot with @BotFather, add it to a group, put the group id here.
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    public_base_url: str = ""  # e.g. https://cp360.uz, used for links inside notifications
    bootstrap_admin_name: str = "Администратор"
    bootstrap_admin_phone: str = ""
    bootstrap_admin_email: str = "admin@example.com"
    bootstrap_admin_password: str = "admin12345"


settings = Settings()
