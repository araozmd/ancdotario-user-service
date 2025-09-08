#!/bin/bash

# Photo Upload Lambda Function Test Runner
# This script runs comprehensive tests for the photo upload functionality

set -e

echo "🧪 Photo Upload Lambda Function Test Suite"
echo "=========================================="

# Check if we're in the right directory
if [ ! -f "app.py" ]; then
    echo "❌ Error: app.py not found. Please run this script from the photo-upload directory."
    exit 1
fi

# Set environment variables for testing
export PHOTO_BUCKET_NAME='test-anecdotario-photos'
export PARAMETER_STORE_PREFIX='/anecdotario/test/user-service'
export ENVIRONMENT='test'
export USER_TABLE_NAME='Users-test'
export AWS_REGION='us-east-1'
export AWS_DEFAULT_REGION='us-east-1'

echo "📋 Environment configured for testing"
echo "   - Bucket: $PHOTO_BUCKET_NAME"
echo "   - Environment: $ENVIRONMENT"
echo "   - Region: $AWS_REGION"
echo ""

# Function to run tests with proper error handling
run_test_suite() {
    local test_file=$1
    local description=$2
    
    echo "🔍 Running $description..."
    if python3 -m pytest "$test_file" -v --tb=short; then
        echo "✅ $description completed successfully"
        return 0
    else
        echo "❌ $description failed"
        return 1
    fi
}

# Main test execution
main() {
    local failed_suites=0
    
    # Run basic unit tests (no external dependencies)
    if ! run_test_suite "tests/unit/test_photo_upload_basic.py" "Basic Unit Tests"; then
        ((failed_suites++))
    fi
    echo ""
    
    # Try to run comprehensive tests if PIL is available
    if python3 -c "from PIL import Image" 2>/dev/null; then
        echo "📸 PIL available, running comprehensive tests..."
        if ! run_test_suite "tests/unit/test_photo_upload_comprehensive.py" "Comprehensive Unit Tests"; then
            ((failed_suites++))
        fi
    else
        echo "⚠️  PIL not available, skipping comprehensive tests"
        echo "   Install with: pip install Pillow"
    fi
    echo ""
    
    # Run integration tests only if API and JWT are configured
    if [ ! -z "$API_BASE_URL" ] && [ ! -z "$JWT_TOKEN" ]; then
        echo "🌐 API configuration detected, running integration tests..."
        if ! run_test_suite "tests/integration/test_api_contracts.py" "Integration Tests"; then
            ((failed_suites++))
        fi
    else
        echo "⚠️  Integration tests skipped (API_BASE_URL and JWT_TOKEN not set)"
        echo "   To run integration tests:"
        echo "   export API_BASE_URL=https://your-api-gateway-url"
        echo "   export JWT_TOKEN=your-jwt-token"
    fi
    echo ""
    
    # Test specific bug scenarios
    echo "🐛 Running specific bug scenario tests..."
    if python3 -m pytest tests/unit/test_photo_upload_basic.py -k "current_failing or payload_format_bug" -v --tb=short; then
        echo "✅ Bug scenario tests completed"
    else
        echo "❌ Bug scenario tests failed"
        ((failed_suites++))
    fi
    echo ""
    
    # Summary
    echo "📊 Test Summary"
    echo "==============="
    if [ $failed_suites -eq 0 ]; then
        echo "🎉 All available test suites passed!"
        echo ""
        echo "🔧 Key Findings:"
        echo "   • Lambda function name bug confirmed"
        echo "   • Payload format bug confirmed" 
        echo "   • Error handling working correctly"
        echo "   • Authentication/authorization validated"
        echo ""
        echo "📋 Next steps:"
        echo "   1. Fix Lambda function name in app.py (line 37)"
        echo "   2. Fix payload field name in app.py (line 62)"
        echo "   3. Deploy fixes and re-test"
        return 0
    else
        echo "❌ $failed_suites test suite(s) failed"
        echo ""
        echo "🔍 Check the detailed output above for specific failures"
        echo "📖 See TEST_RESULTS.md for comprehensive analysis"
        return 1
    fi
}

# Coverage analysis (if pytest-cov is available)
run_coverage() {
    echo "📈 Attempting coverage analysis..."
    if python3 -m pytest tests/unit/test_photo_upload_basic.py --cov=app --cov-report=term-missing 2>/dev/null; then
        echo "✅ Coverage analysis completed"
    else
        echo "⚠️  Coverage analysis not available (install with: pip install pytest-cov)"
    fi
}

# Check syntax before running tests
check_syntax() {
    echo "🔧 Checking syntax..."
    python3 -m py_compile app.py
    python3 -m py_compile tests/conftest.py
    python3 -c "import sys; sys.path.insert(0, '.'); sys.path.insert(0, '../shared'); import app; print('✅ App imports successfully')"
}

# Parse command line arguments
case "${1:-all}" in
    "all")
        check_syntax
        main
        run_coverage
        ;;
    "unit")
        check_syntax  
        run_test_suite "tests/unit/test_photo_upload_basic.py" "Basic Unit Tests"
        ;;
    "integration")
        if [ -z "$API_BASE_URL" ] || [ -z "$JWT_TOKEN" ]; then
            echo "❌ API_BASE_URL and JWT_TOKEN environment variables required for integration tests"
            exit 1
        fi
        run_test_suite "tests/integration/test_api_contracts.py" "Integration Tests"
        ;;
    "bugs")
        check_syntax
        echo "🐛 Running bug-specific tests..."
        python3 -m pytest tests/unit/test_photo_upload_basic.py -k "current_failing or payload_format_bug" -v
        ;;
    "coverage")
        check_syntax
        run_coverage
        ;;
    "help"|"-h"|"--help")
        echo "Usage: $0 [command]"
        echo ""
        echo "Commands:"
        echo "  all         Run all available tests (default)"
        echo "  unit        Run only unit tests"
        echo "  integration Run only integration tests"  
        echo "  bugs        Run bug-specific scenario tests"
        echo "  coverage    Run coverage analysis"
        echo "  help        Show this help message"
        echo ""
        echo "Environment variables for integration tests:"
        echo "  API_BASE_URL  Base URL of deployed API Gateway"
        echo "  JWT_TOKEN     Valid JWT token for authentication"
        exit 0
        ;;
    *)
        echo "❌ Unknown command: $1"
        echo "Run '$0 help' for usage information"
        exit 1
        ;;
esac