"""
BuddyHelps Voice Server Configuration
"""
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"

    # Models
    stt_model: str = "nvidia/parakeet-tdt-0.6b-v2"
    llm_model: str = "Qwen/Qwen2.5-0.5B-Instruct"
    tts_voice: str = "af_heart"  # Kokoro voice preset

    # LLM settings
    llm_max_tokens: int = 256
    llm_temperature: float = 0.7

    # Database
    database_url: str = ""

    # SignalWire
    signalwire_project_id: str = ""
    signalwire_token: str = ""
    signalwire_space: str = ""

    # Audio
    sample_rate: int = 16000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
