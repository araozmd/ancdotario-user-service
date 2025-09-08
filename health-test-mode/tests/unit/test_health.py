import json
import os
import pytest
from unittest.mock import patch, Mock, MagicMock
from datetime import datetime, timezone
from botocore.exceptions import ClientError, NoCredentialsError

# Import the handler
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import app


@pytest.fixture
def api_gateway_event():
    """Simple API Gateway event for health check"""
    return {
        "httpMethod": "GET",
        "path": "/health/test-mode",
        "headers": {
            "Content-Type": "application/json"
        }
    }


@pytest.fixture
def lambda_context():
    """Mock Lambda context"""
    context = Mock()
    context.function_name = "health-test-mode"
    context.function_version = "1"
    context.invoked_function_arn = "arn:aws:lambda:us-east-1:123456789:function:health-test-mode"
    return context


@pytest.fixture
def mock_environment():
    """Mock environment variables"""
    return {
        'ENVIRONMENT': 'dev',
        'USER_TABLE_NAME': 'Users-dev',
        'PHOTO_BUCKET_NAME': 'test-bucket-photos-dev',
        'AWS_EXECUTION_ENV': 'AWS_Lambda_python3.12'
    }


class TestHealthEndpoint:
    """Test cases for health test mode endpoint"""

    def test_successful_health_check(self, api_gateway_event, lambda_context, mock_environment):
        """Test successful health check with all services connected"""
        with patch.dict(os.environ, mock_environment):
            with patch('boto3.client') as mock_boto3:
                # Mock successful DynamoDB response
                mock_dynamodb = Mock()
                mock_dynamodb.describe_table.return_value = {
                    'Table': {'TableStatus': 'ACTIVE'}
                }
                
                # Mock successful S3 response
                mock_s3 = Mock()
                mock_s3.head_bucket.return_value = {}
                
                # Configure boto3 client to return appropriate mocks
                def client_side_effect(service):
                    if service == 'dynamodb':
                        return mock_dynamodb
                    elif service == 's3':
                        return mock_s3
                    return Mock()
                
                mock_boto3.side_effect = client_side_effect
                
                # Call the handler
                response = app.lambda_handler(api_gateway_event, lambda_context)
                
                # Verify response
                assert response['statusCode'] == 200
                
                body = json.loads(response['body'])
                assert body['service'] == 'anecdotario-user-service'
                assert body['environment'] == 'dev'
                assert body['test_mode'] is True
                assert body['health'] == 'ok'
                assert body['connectivity']['dynamodb'] == 'connected'
                assert body['connectivity']['s3'] == 'connected'
                assert 'timestamp' in body
                assert 'version' in body

    def test_health_check_with_production_environment(self, api_gateway_event, lambda_context):
        """Test health check identifies production as non-test mode"""
        prod_env = {
            'ENVIRONMENT': 'prod',
            'USER_TABLE_NAME': 'Users-prod',
            'PHOTO_BUCKET_NAME': 'test-bucket-photos-prod'
        }
        
        with patch.dict(os.environ, prod_env):
            with patch('boto3.client') as mock_boto3:
                # Mock successful responses
                mock_dynamodb = Mock()
                mock_dynamodb.describe_table.return_value = {
                    'Table': {'TableStatus': 'ACTIVE'}
                }
                mock_s3 = Mock()
                mock_s3.head_bucket.return_value = {}
                
                def client_side_effect(service):
                    if service == 'dynamodb':
                        return mock_dynamodb
                    elif service == 's3':
                        return mock_s3
                    return Mock()
                
                mock_boto3.side_effect = client_side_effect
                
                response = app.lambda_handler(api_gateway_event, lambda_context)
                
                assert response['statusCode'] == 200
                body = json.loads(response['body'])
                assert body['environment'] == 'prod'
                assert body['test_mode'] is False

    def test_health_check_with_dynamodb_failure(self, api_gateway_event, lambda_context, mock_environment):
        """Test health check when DynamoDB is not accessible"""
        with patch.dict(os.environ, mock_environment):
            with patch('boto3.client') as mock_boto3:
                # Mock DynamoDB error
                mock_dynamodb = Mock()
                mock_dynamodb.describe_table.side_effect = ClientError(
                    {'Error': {'Code': 'ResourceNotFoundException', 'Message': 'Table not found'}},
                    'DescribeTable'
                )
                
                # Mock successful S3 response
                mock_s3 = Mock()
                mock_s3.head_bucket.return_value = {}
                
                def client_side_effect(service):
                    if service == 'dynamodb':
                        return mock_dynamodb
                    elif service == 's3':
                        return mock_s3
                    return Mock()
                
                mock_boto3.side_effect = client_side_effect
                
                response = app.lambda_handler(api_gateway_event, lambda_context)
                
                assert response['statusCode'] == 200
                body = json.loads(response['body'])
                assert body['health'] == 'degraded'
                assert body['connectivity']['dynamodb'] == 'error'
                assert body['connectivity']['s3'] == 'connected'
                assert 'connectivity_details' in body

    def test_health_check_with_s3_failure(self, api_gateway_event, lambda_context, mock_environment):
        """Test health check when S3 is not accessible"""
        with patch.dict(os.environ, mock_environment):
            with patch('boto3.client') as mock_boto3:
                # Mock successful DynamoDB response
                mock_dynamodb = Mock()
                mock_dynamodb.describe_table.return_value = {
                    'Table': {'TableStatus': 'ACTIVE'}
                }
                
                # Mock S3 error
                mock_s3 = Mock()
                mock_s3.head_bucket.side_effect = ClientError(
                    {'Error': {'Code': 'NoSuchBucket', 'Message': 'Bucket does not exist'}},
                    'HeadBucket'
                )
                
                def client_side_effect(service):
                    if service == 'dynamodb':
                        return mock_dynamodb
                    elif service == 's3':
                        return mock_s3
                    return Mock()
                
                mock_boto3.side_effect = client_side_effect
                
                response = app.lambda_handler(api_gateway_event, lambda_context)
                
                assert response['statusCode'] == 200
                body = json.loads(response['body'])
                assert body['health'] == 'degraded'
                assert body['connectivity']['dynamodb'] == 'connected'
                assert body['connectivity']['s3'] == 'error'

    def test_health_check_missing_environment_variables(self, api_gateway_event, lambda_context):
        """Test health check when environment variables are missing"""
        # Use minimal environment
        minimal_env = {'ENVIRONMENT': 'dev'}
        
        with patch.dict(os.environ, minimal_env, clear=True):
            response = app.lambda_handler(api_gateway_event, lambda_context)
            
            assert response['statusCode'] == 200
            body = json.loads(response['body'])
            assert body['health'] == 'degraded'
            assert body['connectivity']['dynamodb'] == 'error'
            assert body['connectivity']['s3'] == 'error'

    def test_health_check_unexpected_error(self, api_gateway_event, lambda_context, mock_environment):
        """Test health check handles unexpected errors gracefully"""
        with patch.dict(os.environ, mock_environment):
            with patch('app.determine_test_mode', side_effect=Exception("Unexpected error")):
                response = app.lambda_handler(api_gateway_event, lambda_context)
                
                assert response['statusCode'] == 500
                body = json.loads(response['body'])
                assert body['error'] == 'Health check failed'
                assert 'details' in body

    def test_determine_test_mode_function(self):
        """Test the determine_test_mode helper function"""
        test_cases = [
            ('dev', True),
            ('staging', True),
            ('development', True),
            ('test', True),
            ('prod', False),
            ('production', False),
            ('unknown', False)
        ]
        
        for env, expected in test_cases:
            with patch('app.config.get_local_parameter', return_value=env):
                assert app.determine_test_mode() == expected

    def test_get_service_version_function(self):
        """Test the get_service_version helper function"""
        # Test with CodeBuild ID
        with patch.dict(os.environ, {'CODEBUILD_BUILD_ID': 'test-build-123'}):
            version = app.get_service_version()
            assert version == 'CODEBUILD_BUILD_ID=test-build-123'
        
        # Test with SAM local
        with patch.dict(os.environ, {'AWS_SAM_LOCAL': 'true'}):
            version = app.get_service_version()
            assert version == 'AWS_SAM_LOCAL=true'
        
        # Test fallback to runtime
        with patch.dict(os.environ, {}, clear=True):
            version = app.get_service_version()
            assert 'runtime=' in version


