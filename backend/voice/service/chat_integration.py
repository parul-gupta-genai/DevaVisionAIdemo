from loguru import logger
import asyncio
from agents.chat_agent import agent

class VoiceChatIntegration:
    """
    Service layer bridging the Voice STT final transcript to the existing DevaVisionAIAgent.
    Ensures zero duplication of business logic by directly invoking the exact same method 
    used by the REST API.
    """
    def process_chat_message(self, text: str, camera_id: str = "") -> str:
        """
        Takes the final transcript from STT, passes it to the agent, and returns the text response.
        Since agent.chat is synchronous, we run it in an executor in the manager, or just block lightly here.
        """
        logger.info(f"Voice Integration: Sending to LLM -> '{text}'")
        try:
            response = agent.chat(user_input=text, camera_id=camera_id)
            return response
        except Exception as e:
            logger.error(f"Voice Integration Error: {e}")
            return "Sorry, I encountered an error while processing your voice request."
