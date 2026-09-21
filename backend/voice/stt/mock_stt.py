import asyncio
import io
import httpx
import requests
from pydub import AudioSegment
from typing import AsyncGenerator
from loguru import logger
from voice.interfaces.stt import ISttEngine
from config.config import config
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import json

class LiveSttEngine(ISttEngine):
    """
    Live STT engine using Groq's whisper-large-v3 API.
    Accumulates WebM chunks from the frontend and converts them to WAV for recognition.
    Enforces English and implements resilient retries.
    """
    def __init__(self):
        self.api_key = config.GROQ_API_KEY
        if not self.api_key:
            logger.warning("GROQ_API_KEY is not set. Voice recognition will fail.")

    async def transcribe_stream(self, audio_stream: AsyncGenerator[bytes, None]) -> AsyncGenerator[dict, None]:
        audio_buffer = bytearray()
        logger.info("GroqSTT: Started receiving audio stream...")
        
        try:
            async for chunk in audio_stream:
                audio_buffer.extend(chunk)
                if len(audio_buffer) % 30000 < 5000:
                    yield {"type": "partial", "text": "Listening to your voice..."}
                    
            logger.info(f"GroqSTT: Stream ended. Total bytes received: {len(audio_buffer)}")
            
            if len(audio_buffer) == 0:
                yield {"type": "error", "message": "No audio data received.", "code": "STT_EMPTY_AUDIO"}
                return
            if not self.api_key:
                yield {"type": "error", "message": "Groq API Key is missing. Please configure it.", "code": "STT_NO_API_KEY"}
                return

            yield {"type": "partial", "text": "Transcribing with Groq..."}
            
            loop = asyncio.get_running_loop()
            
            @retry(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=1, min=1, max=5),
                retry=retry_if_exception_type((requests.exceptions.RequestException, requests.exceptions.Timeout)),
                reraise=True
            )
            def _call_groq_api(webm_io):
                headers = {
                    "Authorization": f"Bearer {self.api_key}"
                }
                files = {
                    "file": ("audio.webm", webm_io, "audio/webm")
                }
                data = {
                    "model": "whisper-large-v3",
                    "response_format": "json",
                    "language": "en" # Phase 3: Enforce English to prevent Urdu/Welsh hallucinations
                }
                
                response = requests.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers=headers,
                    files=files,
                    data=data,
                    timeout=10
                )
                response.raise_for_status()
                return response.json().get("text", "")
            
            def process_audio(raw_bytes):
                try:
                    webm_io = io.BytesIO(raw_bytes)
                    return {"success": True, "text": _call_groq_api(webm_io)}
                except requests.exceptions.HTTPError as e:
                    logger.error(f"Groq API HTTP Error: {e.response.status_code} - {e.response.text}")
                    return {"success": False, "code": "STT_PROVIDER_ERROR", "message": "The STT provider is currently unavailable. Please try again."}
                except Exception as e:
                    logger.error(f"STT processing error: {e}")
                    return {"success": False, "code": "STT_SYSTEM_ERROR", "message": "Failed to process audio format internally."}

            result = await loop.run_in_executor(None, process_audio, audio_buffer)
            
            if not result.get("success"):
                yield {"type": "error", "message": result.get("message"), "code": result.get("code")}
                return
                
            final_text = result.get("text", "")
            logger.info(f"GroqSTT: Final Transcript -> '{final_text}'")
            yield {"type": "final", "text": final_text, "confidence": 0.95}
                
        except Exception as e:
            logger.error(f"GroqSTT Stream Error: {e}")
            yield {"type": "error", "message": "An unexpected error occurred during transcription.", "code": "STT_UNEXPECTED"}
