# CLAUDE.md - User Service

This file provides guidance to Claude Code (claude.ai/code) when working with the User Service.

## Service Overview

This is the **User Service** microservice for the Anecdotario platform - a serverless AWS Lambda service that manages user accounts, photo uploads, and authentication. Built with Python 3.12 LTS and deployed using AWS SAM (Serverless Application Model).

## Key Architectural Decisions & Lessons Learned

### 1. API Gateway JWT Authorization (CRITICAL)
- **Decision**: Move JWT validation from Lambda to API Gateway
- **Why**: Eliminates redundant validation code, improves performance, centralizes security
- **Implementation**: Use `AWS::Serverless::Api` with `CognitoJWTAuthorizer`
- **Result**: Lambda functions receive pre-validated claims in `event['requestContext']['authorizer']['claims']`

### 2. CORS Configuration (CRITICAL)
- **Decision**: Handle CORS entirely at API Gateway level
- **Why**: Lambda CORS headers are ignored when using API Gateway authorizers
- **Implementation**: Configure CORS in API Gateway + GatewayResponses for error responses
- **Key Learning**: Must configure `DEFAULT_4XX` gateway response for CORS on auth failures

### 3. Multi-Function Architecture
- **Decision**: Separate Lambda function per endpoint instead of monolithic handler
- **Why**: Better resource optimization, independent scaling, focused responsibilities
- **Pattern**: `photo-upload/`, `user-lookup/`, `user-create/`, etc.
- **Benefit**: Each function has optimized memory/timeout settings

### 4. Hybrid Configuration Management
- **Decision**: Use local .env files + AWS Parameter Store
- **Why**: Separate static config from sensitive/environment-specific values
- **Local**: Application settings, feature flags, default values
- **SSM**: Secrets, environment-specific URLs, resource names

### 5. Shared Module Pattern
- **Decision**: Centralized `shared/` directory for common code
- **Why**: Avoid duplication across Lambda functions
- **Contents**: Configuration, models, auth helpers
- **Deployment**: SAM packages shared code with each function

## Architecture

### Technology Stack
- **Runtime**: Python 3.12 LTS on AWS Lambda
- **Database**: DynamoDB with PynamoDB ORM (v6.0.0+)
- **Storage**: S3 bucket for photo storage (created with stack)
- **Authentication**: AWS Cognito JWT token validation
- **Image Processing**: Pillow for image optimization
- **Testing**: pytest test framework
- **Deployment**: AWS SAM (Serverless Application Model)
- **API**: AWS API Gateway with Lambda Proxy Integration

### Complete File Structure
```
anecdotario-user-service/
├── shared/                      # Shared modules across all functions
│   ├── config.py               # Hybrid configuration manager
│   ├── auth.py                 # Full auth module (legacy/fallback)
│   ├── auth_simplified.py      # Simplified auth for API Gateway
│   ├── models/
│   │   └── user.py            # PynamoDB User model
│   ├── .env.defaults          # Default configuration
│   └── .env.{env}             # Environment overrides
│
├── photo-upload/               # POST /users/{userId}/photo
│   ├── app.py                 # Handler with image processing
│   ├── requirements.txt       # Pillow, boto3, pynamodb
│   └── tests/unit/
│
├── photo-delete/               # DELETE /users/{userId}/photo
│   ├── app.py                 # Handler for photo deletion
│   ├── requirements.txt
│   └── tests/unit/
│
├── photo-refresh/              # GET /users/{userId}/photo/refresh
│   ├── app.py                 # Presigned URL regeneration
│   ├── requirements.txt
│   └── tests/unit/
│
├── user-create/                # POST /users
│   ├── app.py                 # User registration handler
│   ├── requirements.txt
│   └── tests/unit/
│
├── user-delete/                # DELETE /users/{userId}
│   ├── app.py                 # User deletion with cleanup
│   ├── requirements.txt
│   └── tests/unit/
│
├── user-lookup/                # GET /users/by-nickname/{nickname}
│   ├── app.py                 # Nickname search handler
│   ├── requirements.txt
│   └── tests/unit/
│
├── pipeline/                   # CI/CD Configuration
│   ├── buildspec.yml          # Main build specification
│   ├── deploy-dev-buildspec.yml
│   ├── deploy-staging-buildspec.yml
│   ├── deploy-prod-buildspec.yml
│   └── pipeline-template.yaml # CodePipeline CloudFormation
│
├── events/                     # Test events for local testing
│   ├── photo-upload-event.json
│   └── user-lookup-event.json
│
├── template.yaml              # SAM template (API + Functions)
├── samconfig-dev.toml         # Development configuration
├── samconfig-staging.toml     # Staging configuration
├── samconfig-prod.toml        # Production configuration
├── deploy-pipeline.sh         # Pipeline deployment script
└── .python-version           # Python 3.12.8 for pyenv
```

