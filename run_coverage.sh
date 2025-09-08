#!/bin/bash
set -e

echo "🔍 Running Code Coverage Analysis for anecdotario-user-service"
echo "=============================================================="

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Create and activate virtual environment
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}🏗️  Creating virtual environment...${NC}"
    python3 -m venv venv
fi

echo -e "${YELLOW}🔄 Activating virtual environment...${NC}"
source venv/bin/activate

# Install dev dependencies
echo -e "${YELLOW}📦 Installing development dependencies...${NC}"
pip install -r requirements-dev.txt

# Create coverage directory
mkdir -p coverage-reports

# Function to run coverage for each Lambda function
run_function_coverage() {
    local func_dir=$1
    local func_name=$(basename $func_dir)
    
    if [ -d "$func_dir/tests" ]; then
        echo -e "${GREEN}🧪 Running coverage for $func_name...${NC}"
        cd $func_dir
        
        # Run pytest with coverage
        python -m pytest tests/ \
            --cov=app \
            --cov=models \
            --cov-report=term-missing \
            --cov-report=html:../coverage-reports/$func_name-html \
            --cov-report=json:../coverage-reports/$func_name-coverage.json \
            --cov-report=lcov:../coverage-reports/$func_name-coverage.lcov \
            -v || echo -e "${RED}❌ Tests failed for $func_name${NC}"
        
        cd ..
    else
        echo -e "${YELLOW}⚠️  No tests found for $func_name${NC}"
    fi
}

# Get all Lambda function directories
echo -e "${YELLOW}🔍 Discovering Lambda functions...${NC}"
LAMBDA_FUNCTIONS=($(find . -maxdepth 1 -type d -name '*-*' | grep -E '\./[a-z-]+$' | sort))

# Run coverage for each function
for func_dir in "${LAMBDA_FUNCTIONS[@]}"; do
    if [ -f "$func_dir/app.py" ]; then
        run_function_coverage $func_dir
    fi
done

# Generate combined coverage report
echo -e "${GREEN}📊 Generating combined coverage report...${NC}"

# Combine all coverage data
python -m coverage combine coverage-reports/*/.coverage* 2>/dev/null || echo "No coverage data to combine"

# Create overall HTML report
python -c "
import json
import os
from pathlib import Path

coverage_files = list(Path('coverage-reports').glob('*-coverage.json'))
total_covered = 0
total_lines = 0
function_stats = {}

print('\\n📋 COVERAGE SUMMARY BY FUNCTION')
print('=' * 50)

for file_path in sorted(coverage_files):
    func_name = file_path.stem.replace('-coverage', '')
    try:
        with open(file_path) as f:
            data = json.load(f)
            covered = data['totals']['covered_lines']
            total = data['totals']['num_statements']
            percentage = (covered / total * 100) if total > 0 else 0
            
            function_stats[func_name] = {
                'covered': covered,
                'total': total,
                'percentage': percentage
            }
            
            total_covered += covered
            total_lines += total
            
            status = '✅' if percentage >= 80 else '⚠️' if percentage >= 60 else '❌'
            print(f'{status} {func_name:<20} {covered:>3}/{total:<3} lines ({percentage:>5.1f}%)')
    except Exception as e:
        print(f'❌ {func_name:<20} Error reading coverage data')

overall_percentage = (total_covered / total_lines * 100) if total_lines > 0 else 0
print('=' * 50)
status = '✅' if overall_percentage >= 80 else '⚠️' if overall_percentage >= 60 else '❌'
print(f'{status} OVERALL COVERAGE    {total_covered:>3}/{total_lines:<3} lines ({overall_percentage:>5.1f}%)')

# Coverage quality assessment
print('\\n🎯 COVERAGE QUALITY ANALYSIS')
print('=' * 30)
if overall_percentage >= 90:
    print('🟢 EXCELLENT - Very high coverage!')
elif overall_percentage >= 80:
    print('🟡 GOOD - Meets target coverage (80%+)')
elif overall_percentage >= 60:
    print('🟠 NEEDS IMPROVEMENT - Below target coverage')
else:
    print('🔴 CRITICAL - Coverage too low, needs immediate attention')

# Functions needing attention
low_coverage = [f for f, stats in function_stats.items() if stats['percentage'] < 80]
if low_coverage:
    print(f'\\n📝 Functions needing more tests: {', '.join(low_coverage)}')
"

# Create coverage badge data
echo -e "${GREEN}🏷️  Generating coverage badge data...${NC}"
python -c "
import json
from pathlib import Path

coverage_files = list(Path('coverage-reports').glob('*-coverage.json'))
total_covered = sum(json.load(open(f))['totals']['covered_lines'] for f in coverage_files)
total_lines = sum(json.load(open(f))['totals']['num_statements'] for f in coverage_files)
percentage = (total_covered / total_lines * 100) if total_lines > 0 else 0

badge_data = {
    'schemaVersion': 1,
    'label': 'coverage',
    'message': f'{percentage:.1f}%',
    'color': 'brightgreen' if percentage >= 80 else 'yellow' if percentage >= 60 else 'red'
}

with open('coverage-reports/coverage-badge.json', 'w') as f:
    json.dump(badge_data, f, indent=2)

print(f'Coverage badge data saved to coverage-reports/coverage-badge.json')
"

echo -e "${GREEN}✅ Coverage analysis complete!${NC}"
echo ""
echo "📁 Reports generated in coverage-reports/:"
echo "   • Individual HTML reports: coverage-reports/{function-name}-html/"
echo "   • JSON reports: coverage-reports/{function-name}-coverage.json"
echo "   • Badge data: coverage-reports/coverage-badge.json"
echo ""
echo "🌐 To view HTML reports:"
echo "   open coverage-reports/{function-name}-html/index.html"
echo ""
echo "📊 Coverage targets:"
echo "   • 🎯 Target: 80%+"
echo "   • 🏆 Excellent: 90%+"