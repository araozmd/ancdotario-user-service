# Makefile for Anecdotario User Service

.PHONY: help install install-dev lint format type-check test test-cov clean build deploy-dev deploy-staging deploy-prod

# Default target
help:
	@echo "Available commands:"
	@echo "  install       Install production dependencies"
	@echo "  install-dev   Install development dependencies"
	@echo "  lint          Run ruff linter"
	@echo "  format        Format code with black"
	@echo "  type-check    Run mypy type checking"
	@echo "  test          Run unit tests"
	@echo "  test-cov      Run tests with coverage report"
	@echo "  quality       Run all code quality checks"
	@echo "  clean         Clean build artifacts"
	@echo "  build         Build SAM application"
	@echo "  deploy-dev    Deploy to development"
	@echo "  deploy-staging Deploy to staging"
	@echo "  deploy-prod   Deploy to production"

# Installation
install:
	cd hello-world && pip install -r requirements.txt

install-dev:
	pip install -r requirements-dev.txt
	cd hello-world && pip install -r requirements.txt
	pre-commit install

# Code quality
lint:
	ruff check hello-world/

format:
	black hello-world/

type-check:
	mypy hello-world/ --exclude hello-world/tests/

test:
	cd hello-world && python -m pytest tests/unit/ -v

test-cov:
	cd hello-world && python -m pytest tests/unit/ -v --cov=. --cov-report=term-missing --cov-report=html

quality: lint type-check test
	@echo "✅ All code quality checks passed!"

# Build and deployment
clean:
	rm -rf .aws-sam/
	rm -rf hello-world/.coverage
	rm -rf hello-world/htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

build:
	sam build

deploy-dev: build
	sam deploy --config-file samconfig-dev.toml

deploy-staging: build
	sam deploy --config-file samconfig-staging.toml

deploy-prod: build
	sam deploy --config-file samconfig-prod.toml

# Local development
local-api:
	sam local start-api --parameter-overrides Environment=dev

local-invoke:
	sam local invoke HelloWorldFunction --event events/event.json