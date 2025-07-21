#!/bin/bash

# Script to set up Parameter Store parameters for the user service
# Usage: ./setup-parameters.sh <environment> [profile]
# Example: ./setup-parameters.sh dev my-aws-profile

set -e

ENVIRONMENT=${1:-dev}
AWS_PROFILE=${2:-default}
PREFIX="/anecdotario/${ENVIRONMENT}/user-service"

echo "Setting up Parameter Store parameters for environment: ${ENVIRONMENT}"
echo "Using AWS profile: ${AWS_PROFILE}"
echo "Parameter prefix: ${PREFIX}"

# Function to put a parameter
put_parameter() {
    local name="$1"
    local value="$2"
    local type="${3:-String}"
    local description="$4"
    
    echo "Setting parameter: ${PREFIX}/${name}"
    
    aws ssm put-parameter \
        --profile "${AWS_PROFILE}" \
        --name "${PREFIX}/${name}" \
        --value "${value}" \
        --type "${type}" \
        --description "${description}" \
        --overwrite \
        --tier Standard
}

# User service specific configuration (stored in SSM)
echo "Setting user service SSM parameters..."
echo ""
echo "ℹ️  Note: Cognito configuration is read from /anecdotario/${ENVIRONMENT}/cognito/"
echo "   Make sure these parameters exist:"
echo "   - /anecdotario/${ENVIRONMENT}/cognito/user-pool-id"
echo "   - /anecdotario/${ENVIRONMENT}/cognito/region"
echo ""

# Optional: Photo bucket name override (usually set by CloudFormation)
read -p "Enter custom S3 bucket name for photos (leave empty for default): " CUSTOM_BUCKET
if [ -n "$CUSTOM_BUCKET" ]; then
    put_parameter "photo-bucket-name" "${CUSTOM_BUCKET}" "String" "Custom S3 bucket name for photo storage"
fi

# Database configuration (if different from CloudFormation defaults)
read -p "Enter custom DynamoDB table name (leave empty for default): " CUSTOM_TABLE
if [ -n "$CUSTOM_TABLE" ]; then
    put_parameter "user-table-name" "${CUSTOM_TABLE}" "String" "Custom DynamoDB table name for users"
fi

# Environment-specific CORS origins (optional override of .env files)
read -p "Enter custom CORS origins (comma-separated, leave empty for .env defaults): " CUSTOM_ORIGINS
if [ -n "$CUSTOM_ORIGINS" ]; then
    put_parameter "allowed-origins" "${CUSTOM_ORIGINS}" "String" "Custom CORS origins for ${ENVIRONMENT}"
fi

echo ""
echo "✅ Parameter Store setup complete for environment: ${ENVIRONMENT}"
echo ""
echo "📋 Summary of created parameters:"
aws ssm get-parameters-by-path \
    --profile "${AWS_PROFILE}" \
    --path "${PREFIX}" \
    --query 'Parameters[*].[Name,Value,Type]' \
    --output table

echo ""
echo "📄 Static configuration is stored in local .env files:"
echo "  - .env.defaults (base configuration)"
echo "  - .env.${ENVIRONMENT} (environment-specific overrides)"
echo ""
echo "🔧 To update SSM parameters later:"
echo "aws ssm put-parameter --name '${PREFIX}/parameter-name' --value 'new-value' --overwrite"
echo ""
echo "🔧 To update static configuration:"
echo "Edit photo-upload/.env.defaults or photo-upload/.env.${ENVIRONMENT}"
echo ""
echo "🗑️  To delete all SSM parameters for this environment:"
echo "aws ssm delete-parameters --names \$(aws ssm get-parameters-by-path --path '${PREFIX}' --query 'Parameters[*].Name' --output text)"