## Data Model

### User Schema
The User model (`photo-upload/models/user.py`) includes:
- **cognito_id**: Primary key (hash key) - Cognito user ID (sub)
- **nickname**: Searchable unique nickname
- **image_url**: S3 URL for profile image
- **created_at**: Timestamp when user record was created
- **updated_at**: Timestamp when user record was last updated

### Global Secondary Indexes
- `nickname-index`: For user lookup by nickname (main search field)

## API Endpoints (Complete)

### 1. User Creation
- **POST** `/users`
- **Authorization**: Required (JWT)
- **Body**: `{"nickname": "username"}`
- **Function**: `UserCreateFunction` (128MB, 10s)
- **Response**: 201 with user object

### 2. User Lookup
- **GET** `/users/by-nickname/{nickname}`
- **Authorization**: Required (JWT)
- **Function**: `UserLookupFunction` (128MB, 5s)
- **Response**: 200 with user object or 404

### 3. Photo Upload
- **POST** `/users/{userId}/photo`
- **Authorization**: Required (JWT, must match userId)
- **Body**: `{"image": "data:image/jpeg;base64,..."}`
- **Function**: `PhotoUploadFunction` (512MB, 60s)
- **Features**:
  - Creates 3 image versions (thumbnail, standard, high-res)
  - Cleans up old images automatically
  - Returns presigned URLs for protected images

### 4. Photo Deletion
- **DELETE** `/users/{userId}/photo`
- **Authorization**: Required (JWT, must match userId)
- **Function**: `PhotoDeleteFunction` (256MB, 30s)
- **Features**: Removes all image versions from S3

### 5. Photo URL Refresh
- **GET** `/users/{userId}/photo/refresh`
- **Authorization**: Required (JWT, must match userId)
- **Function**: `PhotoRefreshFunction` (128MB, 10s)
- **Features**: Regenerates expired presigned URLs

### 6. User Deletion
- **DELETE** `/users` or `/users/{userId}`
- **Authorization**: Required (JWT)
- **Function**: `UserDeleteFunction` (256MB, 30s)
- **Features**: Cascading delete of photos and user record

## Common Development Commands

### Building and Testing
```bash
# Build both functions
sam build

# Test photo upload function
cd photo-upload/
pip install -r requirements.txt
pytest tests/unit/

# Test user lookup function  
cd ../user-lookup/
pip install -r requirements.txt
pytest tests/unit/

# Test functions locally
sam local invoke PhotoUploadFunction --event events/photo-event.json
sam local invoke UserLookupFunction --event events/lookup-event.json

# Start local API (port 3000)
sam local start-api
curl -X POST http://localhost:3000/users/123/photo -H "Authorization: Bearer <token>" -d '{"image":"base64-data"}'
curl -H "Authorization: Bearer <token>" http://localhost:3000/users/testuser
```

### Environment-Specific Deployment

#### Development Environment
```bash
# Build and deploy to development
sam build
sam deploy --config-file samconfig-dev.toml

# View logs
sam logs -n HelloWorldFunction --stack-name user-service-dev --tail

# Delete dev stack
sam delete --stack-name user-service-dev
```

#### Staging Environment
```bash
# Build and deploy to staging
sam build
sam deploy --config-file samconfig-staging.toml

# View logs
sam logs -n HelloWorldFunction --stack-name user-service-staging --tail

# Delete staging stack
sam delete --stack-name user-service-staging
```

#### Production Environment
```bash
# Build and deploy to production
sam build
sam deploy --config-file samconfig-prod.toml

# View logs
sam logs -n HelloWorldFunction --stack-name user-service-prod --tail

# Delete production stack (USE WITH CAUTION!)
sam delete --stack-name user-service-prod
```

### Environment Configuration Files
- `samconfig-dev.toml` - Development environment
- `samconfig-staging.toml` - Staging environment  
- `samconfig-prod.toml` - Production environment

Each environment has:
- Separate stack names (user-service-{env})
- Separate DynamoDB tables (Users-{env})
- Environment-specific tags and settings

### Development Workflow
1. **Lambda Handler**: Photo upload logic in `photo-upload/app.py` with JWT validation
2. **Models**: DynamoDB schemas in `photo-upload/models/` using PynamoDB
3. **Tests**: Unit tests in `photo-upload/tests/unit/` using pytest
4. **API Configuration**: Routes defined in `template.yaml` Events section
5. **S3 Integration**: Bucket created/deleted with stack, lifecycle rules configured

### Configuration Management (CRITICAL PATTERN)

The service uses a **hybrid configuration approach** that separates concerns:

#### Configuration Hierarchy
1. **Local .env files** → Static, non-sensitive settings
2. **AWS Parameter Store** → Sensitive/environment-specific values
3. **Environment variables** → Fallback/override mechanism

