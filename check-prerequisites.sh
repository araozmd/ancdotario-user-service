#!/bin/bash

# Check Prerequisites for CodePipeline Deployment
set -e

echo "🔍 Checking prerequisites for CodePipeline deployment..."
echo ""

# Check AWS CLI
if command -v aws &> /dev/null; then
    echo "✅ AWS CLI installed: $(aws --version)"
else
    echo "❌ AWS CLI not found. Please install: https://aws.amazon.com/cli/"
    exit 1
fi

# Check AWS credentials
if aws sts get-caller-identity &> /dev/null; then
    ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
    USER_ARN=$(aws sts get-caller-identity --query Arn --output text)
    echo "✅ AWS credentials configured"
    echo "   Account ID: $ACCOUNT_ID"
    echo "   User/Role: $USER_ARN"
else
    echo "❌ AWS credentials not configured. Run: aws configure"
    exit 1
fi

# Check default region
DEFAULT_REGION=$(aws configure get region)
if [ -n "$DEFAULT_REGION" ]; then
    echo "✅ Default region set: $DEFAULT_REGION"
else
    echo "⚠️  No default region set. Using us-east-1"
fi

# Check required permissions (basic test)
echo ""
echo "🔐 Testing required AWS permissions..."

# Test CloudFormation permissions
if aws cloudformation list-stacks --max-items 1 &> /dev/null; then
    echo "✅ CloudFormation access confirmed"
else
    echo "❌ CloudFormation access denied"
    exit 1
fi

# Test CodePipeline permissions
if aws codepipeline list-pipelines --max-items 1 &> /dev/null; then
    echo "✅ CodePipeline access confirmed"
else
    echo "❌ CodePipeline access denied"
    exit 1
fi

# Test CodeBuild permissions
if aws codebuild list-projects --max-items 1 &> /dev/null; then
    echo "✅ CodeBuild access confirmed"
else
    echo "❌ CodeBuild access denied"
    exit 1
fi

# Test S3 permissions
if aws s3 ls &> /dev/null; then
    echo "✅ S3 access confirmed"
else
    echo "❌ S3 access denied"
    exit 1
fi

# Check if stack already exists
STACK_NAME="anecdotario-user-service-pipeline"
if aws cloudformation describe-stacks --stack-name "$STACK_NAME" &> /dev/null; then
    STACK_STATUS=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" --query 'Stacks[0].StackStatus' --output text)
    echo ""
    echo "⚠️  Stack '$STACK_NAME' already exists with status: $STACK_STATUS"
    echo "   To update: aws cloudformation update-stack ..."
    echo "   To delete: aws cloudformation delete-stack --stack-name $STACK_NAME"
else
    echo "✅ Stack name '$STACK_NAME' available"
fi

# Check SAM configuration files
echo ""
echo "📋 Checking SAM configuration files..."

CONFIG_FILES=("samconfig-dev.toml" "samconfig-staging.toml" "samconfig-prod.toml")
for config in "${CONFIG_FILES[@]}"; do
    if [ -f "$config" ]; then
        echo "✅ Found: $config"
    else
        echo "❌ Missing: $config"
        exit 1
    fi
done

# Check repository status
echo ""
echo "📦 Checking repository status..."

if git status --porcelain | grep -q .; then
    echo "⚠️  Repository has uncommitted changes"
    echo "   Consider committing changes before deployment"
else
    echo "✅ Repository is clean"
fi

CURRENT_BRANCH=$(git branch --show-current)
echo "✅ Current branch: $CURRENT_BRANCH"

if [ "$CURRENT_BRANCH" != "main" ]; then
    echo "⚠️  You're not on the main branch"
    echo "   Pipeline is configured to track 'main' branch"
fi

echo ""
echo "🎯 Prerequisites check complete!"
echo ""
echo "📋 Next steps:"
echo "1. Create GitHub Personal Access Token:"
echo "   https://github.com/settings/tokens"
echo "   Required scopes: repo, admin:repo_hook"
echo ""
echo "2. Deploy pipeline:"
echo "   ./deploy-pipeline.sh YOUR_GITHUB_TOKEN"
echo ""
echo "3. Monitor deployment:"
echo "   aws cloudformation describe-stacks --stack-name $STACK_NAME"