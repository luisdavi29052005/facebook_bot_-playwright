
.PHONY: install setup test run clean lint format

# Install dependencies
install:
	pip install -r requirements.txt
	playwright install

# Full setup
setup: install
	@echo "Setup complete! You can now:"
	@echo "  1. Configure .env file"
	@echo "  2. Run 'make test' to verify setup"
	@echo "  3. Run 'make run' to start the bot"

# Run tests
test:
	pytest -v

# Run tests with coverage
test-cov:
	pytest --cov=fb_bot --cov-report=html tests/

# Run the application
run:
	python app.py

# Clean up
clean:
	rm -rf __pycache__ .pytest_cache htmlcov
	find . -name "*.pyc" -delete
	find . -name "*.pyo" -delete

# Lint code
lint:
	ruff check .

# Format code
format:
	ruff format .

# Type check
typecheck:
	mypy fb_bot/

# Validate configuration
check-config:
	python -c "from fb_bot.config import config; is_valid, msg = config.is_valid(); print('✅ Config válida' if is_valid else f'❌ Config inválida: {msg}')"

# Test n8n connection
test-n8n:
	python -c "import asyncio; from fb_bot.n8n_client import healthcheck_n8n; from fb_bot.config import config; print('✅ n8n OK' if asyncio.run(healthcheck_n8n(config.n8n_webhook_url)) else '❌ n8n inacessível')"

# All checks
check: lint typecheck test check-config

# Help
help:
	@echo "Available commands:"
	@echo "  install     - Install dependencies"
	@echo "  setup       - Full setup (install + playwright browsers)"
	@echo "  test        - Run tests"
	@echo "  test-cov    - Run tests with coverage"
	@echo "  run         - Start the application"
	@echo "  clean       - Clean up temporary files"
	@echo "  lint        - Lint code with ruff"
	@echo "  format      - Format code with ruff"
	@echo "  typecheck   - Type check with mypy"
	@echo "  check       - Run all checks (lint + typecheck + test + config)"
	@echo "  help        - Show this help"
