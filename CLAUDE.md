# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Service Overview

This is the **User Service** microservice for the Anecdotario platform - a serverless AWS Lambda service that manages user accounts, photo uploads, and authentication. Built with Python 3.12 LTS and deployed using AWS SAM (Serverless Application Model).

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

### File Structure
```
shared/              # Shared modules for both functions
  config.py          # Configuration management (local .env + Parameter Store)
  models/            # DynamoDB models
    user.py          # User model with PynamoDB
  .env.defaults      # Default configuration values
  .env.{env}         # Environment-specific overrides

photo-upload/        # Photo upload Lambda function
  app.py             # Photo upload handler (POST /users/{userId}/photo)
  requirements.txt   # Dependencies (Pillow, PyJWT, boto3, pynamodb)
  tests/unit/        # Unit tests for photo upload

user-lookup/         # User lookup Lambda function  
  app.py             # User lookup handler (GET /users?nickname={nickname})
  requirements.txt   # Dependencies (pynamodb only)
  tests/unit/        # Unit tests for user lookup

template.yaml        # SAM template with two separate functions
samconfig-*.toml     # SAM deployment configurations per environment
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

## API Endpoints

### Photo Upload Function
- **POST** `/users/{userId}/photo`
- **Headers**: `Authorization: Bearer <cognito-jwt-token>`
- **Body**: JSON with base64 encoded image data and optional nickname
  ```json
  {
    "image": "data:image/jpeg;base64,...",
    "nickname": "optional-for-new-users"
  }
  ```
- **Function**: `PhotoUploadFunction` (512MB memory, 30s timeout)
- **Features**:
  - Validates Cognito JWT token
  - Ensures user can only upload their own photo
  - Optimizes images (max 1920x1080, JPEG quality 85)
  - Creates/updates user record in DynamoDB
  - Returns presigned URL valid for 7 days
  - For new users, nickname is required

### User Lookup Function
- **GET** `/users/{nickname}`
- **Headers**: `Authorization: Bearer <cognito-jwt-token>`
- **Path Parameters**: `nickname` (required, 3-20 characters)
- **Response**: User object with cognito_id, nickname, image_url, and timestamps
- **Function**: `UserLookupFunction` (128MB memory, 5s timeout)
- **Features**:
  - Requires Cognito JWT authentication
  - Lightweight and fast (read-only DynamoDB access)
  - Uses GSI for efficient nickname lookup
  - Returns 404 if user not found
  - Basic nickname validation

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

### Configuration Management

The service uses a **hybrid configuration approach**:
1. **Local .env files** for static application settings
2. **AWS Parameter Store** for environment-specific and sensitive configuration

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