#### Key Implementation Details
```python
# Configuration priority order:
1. Check local .env cache (fastest)
2. Check SSM Parameter Store cache
3. Fetch from SSM if not cached
4. Fall back to environment variables
5. Use default value if provided
```

#### Local Configuration (.env files)
Static settings stored in version-controlled files:
- `photo-upload/.env.defaults` - Base configuration for all environments
- `photo-upload/.env.{environment}` - Environment-specific overrides

Contains: image processing settings, security rules, feature flags, default CORS origins

#### Parameter Store (SSM)
**Cognito Configuration (Centralized)** under `/anecdotario/{environment}/cognito/`:
- `user-pool-id` (required)
- `region` (required)

**User Service Configuration** under `/anecdotario/{environment}/user-service/`:
- `photo-bucket-name` (optional override)
- `user-table-name` (optional override) 
- `allowed-origins` (optional CORS override)

#### Setup Configuration
```bash
# Ensure Cognito parameters exist (should already be configured)
# /anecdotario/{environment}/cognito/user-pool-id
# /anecdotario/{environment}/cognito/region

# Set up optional user service SSM parameters
./scripts/setup-parameters.sh dev [aws-profile]

# Test complete configuration (local + SSM + Cognito)
python scripts/test-parameters.py dev [aws-profile]

# Edit static configuration
vim photo-upload/.env.defaults
vim photo-upload/.env.dev
```

#### Required Parameters
The service expects these Parameter Store values to exist:
- `/anecdotario/{environment}/cognito/user-pool-id` - Your Cognito User Pool ID
- `/anecdotario/{environment}/cognito/region` - AWS region for Cognito

SAM configuration (samconfig files):
```bash
# In samconfig-dev.toml, samconfig-staging.toml, samconfig-prod.toml
parameter_overrides = [
    "Environment=dev",
    "TableName=Users-dev",
    "ParameterStorePrefix=/anecdotario/dev/user-service"
]
```

### Project Structure Benefits
- **Self-contained**: All Lambda code in one directory
- **No import issues**: Models and handler in same package
- **Easy deployment**: SAM packages everything together
- **Standard Python**: Follows Python package conventions

## Critical Implementation Patterns

### Authentication Pattern (MUST FOLLOW)
```python
# DO NOT validate JWT in Lambda - API Gateway handles it
from auth_simplified import get_authenticated_user, create_response

def lambda_handler(event, context):
    # Get pre-validated claims from API Gateway
    claims, error = get_authenticated_user(event)
    if error:
        return error
    
    user_id = claims['sub']  # Cognito user ID
    # Your business logic here
```

### Error Response Pattern
```python
def create_error_response(status_code, message, event, details=None):
    # CORS headers NOT needed - API Gateway handles them
    return {
        'statusCode': status_code,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps({
            'error': message,
            'statusCode': status_code,
            'details': details
        })
    }
```

### S3 Cleanup Pattern
```python
def cleanup_old_images(user_id, bucket_name):
    """Remove all existing images before uploading new ones"""
    prefix = f"users/{user_id}/"
    objects = s3_client.list_objects_v2(
        Bucket=bucket_name,
        Prefix=prefix
    )
    
    if 'Contents' in objects:
        delete_keys = [{'Key': obj['Key']} for obj in objects['Contents']]
        s3_client.delete_objects(
            Bucket=bucket_name,
            Delete={'Objects': delete_keys}
        )
```

## Key Patterns

### Lambda Response Format
Functions return API Gateway Lambda Proxy format:
```python
{
    'statusCode': 200,
    'headers': {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*'
    },
    'body': json.dumps({'message': 'response'})
}
```

### DynamoDB Integration
- Uses PynamoDB ORM for DynamoDB operations
- Global secondary indexes for efficient queries
- Automatic timestamps with custom save() method
- Model validation and type safety
- Environment-based table configuration

### SAM Configuration
- Stack names: `user-service-{env}` (environment-specific)
- Runtime: `python3.12` (LTS version)
- Architecture: `x86_64`
- Timeout: 3 seconds (global default)

## CI/CD Pipeline Architecture

### Pipeline Stages
1. **Source** - GitHub webhook trigger
2. **Build** - Run tests, package with SAM
3. **Deploy-Dev** - Automatic deployment
4. **Deploy-Staging** - Automatic after dev
5. **Deploy-Production** - Manual approval required

### Key Pipeline Components

#### Build Stage (`pipeline/buildspec.yml`)
- Creates SAM artifact buckets if needed
- Runs pytest for all Lambda functions
- Packages application with SAM
- Outputs `packaged-template.yaml`

#### Deploy Stages
- Each environment has dedicated buildspec
- Uses environment-specific samconfig
- Automatic rollback on failure

### IAM Permissions (LEARNED THE HARD WAY)

