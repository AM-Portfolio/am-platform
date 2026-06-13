import logging
from typing import Dict, Any, Optional
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

class FinAgentClient:
    def __init__(self):
        self.base_url = settings.MCP_SERVER_URL  # points to http://localhost:8100 or am-fin-agent service
        self.timeout = settings.MCP_SERVER_TIMEOUT_SECONDS

    async def check_financial_intent(self, message: str) -> bool:
        """
        Uses a lightweight check to determine if the message requires financial tools.
        For example, questions about valuation, portfolio, holdings, stocks, trades, allocation.
        """
        keywords = {
            "portfolio", "valuation", "holdings", "stock", "trade", "buy", "sell", "etf",
            "allocation", "benchmark", "mover", "activity", "balance", "shares", "invest"
        }
        sanitized = message.lower().split()
        for word in sanitized:
            # Check prefix/substring match for keywords
            for kw in keywords:
                if kw in word:
                    return True
        return False

    async def query_agent(
        self,
        message: str,
        user_id: str,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Proxies request to am-fin-agent chat endpoint POST /api/v1/ai/chat.
        """
        url = f"{self.base_url.rstrip('/')}/api/v1/ai/chat"
        payload = {
            "message": message,
            "userId": user_id,
            "sessionId": session_id
        }

        logger.info(f"Routing financial request to am-fin-agent: {url} (User: {user_id})")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=payload)
            if response.status_code != 200:
                logger.error(f"am-fin-agent returned error status {response.status_code}: {response.text}")
                response.raise_for_status()
            
            return response.json()

fin_agent_client = FinAgentClient()
