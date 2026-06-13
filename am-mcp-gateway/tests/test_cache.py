import pytest
from app.session.cache import ResponseCache

@pytest.mark.asyncio
async def test_cache_dynamic_bypassing():
    cache = ResponseCache()
    cache.enabled = True
    
    # Prompt with dynamic word
    assert cache._should_cache("What is the valuation today?") is False
    assert cache._should_cache("give me current stock price") is False
    
    # Normal prompt
    assert cache._should_cache("Explain stock options") is True

@pytest.mark.asyncio
async def test_cache_fallback_in_memory():
    cache = ResponseCache()
    cache.enabled = True
    cache.redis_client = None  # Force in-memory fallback
    
    user_id = "user-123"
    prompt = "Explain stock options"
    model = "deepseek-chat"
    
    # Try reading empty cache
    res = await cache.get(user_id, prompt, model)
    assert res is None
    
    # Write to cache
    await cache.set(user_id, prompt, model, "cached explanation")
    
    # Read cache
    res = await cache.get(user_id, prompt, model)
    assert res == "cached explanation"
