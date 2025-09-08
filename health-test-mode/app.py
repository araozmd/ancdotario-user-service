import json
import os
import sys
import boto3
from datetime import datetime, timezone
from botocore.exceptions import ClientError, NoCredentialsError

# Add shared directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))
from config import config

# Response utility functions (no auth required for health check)
def create_response(status_code: int, body: str) -> dict:
    """Create a Lambda response for health endpoint - no auth required"""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json'
        },
        'body': body
    }


def create_error_response(status_code: int, message: str, details: dict = None) -> dict:
    """Create an error response for health endpoint"""
    error_body = {
        'error': message,
        'statusCode': status_code
    }
    
    if details:
        error_body['details'] = details
    
    return create_response(status_code, json.dumps(error_body))


def check_dynamodb_connectivity() -> dict:
    """Test basic DynamoDB connectivity"""
    try:
        # Get table name from environment
        table_name = os.environ.get('USER_TABLE_NAME')
        if not table_name:
            return {
                'status': 'error',
                'message': 'USER_TABLE_NAME environment variable not set'
            }
        
        # Test DynamoDB connection by describing the table
        dynamodb = boto3.client('dynamodb')
        response = dynamodb.describe_table(TableName=table_name)
        
        return {
            'status': 'connected',
            'table_name': table_name,
            'table_status': response['Table']['TableStatus']
        }
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        return {
            'status': 'error',
            'error_code': error_code,
            'message': str(e)
        }
    except NoCredentialsError:
        return {
            'status': 'error',
            'message': 'AWS credentials not configured'
        }
    except Exception as e:
        return {
            'status': 'error',
            'message': str(e)
        }


def check_s3_connectivity() -> dict:
    """Test basic S3 connectivity"""
    try:
        # Get bucket name from environment
        bucket_name = os.environ.get('PHOTO_BUCKET_NAME')
        if not bucket_name:
            return {
                'status': 'error',
                'message': 'PHOTO_BUCKET_NAME environment variable not set'
            }
        
        # Test S3 connection by checking if bucket exists
        s3_client = boto3.client('s3')
        s3_client.head_bucket(Bucket=bucket_name)
        
        return {
            'status': 'connected',
            'bucket_name': bucket_name
        }
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        return {
            'status': 'error',
            'error_code': error_code,
            'message': str(e)
        }
    except NoCredentialsError:
        return {
            'status': 'error',
            'message': 'AWS credentials not configured'
        }
    except Exception as e:
        return {
            'status': 'error',
            'message': str(e)
        }


def determine_test_mode() -> bool:
    """
    Determine if service is running in test mode based on environment
    """
    # Try environment variable first, then config, then default to dev
    environment = os.environ.get('ENVIRONMENT')
    if not environment:
        environment = config.get_local_parameter('ENVIRONMENT', 'dev')
    
    environment = environment.lower()
    
    # Consider dev and staging as test modes, prod as non-test
    return environment in ['dev', 'staging', 'development', 'test']


def get_service_version() -> str:
    """
    Get service version/build info
    """
    # Check for common build environment variables
    version_indicators = [
        'AWS_SAM_LOCAL',  # SAM local indicator
        'CODEBUILD_BUILD_ID',  # CodeBuild ID
        'CODEBUILD_START_TIME',  # CodeBuild timestamp
        'AWS_LAMBDA_FUNCTION_VERSION'  # Lambda version
    ]
    
    for indicator in version_indicators:
        value = os.environ.get(indicator)
        if value:
            return f"{indicator}={value}"
    
    # Default to runtime environment if no build info
    runtime_version = os.environ.get('AWS_EXECUTION_ENV', 'unknown')
    return f"runtime={runtime_version}"


def lambda_handler(event, context):
    """Lambda handler for health test mode check - handles GET /health/test-mode"""
    try:
        # Get environment information
        environment = config.get_local_parameter('ENVIRONMENT', 'dev')
        test_mode = determine_test_mode()
        service_version = get_service_version()
        
        # Check connectivity to AWS services
        dynamodb_status = check_dynamodb_connectivity()
        s3_status = check_s3_connectivity()
        
        # Determine overall health status
        connectivity_issues = []
        if dynamodb_status['status'] != 'connected':
            connectivity_issues.append('dynamodb')
        if s3_status['status'] != 'connected':
            connectivity_issues.append('s3')
        
        overall_health = 'ok' if not connectivity_issues else 'degraded'
        
        # Build response
        response_data = {
            'service': 'anecdotario-user-service',
            'environment': environment,
            'test_mode': test_mode,
            'health': overall_health,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'version': service_version,
            'connectivity': {
                'dynamodb': dynamodb_status['status'],
                's3': s3_status['status']
            }
        }
        
        # Include detailed connectivity info if there are issues
        if connectivity_issues:
            response_data['connectivity_details'] = {
                'dynamodb': dynamodb_status,
                's3': s3_status
            }
        
        return create_response(
            200,
            json.dumps(response_data, indent=2)
        )
        
    except Exception as e:
        # Return error response for any unexpected failures
        return create_error_response(
            500,
            'Health check failed',
            {'details': str(e)}
        )