CodeBuild role needs extensive permissions:
```yaml
# CloudFormation for stack operations
- cloudformation:*

# Lambda for function management
- lambda:*

# API Gateway for REST API
- apigateway:*

# DynamoDB for tables
- dynamodb:*

# S3 for artifacts AND application buckets
- s3:* on:
  - aws-sam-cli-managed-*
  - anecdotario-sam-artifacts-*
  - user-service-* (app buckets)

# SSM for parameter access
- ssm:GetParameter*

# IAM for role creation
- iam:* on service roles
```

## Testing Strategy

### Unit Test Structure
```python
@pytest.fixture
def api_gateway_event():
    """Event with JWT claims from API Gateway"""
    return {
        "requestContext": {
            "authorizer": {
                "claims": {
                    "sub": "user-123",
                    "email": "test@example.com"
                }
            }
        },
        "pathParameters": {"userId": "user-123"},
        "body": json.dumps({"nickname": "testuser"})
    }

# Mock PynamoDB models
@patch('app.User')
def test_handler(mock_user, api_gateway_event):
    mock_user.get.return_value = Mock(nickname="testuser")
    response = lambda_handler(api_gateway_event, None)
    assert response['statusCode'] == 200
```

### Testing Commands
```bash
# Run all tests with coverage
pytest tests/unit/ -v --cov=app --cov-report=term-missing

# Test specific function locally
sam local invoke UserCreateFunction --event events/create-user.json

# Start local API for integration testing
sam local start-api --env-vars env.json
```

## Deployment Checklist

### Pre-Deployment
- [ ] All tests passing (`pytest`)
- [ ] Configuration in Parameter Store
- [ ] Cognito User Pool configured
- [ ] S3 artifact bucket exists

### Deployment Process
```bash
# First-time setup
aws ssm put-parameter --name "/anecdotario/dev/cognito/user-pool-id" --value "YOUR_POOL_ID"
aws ssm put-parameter --name "/anecdotario/dev/cognito/region" --value "us-east-1"

# Deploy pipeline
./deploy-pipeline.sh YOUR_GITHUB_TOKEN

# Manual deployment to specific environment
sam build
sam deploy --config-file samconfig-dev.toml
```

### Post-Deployment Validation
```bash
# Check stack status
aws cloudformation describe-stacks --stack-name user-service-dev

# View Lambda logs
sam logs -n UserCreateFunction --stack-name user-service-dev --tail

# Test API endpoint
curl -X POST https://API_ID.execute-api.us-east-1.amazonaws.com/Prod/users \
  -H "Authorization: Bearer YOUR_JWT" \
  -H "Content-Type: application/json" \
  -d '{"nickname": "testuser"}'
```

## Common Issues & Solutions

### 1. CORS Errors (Most Common)
**Symptom**: "No 'Access-Control-Allow-Origin' header"
**Solution**: Check API Gateway GatewayResponses configuration
```yaml
GatewayResponses:
  DEFAULT_4XX:  # Critical for auth failures
    ResponseParameters:
      Headers:
        Access-Control-Allow-Origin: "'*'"
```

### 2. JWT Validation Issues
**Symptom**: 401 Unauthorized
**Check**:
- Cognito User Pool ID in Parameter Store
- Token format: `Authorization: Bearer <token>`
- API Gateway Authorizer configuration

### 3. Permission Denied on S3
**Symptom**: AccessDenied on S3 operations
**Solution**: Verify Lambda execution role has S3CrudPolicy

### 4. Parameter Store Access
**Symptom**: ParameterNotFound
**Check**:
- Parameter path: `/anecdotario/{env}/service-name/*`
- Lambda has ssm:GetParameter permission
- Environment variable: PARAMETER_STORE_PREFIX

## Python Version Management

### Setup with pyenv
```bash
# Install Python 3.12 LTS
pyenv install 3.12.8

# Set for this project (uses .python-version file)
pyenv local 3.12.8

# Verify version
python --version  # Should show Python 3.12.8
```

### Why Python 3.12 LTS?
- **Long-term support** until October 2028
- **Performance improvements** over 3.11
- **AWS Lambda support** with python3.12 runtime
- **Stability** for production workloads

## Lessons Learned Summary

1. **API Gateway handles JWT + CORS** - Don't duplicate in Lambda
2. **Multi-function architecture** - Better than monolithic handlers
3. **Hybrid configuration** - Local files + SSM Parameter Store
4. **Clean up resources** - Always delete old S3 objects
5. **Test with mocks** - Use pytest fixtures for API Gateway events
6. **Configure GatewayResponses** - Critical for CORS on errors
7. **Use presigned URLs** - For protected S3 content
8. **Optimize function resources** - Right-size memory/timeout per function
9. **Cache configuration** - Reduce SSM API calls
10. **Document everything** - Future you will thank present you