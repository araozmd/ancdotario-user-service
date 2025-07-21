# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Service Overview

This is the **User Service** microservice for the Anecdotario platform - a serverless AWS Lambda service that manages user accounts, authentication, and certification systems. Built with Python 3.12 LTS and deployed using AWS SAM (Serverless Application Model).

## Architecture

### Technology Stack
- **Runtime**: Python 3.12 LTS on AWS Lambda
- **Database**: DynamoDB with PynamoDB ORM (v6.0.0+)
- **Testing**: pytest test framework
- **Deployment**: AWS SAM (Serverless Application Model)
- **API**: AWS API Gateway with Lambda Proxy Integration

### File Structure
```
hello-world/          # Lambda function code (self-contained)
  app.py             # Main Lambda handler
  models/            # DynamoDB models
    __init__.py      # Package initialization
    user.py          # User model with PynamoDB
  tests/unit/        # Unit tests with pytest
    test_handler.py  # Lambda handler tests
  requirements.txt   # Function dependencies
template.yaml        # SAM template for AWS resources
samconfig.toml       # SAM deployment configuration
```

## Data Model

### User Schema
The User model (`hello-world/models/user.py`) includes:
- **id**: Primary key (hash key)
- **name**: Required field
- **email**: Required field with global secondary index
- **is_certified**: Boolean with global index for certification queries
- **created_at**: Timestamp with global index
- **profile_image**: Optional profile image URL

### Global Secondary Indexes
- `email-index`: For user lookup by email
- `certified-index`: For querying certified users
- `created-at-index`: For chronological user queries

## Common Development Commands

### Building and Testing
```bash
# Build the service
sam build

# Run unit tests
cd hello-world/
pip install -r requirements.txt
pytest tests/unit/

# Test single function locally
sam local invoke HelloWorldFunction --event events/event.json

# Start local API (port 3000)
sam local start-api
curl http://localhost:3000/hello
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
1. **Lambda Handler**: Main business logic in `hello-world/app.py` with type hints
2. **Models**: DynamoDB schemas in `hello-world/models/` using PynamoDB
3. **Tests**: Unit tests in `hello-world/tests/unit/` using pytest
4. **API Configuration**: Routes defined in `template.yaml` Events section

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