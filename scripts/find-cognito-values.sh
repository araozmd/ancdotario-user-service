#!/bin/bash

# Script to help find Cognito User Pool values
# Usage: ./find-cognito-values.sh [aws-profile] [region]

AWS_PROFILE=${1:-default}
AWS_REGION=${2:-us-east-1}

echo "🔍 Finding Cognito User Pool information..."
echo "📍 AWS Profile: ${AWS_PROFILE}"
echo "📍 AWS Region: ${AWS_REGION}"
echo ""

# List User Pools
echo "📋 Available User Pools in ${AWS_REGION}:"
aws cognito-idp list-user-pools \
    --profile "${AWS_PROFILE}" \
    --region "${AWS_REGION}" \
    --max-items 20 \
    --query 'UserPools[*].[Id,Name]' \
    --output table

echo ""
echo "💡 To get details for a specific User Pool, enter the Pool ID:"
read -p "User Pool ID (or press Enter to skip): " POOL_ID

if [ -n "$POOL_ID" ]; then
    echo ""
    echo "📊 User Pool Details:"
    aws cognito-idp describe-user-pool \
        --profile "${AWS_PROFILE}" \
        --region "${AWS_REGION}" \
        --user-pool-id "${POOL_ID}" \
        --query 'UserPool.{Id:Id,Name:Name,Domain:Domain,CreationDate:CreationDate}' \
        --output table
    
    echo ""
    echo "📱 App Clients for this User Pool:"
    aws cognito-idp list-user-pool-clients \
        --profile "${AWS_PROFILE}" \
        --region "${AWS_REGION}" \
        --user-pool-id "${POOL_ID}" \
        --query 'UserPoolClients[*].[ClientId,ClientName]' \
        --output table
    
    echo ""
    echo "💡 To get App Client details, enter the Client ID:"
    read -p "App Client ID (or press Enter to skip): " CLIENT_ID
    
    if [ -n "$CLIENT_ID" ]; then
        echo ""
        echo "📱 App Client Details:"
        aws cognito-idp describe-user-pool-client \
            --profile "${AWS_PROFILE}" \
            --region "${AWS_REGION}" \
            --user-pool-id "${POOL_ID}" \
            --client-id "${CLIENT_ID}" \
            --query 'UserPoolClient.{ClientId:ClientId,ClientName:ClientName,GenerateSecret:GenerateSecret,ExplicitAuthFlows:ExplicitAuthFlows}' \
            --output table
    fi
    
    echo ""
    echo "✅ Values for your configuration:"
    echo "   COGNITO_USER_POOL_ID: ${POOL_ID}"
    [ -n "$CLIENT_ID" ] && echo "   COGNITO_APP_CLIENT_ID: ${CLIENT_ID}"
    echo "   AWS_REGION: ${AWS_REGION}"
    
    echo ""
    echo "🚀 Run this to set up parameters:"
    echo "   ./scripts/setup-parameters.sh dev ${AWS_PROFILE}"

else
    echo ""
    echo "💡 You can also find these values in the AWS Console:"
    echo "   1. Go to AWS Cognito → User Pools"
    echo "   2. Click on your User Pool"
    echo "   3. Copy the 'User Pool ID' from the General Settings"
    echo "   4. Go to 'App clients' tab to find App Client IDs"
fi

echo ""
echo "📖 For more information:"
echo "   - User Pool ID format: us-east-1_xxxxxxxxx"
echo "   - App Client ID format: alphanumeric string"
echo "   - Region must match where your User Pool is located"