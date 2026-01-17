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

    # STT Backend Selection
    stt_backend: str = "whisper"  # "parakeet" or "whisper"

    # Whisper Pool Settings (when stt_backend="whisper")
    whisper_model_size: str = "base"  # tiny, base, small
    whisper_num_instances: int = 8  # Number of concurrent instances
    whisper_compute_type: str = "float16"  # float16, int8_float16, int8
    whisper_device: str = "cuda"

    # LLM settings
    llm_max_tokens: int = 256
    llm_temperature: float = 0.7

    # Database
    database_url: str = ""

    # SignalWire
    signalwire_project_id: str = ""
    signalwire_token: str = ""
    signalwire_space: str = ""

    # Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""

    # RunPod
    runpod_api_key: str = ""
    runpod_endpoint: str = "9fal0rjnh2vqbj-8888.proxy.runpod.net"

    # Audio
    sample_rate: int = 16000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Allow extra env vars without error


settings = Settings()
