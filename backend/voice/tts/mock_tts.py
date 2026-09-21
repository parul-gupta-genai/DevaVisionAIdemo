import asyncio
import base64
from typing import AsyncGenerator
from loguru import logger
from voice.interfaces.tts import ITtsEngine

class MockTtsEngine(ITtsEngine):
    """
    Simulates a streaming TTS engine (like ElevenLabs or AWS Polly).
    Takes a string of text and yields base64 encoded audio chunks.
    Since we don't have a real TTS model, we will yield a dummy silent WAV/Opus file.
    """
    async def synthesize_stream(self, text: str) -> AsyncGenerator[bytes, None]:
        logger.info(f"MockTTS: Synthesizing text: '{text[:30]}...'")
        
        # Simulate initial processing latency (TTFB - Time to First Byte)
        await asyncio.sleep(0.3)
        
        # Generate some dummy bytes to simulate audio chunks
        # In a real app, this would be MP3 or Opus frames
        dummy_audio = b"RIFF" + b"\x00" * 44  # Just a fake WAV header to prevent complete client crashes
        
        for i in range(3):
            # Stream the chunks out
            yield dummy_audio
            await asyncio.sleep(0.1) # Simulate real-time streaming
            
        logger.info("MockTTS: Finished streaming audio.")
