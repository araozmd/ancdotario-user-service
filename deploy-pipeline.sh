#!/bin/bash

# Deploy AWS CodePipeline Infrastructure
# Usage: ./deploy-pipeline.sh YOUR_GITHUB_TOKEN

set -e

# Configuration
STACK_NAME="anecdotario-user-service-pipeline"
TEMPLATE_FILE="pipeline/pipeline-template.yaml"
REGION="us-east-1"

# Parameters
GITHUB_OWNER="araozmd"
GITHUB_REPO="ancdotario-user-service"
GITHUB_BRANCH="main"
GITHUB_TOKEN="$1"

if [ -z "$GITHUB_TOKEN" ]; then
    echo "❌ Error: GitHub token is required"
    echo "Usage: $0 YOUR_GITHUB_TOKEN"
    echo ""
    echo "Get your token from: https://github.com/settings/tokens"
    echo "Required scopes: repo, admin:repo_hook"
    exit 1
fi

echo "🚀 Deploying CodePipeline infrastructure..."
echo "Stack Name: $STACK_NAME"
echo "Repository: $GITHUB_OWNER/$GITHUB_REPO"
echo "Branch: $GITHUB_BRANCH"
echo "Region: $REGION"
echo ""

# Deploy CloudFormation stack
aws cloudformation create-stack \
    --stack-name "$STACK_NAME" \
    --template-body "file://$TEMPLATE_FILE" \
    --parameters \
        ParameterKey=GitHubOwner,ParameterValue="$GITHUB_OWNER" \
        ParameterKey=GitHubRepo,ParameterValue="$GITHUB_REPO" \
        ParameterKey=GitHubBranch,ParameterValue="$GITHUB_BRANCH" \
        ParameterKey=GitHubToken,ParameterValue="$GITHUB_TOKEN" \
    --capabilities CAPABILITY_IAM \
    --region "$REGION" \
    --tags \
        Key=Project,Value=Anecdotario \
        Key=Service,Value=UserService \
        Key=Environment,Value=Pipeline

if [ $? -eq 0 ]; then
    echo "✅ Stack creation initiated successfully!"
    echo ""
    echo "📊 Monitor deployment progress:"
    echo "aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION"
    echo ""
    echo "🔗 View in AWS Console:"
    echo "https://console.aws.amazon.com/cloudformation/home?region=$REGION#/stacks/stackinfo?stackId=$STACK_NAME"
    echo ""
    echo "⏳ Waiting for stack creation to complete..."
    
    # Wait for stack creation to complete
    aws cloudformation wait stack-create-complete \
        --stack-name "$STACK_NAME" \
        --region "$REGION"
    
    if [ $? -eq 0 ]; then
        echo ""
        echo "🎉 Pipeline infrastructure deployed successfully!"
        echo ""
        
        # Get pipeline URL
        PIPELINE_URL=$(aws cloudformation describe-stacks \
            --stack-name "$STACK_NAME" \
            --region "$REGION" \
            --query 'Stacks[0].Outputs[?OutputKey==`PipelineUrl`].OutputValue' \
            --output text)
        
        echo "🔗 CodePipeline URL: $PIPELINE_URL"
        echo ""
        echo "📝 Next steps:"
        echo "1. Visit the pipeline URL above"
        echo "2. The pipeline should start automatically"
        echo "3. Monitor the deployment progress"
        echo "4. Approve production deployment when ready"
    else
        echo "❌ Stack creation failed. Check CloudFormation console for details."
        exit 1
    fi
else
    echo "❌ Failed to create stack. Check your AWS credentials and permissions."
    exit 1
fi