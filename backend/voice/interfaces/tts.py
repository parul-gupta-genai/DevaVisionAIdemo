from abc import ABC, abstractmethod
from typing import AsyncGenerator

class ITtsEngine(ABC):
    """
    Interface for Streaming Text-To-Speech.
    Takes a text string and yields audio chunks asynchronously.
    """
    @abstractmethod
    async def synthesize_stream(self, text: str) -> AsyncGenerator[bytes, None]:
        """
        Yields binary audio chunks suitable for real-time playback.
        """
        pass
        # Need yield statement in implementation