class TestHelperFunctions:
    """Test helper functions"""

    def test_create_response(self):
        """Test create_response function"""
        response = app.create_response(200, '{"test": "data"}')
        
        assert response['statusCode'] == 200
        assert response['headers']['Content-Type'] == 'application/json'
        assert response['body'] == '{"test": "data"}'

    def test_create_error_response(self):
        """Test create_error_response function"""
        response = app.create_error_response(400, 'Test error', {'key': 'value'})
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error'] == 'Test error'
        assert body['statusCode'] == 400
        assert body['details'] == {'key': 'value'}

    def test_check_dynamodb_connectivity_success(self):
        """Test DynamoDB connectivity check success"""
        with patch.dict(os.environ, {'USER_TABLE_NAME': 'test-table'}):
            with patch('boto3.client') as mock_boto3:
                mock_client = Mock()
                mock_client.describe_table.return_value = {
                    'Table': {'TableStatus': 'ACTIVE'}
                }
                mock_boto3.return_value = mock_client
                
                result = app.check_dynamodb_connectivity()
                
                assert result['status'] == 'connected'
                assert result['table_name'] == 'test-table'
                assert result['table_status'] == 'ACTIVE'

    def test_check_dynamodb_connectivity_missing_env(self):
        """Test DynamoDB connectivity check with missing environment variable"""
        with patch.dict(os.environ, {}, clear=True):
            result = app.check_dynamodb_connectivity()
            
            assert result['status'] == 'error'
            assert 'USER_TABLE_NAME' in result['message']

    def test_check_s3_connectivity_success(self):
        """Test S3 connectivity check success"""
        with patch.dict(os.environ, {'PHOTO_BUCKET_NAME': 'test-bucket'}):
            with patch('boto3.client') as mock_boto3:
                mock_client = Mock()
                mock_client.head_bucket.return_value = {}
                mock_boto3.return_value = mock_client
                
                result = app.check_s3_connectivity()
                
                assert result['status'] == 'connected'
                assert result['bucket_name'] == 'test-bucket'

    def test_check_s3_connectivity_missing_env(self):
        """Test S3 connectivity check with missing environment variable"""
        with patch.dict(os.environ, {}, clear=True):
            result = app.check_s3_connectivity()
            
            assert result['status'] == 'error'
            assert 'PHOTO_BUCKET_NAME' in result['message']