# Anecdotario User Service

A serverless AWS Lambda microservice for managing user accounts, authentication, and certification in the Anecdotario platform. Built with Python 3.12 LTS and deployed using AWS SAM.

## 🏗️ Architecture

- **Runtime**: Python 3.12 LTS (AWS Lambda)
- **Database**: DynamoDB with PynamoDB ORM
- **API**: AWS API Gateway with Lambda Proxy Integration
- **Testing**: pytest framework
- **Deployment**: AWS SAM (Serverless Application Model)

## 📁 Project Structure

```
hello-world/          # Lambda function code (self-contained)
├── app.py           # Main Lambda handler
├── models/          # DynamoDB models  
│   ├── __init__.py
│   └── user.py      # User model with PynamoDB
├── tests/unit/      # Unit tests with pytest
│   └── test_handler.py
└── requirements.txt # Python dependencies

events/              # Test events for local invocation
template.yaml        # SAM template defining AWS resources
samconfig-*.toml     # Environment-specific SAM configurations
```

## 🐍 Python Setup

This project uses **Python 3.12 LTS** for maximum compatibility and long-term support.

### Prerequisites

1. **Install pyenv** (if not already installed):
   ```bash
   # macOS
   brew install pyenv
   
   # Add to your shell profile (.bashrc, .zshrc, etc.)
   export PATH="$HOME/.pyenv/bin:$PATH"
   eval "$(pyenv init -)"
   ```

2. **Install Python 3.12.8**:
   ```bash
   pyenv install 3.12.8
   ```

3. **Set Python version for this project**:
   ```bash
   cd anecdotario-user-service/
   pyenv local 3.12.8  # Uses .python-version file
   python --version     # Should show Python 3.12.8
   ```

### Installing Dependencies

```bash
# Production dependencies
cd hello-world/
pip install -r requirements.txt

# Development dependencies (for code quality tools)
pip install -r requirements-dev.txt

# Install pre-commit hooks
pre-commit install
```

## 🚀 Quick Start

### Prerequisites

- [Python 3.12.8](https://www.python.org/downloads/) (via pyenv)
- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-install.html)
- [Docker](https://hub.docker.com/search/?type=edition&offering=community) (for local testing)
- [AWS CLI](https://aws.amazon.com/cli/) (configured with credentials)

### Local Development

1. **Setup Python environment**:
   ```bash
   pyenv install 3.12.8
   pyenv local 3.12.8
   ```

2. **Install dependencies**:
   ```bash
   cd hello-world/
   pip install -r requirements.txt
   ```

3. **Run code quality checks**:
   ```bash
   # Run all quality checks
   make quality
   
   # Or run individually
   make lint          # Linting with ruff
   make format        # Code formatting with black
   make type-check    # Type checking with mypy
   make test          # Unit tests
   make test-cov      # Tests with coverage
   ```

4. **Build the application**:
   ```bash
   sam build
   ```

5. **Test locally**:
   ```bash
   # Start local API
   sam local start-api
   
   # Test the endpoint
   curl http://localhost:3000/hello
   ```

## 🚀 Deployment

This service supports **multi-environment deployments** with separate configurations for development, staging, and production.

### Environment-Specific Deployment

#### Development Environment
```bash
sam build
sam deploy --config-file samconfig-dev.toml
```

#### Staging Environment  
```bash
sam build
sam deploy --config-file samconfig-staging.toml
```

#### Production Environment
```bash
sam build
sam deploy --config-file samconfig-prod.toml
```

### Environment Resources

Each environment creates:
- **Stack**: `user-service-{env}` (e.g., `user-service-dev`)
- **DynamoDB Table**: `Users-{env}` (e.g., `Users-dev`)
- **Lambda Function**: Environment-specific with proper IAM permissions
- **API Gateway**: Separate endpoints per environment

### First-Time Deployment

For first-time deployment to any environment:

1. **Configure AWS credentials**:
   ```bash
   aws configure
   ```

2. **Deploy to development** (recommended first):
   ```bash
   sam build
   sam deploy --config-file samconfig-dev.toml
   ```

3. **Test the deployment**:
   ```bash
   # Get the API endpoint from CloudFormation outputs
   aws cloudformation describe-stacks \
     --stack-name user-service-dev \
     --query 'Stacks[0].Outputs[?OutputKey==`UserServiceApi`].OutputValue' \
     --output text
   ```

## 🧪 Testing

### Unit Tests
```bash
# Run unit tests
make test

# Run with coverage report
make test-cov

# Run specific test file
cd hello-world/
pytest tests/unit/test_validation.py -v
```

### Integration Tests
```bash
# Run integration tests (requires running API)
cd hello-world/
pytest tests/integration/ -v -m integration

# Run slow integration tests
pytest tests/integration/ -v -m "integration and slow"
```

### Local Function Testing
```bash
# Test Lambda function directly
sam local invoke HelloWorldFunction --event events/event.json

# Test with custom event
echo '{"httpMethod":"GET","path":"/hello"}' | sam local invoke HelloWorldFunction
```

### Local API Testing
```bash
# Start local API server
make local-api
# OR
sam local start-api

# Test endpoints
curl http://localhost:3000/hello

# Test user creation endpoint
curl -X POST http://localhost:3000/users \
  -H "Content-Type: application/json" \
  -d '{"name":"Test User","email":"test@example.com"}'
```

### Code Quality
```bash
# Run all quality checks
make quality

# Format code
make format

# Check linting
make lint

# Type checking
make type-check
```

## 📊 Monitoring & Logs

### View Logs
```bash
# Development environment
sam logs -n HelloWorldFunction --stack-name user-service-dev --tail

# Production environment  
sam logs -n HelloWorldFunction --stack-name user-service-prod --tail
```

### CloudWatch Logs
Each environment has separate log groups:
- `/aws/lambda/user-service-dev-HelloWorldFunction-*`
- `/aws/lambda/user-service-staging-HelloWorldFunction-*`
- `/aws/lambda/user-service-prod-HelloWorldFunction-*`

## 🗃️ Database Schema

### User Model
The service manages users with the following attributes:

- **id**: Primary key (UUID)
- **name**: User's display name
- **email**: Email address (globally unique)
- **is_certified**: Certification status (boolean)
- **profile_image**: Optional profile image URL
- **created_at**: Account creation timestamp
- **updated_at**: Last modification timestamp

### DynamoDB Global Secondary Indexes
- **email-index**: Fast user lookup by email
- **certified-index**: Query certified users with date range
- **created-at-index**: Chronological user queries

## 🧹 Cleanup

### Delete Environment Stacks
```bash
# Delete development environment
sam delete --stack-name user-service-dev

# Delete staging environment
sam delete --stack-name user-service-staging

# Delete production environment (USE WITH CAUTION!)
sam delete --stack-name user-service-prod
```

## 🔧 Development Tools

### Recommended IDEs
- **VS Code** with AWS Toolkit extension
- **PyCharm** with AWS Toolkit plugin
- **IntelliJ IDEA** with AWS Toolkit plugin

### Useful Commands
```bash
# Validate SAM template
sam validate

# Check Python code style
cd hello-world/
python -m py_compile app.py models/user.py

# Format code (if using black)
pip install black
black app.py models/ tests/
```

## 📚 Resources

- [AWS SAM Developer Guide](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/what-is-sam.html)
- [PynamoDB Documentation](https://pynamodb.readthedocs.io/)
- [AWS Lambda Python Runtime](https://docs.aws.amazon.com/lambda/latest/dg/lambda-python.html)
- [pytest Documentation](https://docs.pytest.org/)
