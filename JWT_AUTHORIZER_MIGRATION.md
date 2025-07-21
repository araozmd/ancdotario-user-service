# JWT Authorizer Migration Guide

This guide explains the migration from in-Lambda JWT validation to API Gateway JWT Authorizer.

## Benefits

1. **Performance**: JWT validation happens at API Gateway level, reducing Lambda cold start time and execution duration
2. **Cost**: Lower Lambda execution time means reduced costs
3. **Security**: Centralized authentication at the API Gateway level
4. **Consistency**: Single point of authentication configuration

## Configuration

### 1. Ensure SSM Parameters Exist

The Cognito User Pool ID is automatically fetched from SSM Parameter Store. Ensure these parameters exist:
- `/anecdotario/development/cognito/user-pool-id` (for dev environment)
- `/anecdotario/staging/cognito/user-pool-id` (for staging environment)
- `/anecdotario/production/cognito/user-pool-id` (for production environment)

The template automatically resolves the correct parameter based on the environment.

### 2. Deploy the Updated Stack

```bash
# Deploy to development
sam build
sam deploy --config-file samconfig-dev.toml

# Deploy to staging
sam deploy --config-file samconfig-staging.toml

# Deploy to production
sam deploy --config-file samconfig-prod.toml
```

## Architecture Changes

### Before (In-Lambda Validation)
1. Client sends request with JWT token to Lambda
2. Lambda validates JWT token using Cognito JWKS
3. Lambda processes request if valid
4. Each Lambda invocation includes JWT validation overhead

### After (API Gateway Authorizer)
1. Client sends request with JWT token to API Gateway
2. API Gateway validates JWT token using configured Cognito User Pool
3. API Gateway passes validated claims to Lambda in request context
4. Lambda receives pre-validated user information

## Code Changes

### Lambda Functions
- Functions now use `auth_simplified.py` instead of full `auth.py`
- JWT claims are extracted from `event['requestContext']['authorizer']['claims']`
- No need for JWT validation logic in Lambda code
- Reduced dependencies (no need for PyJWT in some functions)

### Backwards Compatibility
The Lambda functions include a fallback mechanism:
```python
try:
    from auth_simplified import get_authenticated_user
except ImportError:
    from auth import validate_request_auth as get_authenticated_user
```

This ensures the functions work with both authentication methods during migration.

## Testing

### Local Testing
When testing locally with `sam local`, you'll need to mock the authorizer context:

```json
{
  "requestContext": {
    "authorizer": {
      "claims": {
        "sub": "user-123",
        "email": "user@example.com",
        "cognito:username": "testuser"
      }
    }
  }
}
```

### API Testing
Test the deployed API with a valid Cognito JWT token:

```bash
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  https://your-api-id.execute-api.region.amazonaws.com/Prod/users/by-nickname/testuser
```

## Rollback

If you need to rollback to in-Lambda validation:
1. Keep the original `auth.py` module
2. The fallback mechanism in Lambda functions will automatically use it
3. Remove the API Gateway authorizer configuration from `template.yaml`

## Performance Metrics

Expected improvements:
- **Cold Start**: ~200-300ms reduction (no JWT library initialization)
- **Warm Execution**: ~50-100ms reduction (no JWT validation)
- **Memory Usage**: ~20-30MB reduction per function
- **Cost**: ~20-30% reduction in Lambda costs