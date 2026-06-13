.PHONY: run test lint format clean

run:
	uvicorn app.main:app --host 0.0.0.0 --port 8120 --reload

test:
	pytest tests/

lint:
	black --check app/ tests/
	isort --check-only app/ tests/

format:
	black app/ tests/
	isort app/ tests/

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
