import time
import logging
from enum import Enum
from app.config import settings

logger = logging.getLogger(__name__)

class CircuitState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

class CircuitBreaker:
    def __init__(self, provider: str, failure_threshold: int = None, recovery_timeout: int = None):
        self.provider = provider
        self.failure_threshold = failure_threshold or settings.LLM_CB_FAILURE_THRESHOLD
        self.recovery_timeout = recovery_timeout or settings.LLM_CB_RECOVERY_TIMEOUT_SECONDS
        self.state = CircuitState.CLOSED
        self.failures = 0
        self.last_state_change = time.time()

    def record_success(self):
        """Records a successful call and closes the circuit if it was open or half-open."""
        if not settings.LLM_CB_ENABLED:
            return
        if self.state != CircuitState.CLOSED:
            logger.info(f"Circuit breaker for provider '{self.provider}' changed state from {self.state.name} to CLOSED.")
        self.failures = 0
        self.state = CircuitState.CLOSED

    def record_failure(self):
        """Records a failure and opens the circuit if failure threshold is reached."""
        if not settings.LLM_CB_ENABLED:
            return
        self.failures += 1
        logger.warning(f"Recorded failure for provider '{self.provider}'. Total failures: {self.failures}/{self.failure_threshold}")
        if self.failures >= self.failure_threshold and self.state != CircuitState.OPEN:
            logger.error(f"Circuit breaker for provider '{self.provider}' tripped! State changed to OPEN for {self.recovery_timeout} seconds.")
            self.state = CircuitState.OPEN
            self.last_state_change = time.time()

    def allow_request(self) -> bool:
        """Determines if a request to the provider is allowed based on the circuit state."""
        if not settings.LLM_CB_ENABLED:
            return True
        if self.state == CircuitState.CLOSED:
            return True
        
        now = time.time()
        if self.state == CircuitState.OPEN:
            # Check if recovery timeout has passed
            if now - self.last_state_change > self.recovery_timeout:
                logger.info(f"Recovery timeout passed. Circuit breaker for provider '{self.provider}' set to HALF_OPEN.")
                self.state = CircuitState.HALF_OPEN
                self.last_state_change = now
                return True
            return False
            
        if self.state == CircuitState.HALF_OPEN:
            # In half-open state, we allow one trial request
            return True
            
        return True
