#!/bin/bash
# Comprehensive coverage report for all user-service functions

echo "📊 USER SERVICE - CODE COVERAGE ANALYSIS"
echo "========================================"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}🔍 Analyzing all Lambda functions...${NC}"
echo ""

# Find all function directories
FUNCTIONS=($(find . -maxdepth 1 -type d -name '*-*' | grep -E '\./[a-z-]+$' | sed 's|./||' | sort))

TOTAL_FUNCTIONS=0
FUNCTIONS_WITH_TESTS=0
TOTAL_TEST_FUNCTIONS=0
TOTAL_SOURCE_LINES=0
TOTAL_TEST_LINES=0

echo "Function                Tests   Test Funcs   Source Lines   Est. Coverage"
echo "--------------------------------------------------------------------------"

for func in "${FUNCTIONS[@]}"; do
    if [ -f "$func/app.py" ]; then
        TOTAL_FUNCTIONS=$((TOTAL_FUNCTIONS + 1))
        
        # Get metrics
        SOURCE_LINES=$(find $func -name "*.py" -not -path "*/tests/*" | xargs wc -l 2>/dev/null | tail -n1 | awk '{print $1}' || echo "0")
        
        if [ -d "$func/tests" ]; then
            TEST_LINES=$(find $func/tests -name "*.py" | xargs wc -l 2>/dev/null | tail -n1 | awk '{print $1}' || echo "0")
            TEST_FUNCS=$(grep -r "def test_" $func/tests/ 2>/dev/null | wc -l || echo "0")
            FUNCTIONS_WITH_TESTS=$((FUNCTIONS_WITH_TESTS + 1))
            STATUS="✅"
            
            # Estimate coverage
            if [ $TEST_FUNCS -eq 0 ]; then
                EST_COV="0%"
                STATUS="❌"
            elif [ $SOURCE_LINES -gt 0 ]; then
                # Rough estimation: more test functions = better coverage
                MAIN_FUNCS=$(grep -n "def [a-z_]*(" $func/*.py 2>/dev/null | wc -l || echo "1")
                EST_COV_NUM=$((TEST_FUNCS * 25))
                if [ $EST_COV_NUM -gt 100 ]; then EST_COV_NUM=100; fi
                EST_COV="${EST_COV_NUM}%"
                
                if [ $EST_COV_NUM -lt 60 ]; then
                    STATUS="⚠️"
                fi
            else
                EST_COV="N/A"
            fi
        else
            TEST_LINES=0
            TEST_FUNCS=0
            EST_COV="0%"
            STATUS="❌"
        fi
        
        TOTAL_SOURCE_LINES=$((TOTAL_SOURCE_LINES + SOURCE_LINES))
        TOTAL_TEST_LINES=$((TOTAL_TEST_LINES + TEST_LINES))
        TOTAL_TEST_FUNCTIONS=$((TOTAL_TEST_FUNCTIONS + TEST_FUNCS))
        
        printf "%-20s %s %4d     %6d       %6d         %s\n" "$func" "$STATUS" "$TEST_FUNCS" "$SOURCE_LINES" "$EST_COV"
    fi
done

echo "--------------------------------------------------------------------------"
printf "%-20s     %4d     %6d       %6d\n" "TOTALS" "$TOTAL_TEST_FUNCTIONS" "$TOTAL_SOURCE_LINES"

echo ""
echo -e "${BLUE}📈 SUMMARY STATISTICS${NC}"
echo "===================="
echo "Total Lambda functions: $TOTAL_FUNCTIONS"
echo "Functions with tests: $FUNCTIONS_WITH_TESTS"
echo "Functions without tests: $((TOTAL_FUNCTIONS - FUNCTIONS_WITH_TESTS))"
echo "Total test functions: $TOTAL_TEST_FUNCTIONS"
echo "Total source lines: $TOTAL_SOURCE_LINES"
echo "Total test lines: $TOTAL_TEST_LINES"

# Calculate coverage percentage
if [ $TOTAL_FUNCTIONS -gt 0 ]; then
    TEST_COVERAGE_PERCENT=$(echo "scale=1; ($FUNCTIONS_WITH_TESTS * 100) / $TOTAL_FUNCTIONS" | bc -l 2>/dev/null || echo "0")
    echo "Test coverage: ${TEST_COVERAGE_PERCENT}% of functions have tests"
fi

if [ $TOTAL_SOURCE_LINES -gt 0 ]; then
    TEST_RATIO=$(echo "scale=1; ($TOTAL_TEST_LINES * 100) / $TOTAL_SOURCE_LINES" | bc -l 2>/dev/null || echo "0")
    echo "Test-to-source ratio: ${TEST_RATIO}%"
fi

echo ""
echo -e "${BLUE}🎯 COVERAGE QUALITY ASSESSMENT${NC}"
echo "==============================="

if [ $FUNCTIONS_WITH_TESTS -eq $TOTAL_FUNCTIONS ]; then
    echo -e "${GREEN}🟢 EXCELLENT: All functions have test coverage${NC}"
elif [ $FUNCTIONS_WITH_TESTS -ge $((TOTAL_FUNCTIONS * 80 / 100)) ]; then
    echo -e "${YELLOW}🟡 GOOD: Most functions have test coverage${NC}"
else
    echo -e "${RED}🔴 NEEDS IMPROVEMENT: Many functions lack tests${NC}"
fi

if [ $TOTAL_TEST_FUNCTIONS -ge $((TOTAL_FUNCTIONS * 3)) ]; then
    echo -e "${GREEN}🟢 EXCELLENT: Comprehensive test suite${NC}"
elif [ $TOTAL_TEST_FUNCTIONS -ge $((TOTAL_FUNCTIONS * 2)) ]; then
    echo -e "${YELLOW}🟡 GOOD: Adequate test coverage${NC}"
else
    echo -e "${RED}🔴 NEEDS IMPROVEMENT: Insufficient test coverage${NC}"
fi

echo ""
echo -e "${BLUE}📝 RECOMMENDATIONS${NC}"
echo "=================="

if [ $FUNCTIONS_WITH_TESTS -lt $TOTAL_FUNCTIONS ]; then
    echo "• Add tests to functions without coverage"
    for func in "${FUNCTIONS[@]}"; do
        if [ -f "$func/app.py" ] && [ ! -d "$func/tests" ]; then
            echo "  - $func (no tests directory)"
        fi
    done
fi

if [ $TOTAL_TEST_FUNCTIONS -lt $((TOTAL_FUNCTIONS * 2)) ]; then
    echo "• Add more test cases for better coverage"
    echo "• Aim for at least 2-3 tests per function"
fi

echo "• Target: 80%+ code coverage for each function"
echo "• Include both happy path and error cases"
echo "• Mock AWS services for reliable testing"

echo ""
echo -e "${GREEN}🚀 TO GET EXACT COVERAGE:${NC}"
echo "1. Authenticate with CodeArtifact:"
echo "   aws codeartifact login --tool pip --repository anecdotario-commons"
echo ""
echo "2. Run comprehensive coverage:"
echo "   ./run_coverage.sh"
echo ""
echo "3. Or check individual function:"
echo "   ./check_function_coverage.sh [function-name]"