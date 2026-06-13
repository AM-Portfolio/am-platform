import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.llm.circuit_breaker import CircuitBreaker, CircuitState
from app.llm.router import LLMRouter

@pytest.mark.asyncio
async def test_circuit_breaker_flow():
    breaker = CircuitBreaker("mock-provider", failure_threshold=2, recovery_timeout=1)
    assert breaker.allow_request() is True

    # Record first failure
    breaker.record_failure()
    assert breaker.state == CircuitState.CLOSED
    assert breaker.allow_request() is True

    # Record second failure (trips)
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN
    assert breaker.allow_request() is False

    # Check recovery timeout
    import time
    time.sleep(1.1)
    assert breaker.allow_request() is True
    assert breaker.state == CircuitState.HALF_OPEN

    # Record success resets breaker
    breaker.record_success()
    assert breaker.state == CircuitState.CLOSED
    assert breaker.allow_request() is True

@pytest.mark.asyncio
async def test_llm_router_failover():
    router = LLMRouter()
    
    from app.llm.deepseek import DeepSeekProvider
    from app.llm.gemini import GeminiProvider

    # Mock actual provider instances so class name mapping is preserved
    mock_deepseek = DeepSeekProvider()
    mock_deepseek.generate_chat = AsyncMock(side_effect=Exception("Connection Timeout"))
    
    mock_gemini = GeminiProvider()
    mock_gemini.generate_chat = AsyncMock(return_value="Gemini response")
    
    router.providers_chain = [mock_deepseek, mock_gemini]
    
    # Call router
    response, model = await router.generate_chat("Hello")
    
    assert response == "Gemini response"
    assert model == "gemini"
    
    # Check that DeepSeek circuit breaker recorded failure
    assert router.breakers["deepseek"].failures == 1

