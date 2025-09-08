#!/bin/bash
# Quick coverage check for individual Lambda function
# Usage: ./check_function_coverage.sh [function-name]

set -e

FUNCTION_NAME=$1

if [ -z "$FUNCTION_NAME" ]; then
    echo "Usage: $0 <function-name>"
    echo "Available functions:"
    find . -maxdepth 1 -type d -name '*-*' | grep -E '\./[a-z-]+$' | sed 's|./||' | sort
    exit 1
fi

if [ ! -d "$FUNCTION_NAME" ]; then
    echo "❌ Function directory '$FUNCTION_NAME' not found"
    exit 1
fi

if [ ! -d "$FUNCTION_NAME/tests" ]; then
    echo "⚠️  No tests directory found for $FUNCTION_NAME"
    exit 1
fi

echo "🔍 Running coverage for $FUNCTION_NAME"
echo "======================================"

# Create and activate virtual environment in parent directory
cd /Users/araozmd/repos/anecdotario/anecdotario-backend/anecdotario-user-service

if [ ! -d "venv" ]; then
    echo "🏗️  Creating virtual environment..."
    python3 -m venv venv
fi

echo "🔄 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📦 Installing dependencies..."
pip install pytest pytest-cov coverage moto pytest-mock

cd $FUNCTION_NAME

# Run coverage
python -m pytest tests/ \
    --cov=app \
    --cov=models \
    --cov-report=term-missing \
    --cov-report=html:htmlcov \
    --cov-fail-under=80 \
    -v

echo ""
echo "📊 HTML report generated: $FUNCTION_NAME/htmlcov/index.html"
echo "🎯 Coverage target: 80%"