import io
import json
import logging
from uuid import uuid4
import pytest
from pydantic import ValidationError
from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx

from am_platform_common import (
    setup_logging,
    set_correlation_id,
    clear_correlation_id,
    get_correlation_context,
    APIException,
    BadRequestError,
    NotFoundError,
    BaseDTO,
    APIResponse,
    PaginatedResponse,
    EventEnvelope,
    LoggingMiddleware,
    create_sync_client,
    create_async_client,
)

def test_correlation_context():
    clear_correlation_id()
    assert get_correlation_context() == {"trace_id": None, "span_id": None}
    
    set_correlation_id("test-trace", "test-span")
    assert get_correlation_context() == {"trace_id": "test-trace", "span_id": "test-span"}
    
    clear_correlation_id()
    assert get_correlation_context() == {"trace_id": None, "span_id": None}

def test_json_logging():
    log_capture = io.StringIO()
    root_logger = logging.getLogger("test_json")
    root_logger.setLevel(logging.INFO)
    
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        
    from am_platform_common.logging import JSONFormatter
    handler = logging.StreamHandler(log_capture)
    handler.setFormatter(JSONFormatter())
    root_logger.addHandler(handler)
    
    set_correlation_id("trace-123", "span-456")
    root_logger.info("Test message", extra={"user_id": "usr_999"})
    
    output = log_capture.getvalue().strip()
    log_data = json.loads(output)
    
    assert log_data["message"] == "Test message"
    assert log_data["level"] == "INFO"
    assert log_data["logger"] == "test_json"
    assert log_data["trace_id"] == "trace-123"
    assert log_data["span_id"] == "span-456"
    assert log_data["user_id"] == "usr_999"
    assert "timestamp" in log_data
    
    clear_correlation_id()

def test_exceptions():
    exc = NotFoundError("User not found", details={"id": "usr_1"})
    assert exc.status_code == 404
    assert exc.error_code == "NOT_FOUND"
    assert exc.message == "User not found"
    assert exc.details == {"id": "usr_1"}
    
    d = exc.to_dict()
    assert d["error_code"] == "NOT_FOUND"
    assert d["message"] == "User not found"
    assert d["details"] == {"id": "usr_1"}

def test_pydantic_models():
    class DummyDTO(BaseDTO):
        name: str
        value: int
        
    response = APIResponse(data=DummyDTO(name="test", value=42))
    assert response.data.name == "test"
    assert response.data.value == 42
    
    paginated = PaginatedResponse(
        items=[DummyDTO(name="a", value=1), DummyDTO(name="b", value=2)],
        total=2,
        page=1,
        size=10,
        pages=1
    )
    assert len(paginated.items) == 2
    assert paginated.total == 2
    
    envelope = EventEnvelope(
        event_type="am.test.event.v1",
        producer="test-service",
        tenant_id="tenant-xyz",
        correlation_id="corr-99",
        idempotency_key="biz-key-1",
        payload=DummyDTO(name="payload", value=100)
    )
    assert envelope.event_type == "am.test.event.v1"
    assert envelope.payload.name == "payload"
    assert isinstance(envelope.event_id, type(uuid4()))
    
    serialized = envelope.model_dump_json()
    assert "am.test.event.v1" in serialized
    assert "occurred_at" in serialized

def test_logging_middleware():
    app = FastAPI()
    app.add_middleware(LoggingMiddleware)

    @app.get("/test")
    def get_test():
        # Get active correlation context inside request handler
        ctx = get_correlation_context()
        return {"trace_id": ctx["trace_id"], "span_id": ctx["span_id"]}

    client = TestClient(app)
    
    # Test request with pre-set trace headers
    response = client.get("/test", headers={"X-Trace-ID": "custom-trace-id"})
    assert response.status_code == 200
    
    data = response.json()
    assert data["trace_id"] == "custom-trace-id"
    assert data["span_id"] is not None
    assert response.headers["X-Trace-ID"] == "custom-trace-id"
    assert response.headers["X-Span-ID"] == data["span_id"]
    
    # Verify that context variables are cleared after request finishes
    assert get_correlation_context() == {"trace_id": None, "span_id": None}

def test_http_client_hooks():
    # Setup log capturer
    log_capture = io.StringIO()
    client_logger = logging.getLogger("am_platform_common.http_client")
    client_logger.setLevel(logging.INFO)
    
    for handler in client_logger.handlers[:]:
        client_logger.removeHandler(handler)
        
    handler = logging.StreamHandler(log_capture)
    client_logger.addHandler(handler)

    # Set correlation ID for context propagation
    set_correlation_id("client-trace-101", "client-span-202")

    # Handler mock transport returning 200 OK
    def mock_handler(request: httpx.Request) -> httpx.Response:
        # Assert trace headers are automatically injected into outgoing call
        assert request.headers.get("X-Trace-ID") == "client-trace-101"
        assert request.headers.get("X-Span-ID") is not None
        return httpx.Response(200, json={"status": "ok"})

    transport = httpx.MockTransport(mock_handler)
    
    # Test sync client
    with create_sync_client(transport=transport) as client:
        resp = client.get("http://external-api.com/v1/data")
        assert resp.status_code == 200

    logs = log_capture.getvalue()
    assert "Outgoing API Request: GET http://external-api.com/v1/data" in logs
    assert "Outgoing API Response: GET http://external-api.com/v1/data - Status: 200" in logs

    clear_correlation_id()
