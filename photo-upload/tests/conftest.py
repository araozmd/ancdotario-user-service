"""
Shared pytest configuration and fixtures for photo upload tests.
"""
import pytest
import os
import sys
import json
from unittest.mock import Mock, patch

# Add paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))

# Set test environment variables
os.environ['PHOTO_BUCKET_NAME'] = 'test-anecdotario-photos'
os.environ['PARAMETER_STORE_PREFIX'] = '/anecdotario/test/user-service'
os.environ['ENVIRONMENT'] = 'test'
os.environ['USER_TABLE_NAME'] = 'Users-test'
os.environ['AWS_REGION'] = 'us-east-1'
os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'


@pytest.fixture(scope='session')
def aws_credentials():
    """Mock AWS Credentials for moto"""
    os.environ['AWS_ACCESS_KEY_ID'] = 'testing'
    os.environ['AWS_SECRET_ACCESS_KEY'] = 'testing'
    os.environ['AWS_SECURITY_TOKEN'] = 'testing'
    os.environ['AWS_SESSION_TOKEN'] = 'testing'


@pytest.fixture
def lambda_context():
    """Mock Lambda context object"""
    context = Mock()
    context.function_name = 'photo-upload-test'
    context.function_version = '$LATEST'
    context.invoked_function_arn = 'arn:aws:lambda:us-east-1:123456789012:function:photo-upload-test'
    context.memory_limit_in_mb = 512
    context.remaining_time_in_millis = lambda: 30000
    context.aws_request_id = 'test-request-id'
    return context


@pytest.fixture
def mock_config():
    """Mock config module to avoid Parameter Store calls"""
    with patch('app.config') as mock_config:
        mock_config.get_int_parameter.return_value = 5242880  # 5MB
        mock_config.get_parameter.return_value = 'test-value'
        yield mock_config


@pytest.fixture
def mock_s3_client():
    """Mock S3 client"""
    with patch('app.s3_client') as mock_s3:
        mock_s3.generate_presigned_url.return_value = 'https://test-bucket.s3.amazonaws.com/presigned-url'
        yield mock_s3


# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers"""
    config.addinivalue_line(
        "markers", "unit: mark test as a unit test"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as an integration test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )


def pytest_collection_modifyitems(config, items):
    """Add markers to test items automatically"""
    for item in items:
        # Add unit marker to unit tests
        if "tests/unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        
        # Add integration marker to integration tests
        if "tests/integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        
        # Add slow marker to performance tests
        if "performance" in item.name.lower() or "concurrent" in item.name.lower():
            item.add_marker(pytest.mark.slow)


# Test utilities
def assert_valid_api_response(response_dict):
    """Assert that response follows API Gateway Lambda proxy format"""
    assert 'statusCode' in response_dict
    assert 'headers' in response_dict
    assert 'body' in response_dict
    assert isinstance(response_dict['statusCode'], int)
    assert isinstance(response_dict['headers'], dict)
    assert isinstance(response_dict['body'], str)


def assert_valid_error_response(response_dict, expected_status_code):
    """Assert that error response follows standard format"""
    assert_valid_api_response(response_dict)
    assert response_dict['statusCode'] == expected_status_code
    
    body = json.loads(response_dict['body'])
    assert 'error' in body
    assert 'statusCode' in body
    assert body['statusCode'] == expected_status_code


def assert_valid_success_response(response_dict):
    """Assert that success response follows standard format"""
    assert_valid_api_response(response_dict)
    assert response_dict['statusCode'] == 200
    
    body = json.loads(response_dict['body'])
    assert 'message' in body