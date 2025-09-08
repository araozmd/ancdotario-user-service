# Health Test Mode Endpoint

## Overview

The Health Test Mode endpoint (`GET /health/test-mode`) provides a way for test suites and monitoring systems to verify that the anecdotario-user-service is running in the correct environment and check overall service health.

## Endpoint Details

- **Path**: `/health/test-mode`
- **Method**: GET
- **Authentication**: None (public health endpoint)
- **Timeout**: 15 seconds
- **Memory**: 128 MB

## Response Format

```json
{
  "service": "anecdotario-user-service",
  "environment": "dev",
  "test_mode": true,
  "health": "ok",
  "timestamp": "2023-12-01T10:00:00Z",
  "version": "CODEBUILD_BUILD_ID=build-123",
  "connectivity": {
    "dynamodb": "connected",
    "s3": "connected"
  }
}
```

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `service` | string | Always "anecdotario-user-service" |
| `environment` | string | Current deployment environment (dev/staging/prod) |
| `test_mode` | boolean | true for dev/staging, false for prod |
| `health` | string | "ok" if all services connected, "degraded" if issues |
| `timestamp` | string | ISO 8601 timestamp of health check |
| `version` | string | Build/version information |
| `connectivity` | object | Status of AWS service connections |
| `connectivity_details` | object | Detailed error info (only when health is "degraded") |

## Test Mode Detection

The endpoint determines test mode based on the environment:

- **Test Mode (true)**: dev, staging, development, test
- **Production Mode (false)**: prod, production

## Health Checking

The endpoint performs connectivity checks to:

1. **DynamoDB**: Uses `DescribeTable` on the Users table
2. **S3**: Uses `HeadBucket` on the photo storage bucket

Health status:
- **"ok"**: All services are accessible
- **"degraded"**: One or more services have connectivity issues

## Local Testing

Run the comprehensive test suite:

```bash
cd health-test-mode
python3 test_local.py
```

## Manual Testing

Test with a mock event:
```bash
sam local invoke HealthTestModeFunction --event ../events/health-test-mode-event.json
```

## Usage in Test Suites

```javascript
// Example test suite usage
const response = await fetch('/health/test-mode');
const health = await response.json();

// Verify running in test environment
assert(health.test_mode === true, 'Not running in test mode!');
assert(health.environment === 'dev', 'Wrong environment!');

// Optionally check service health
if (health.health === 'degraded') {
  console.warn('Service health is degraded:', health.connectivity_details);
}
```

## Security

- No authentication required (safe for public access)
- Only returns service status information
- Does not expose sensitive configuration
- Does not accept any input parameters
- Uses least-privilege IAM permissions

## IAM Permissions

The function requires minimal permissions:
- `dynamodb:DescribeTable` on the Users table
- `s3:HeadBucket` on the photo bucket
- `ssm:GetParameter*` for configuration access

## Deployment

The endpoint is included in the main SAM template and deploys automatically with the service.

## Monitoring

The endpoint is suitable for:
- Health check monitoring systems
- Load balancer health checks  
- Integration test environment verification
- CI/CD pipeline validation