from abc import ABC, abstractmethod
from typing import AsyncGenerator

class ISttEngine(ABC):
    """
    Interface for Streaming Speech-To-Text.
    Takes an async generator of audio chunks and yields partial/final transcripts.
    """
    @abstractmethod
    async def transcribe_stream(self, audio_stream: AsyncGenerator[bytes, None]) -> AsyncGenerator[dict, None]:
        """
        Yields dictionaries like:
        {"type": "partial", "text": "hello"}
        {"type": "final", "text": "hello world", "confidence": 0.99}
        """
        pass
        # Need yield statement in implementation
