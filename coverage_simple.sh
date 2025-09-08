#!/bin/bash
# Simple coverage check without external dependencies
# This script works without CodeArtifact authentication

set -e

echo "🔍 Simple Code Coverage Analysis for user-service"
echo "================================================="

FUNCTION_NAME=${1:-"photo-upload"}

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

if [ ! -d "$FUNCTION_NAME" ]; then
    echo -e "${RED}❌ Function directory '$FUNCTION_NAME' not found${NC}"
    echo "Available functions:"
    find . -maxdepth 1 -type d -name '*-*' | grep -E '\./[a-z-]+$' | sed 's|./||' | sort
    exit 1
fi

cd $FUNCTION_NAME

echo -e "${YELLOW}📊 Analyzing code coverage for $FUNCTION_NAME...${NC}"

# Count source lines
echo -e "${YELLOW}📝 Source code analysis:${NC}"
TOTAL_PYTHON_LINES=$(find . -name "*.py" -not -path "./tests/*" | xargs wc -l | tail -n1 | awk '{print $1}')
echo "   Total Python lines: $TOTAL_PYTHON_LINES"

# Count test lines
if [ -d "tests" ]; then
    TEST_LINES=$(find tests -name "*.py" | xargs wc -l | tail -n1 | awk '{print $1}' 2>/dev/null || echo "0")
    echo "   Test lines: $TEST_LINES"
    
    # Count test functions
    TEST_FUNCTIONS=$(grep -r "def test_" tests/ | wc -l 2>/dev/null || echo "0")
    echo "   Test functions: $TEST_FUNCTIONS"
    
    # Calculate test coverage ratio (rough estimate)
    if [ $TOTAL_PYTHON_LINES -gt 0 ]; then
        TEST_RATIO=$(echo "scale=1; ($TEST_LINES * 100) / $TOTAL_PYTHON_LINES" | bc -l 2>/dev/null || echo "0")
        echo "   Test-to-code ratio: ${TEST_RATIO}%"
    fi
else
    echo -e "${RED}   ❌ No tests directory found${NC}"
fi

# Analyze coverage potential
echo -e "${YELLOW}🎯 Coverage Analysis:${NC}"

# Check for main functions
MAIN_FUNCTIONS=$(grep -n "def lambda_handler\|def [a-z_]*(" *.py 2>/dev/null | wc -l || echo "0")
echo "   Functions defined: $MAIN_FUNCTIONS"

# Check for error handling
ERROR_HANDLING=$(grep -n "try:\|except\|raise\|return.*error" *.py 2>/dev/null | wc -l || echo "0")
echo "   Error handling patterns: $ERROR_HANDLING"

# Check for AWS service calls
AWS_CALLS=$(grep -n "boto3\|s3_client\|lambda_client\|dynamo" *.py 2>/dev/null | wc -l || echo "0")
echo "   AWS service calls: $AWS_CALLS"

echo ""
echo -e "${GREEN}📋 Test Coverage Recommendations:${NC}"

if [ ! -d "tests" ]; then
    echo -e "${RED}❌ CRITICAL: No tests directory found${NC}"
    echo "   • Create tests/unit/ directory"
    echo "   • Add test_*.py files"
    echo "   • Target: 80%+ coverage"
elif [ $TEST_FUNCTIONS -eq 0 ]; then
    echo -e "${RED}❌ CRITICAL: No test functions found${NC}"
    echo "   • Add def test_* functions to test files"
    echo "   • Start with happy path tests"
    echo "   • Add error case tests"
else
    echo -e "${GREEN}✅ Tests exist ($TEST_FUNCTIONS functions)${NC}"
    
    if [ $MAIN_FUNCTIONS -gt 0 ] && [ $TEST_FUNCTIONS -lt $((MAIN_FUNCTIONS * 2)) ]; then
        echo -e "${YELLOW}⚠️  Consider adding more test cases${NC}"
        echo "   • Current: $TEST_FUNCTIONS tests for $MAIN_FUNCTIONS functions"
        echo "   • Recommended: At least 2-3 tests per function"
    fi
fi

# Coverage estimation
echo ""
echo -e "${GREEN}🏆 Coverage Quality Estimate:${NC}"

if [ $TEST_FUNCTIONS -eq 0 ]; then
    echo -e "${RED}🔴 CRITICAL (0%): No test coverage${NC}"
elif [ $TEST_FUNCTIONS -lt $((MAIN_FUNCTIONS * 2)) ]; then
    ESTIMATED_COVERAGE=$((TEST_FUNCTIONS * 30))
    if [ $ESTIMATED_COVERAGE -gt 100 ]; then ESTIMATED_COVERAGE=100; fi
    if [ $ESTIMATED_COVERAGE -lt 80 ]; then
        echo -e "${YELLOW}🟡 NEEDS WORK (~${ESTIMATED_COVERAGE}%): Below target${NC}"
    else
        echo -e "${GREEN}🟢 GOOD (~${ESTIMATED_COVERAGE}%): Likely meets target${NC}"
    fi
else
    echo -e "${GREEN}🟢 EXCELLENT: Comprehensive test coverage likely${NC}"
fi

echo ""
echo -e "${GREEN}🚀 To get exact coverage:${NC}"
echo "1. Fix CodeArtifact authentication:"
echo "   aws codeartifact login --tool pip --repository anecdotario-commons"
echo ""
echo "2. Then run:"
echo "   cd $FUNCTION_NAME"
echo "   python3 -m pytest tests/ --cov=app --cov-report=term-missing"
echo ""
echo "3. Or use the full coverage script:"
echo "   ./run_coverage.sh"