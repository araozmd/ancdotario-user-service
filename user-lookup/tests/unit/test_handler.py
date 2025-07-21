import json
import pytest
import os
from unittest.mock import patch, MagicMock, Mock
import sys

# Add paths for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared'))

# Set environment variables before importing handler
os.environ['PARAMETER_STORE_PREFIX'] = '/anecdotario/test/user-service'
os.environ['ENVIRONMENT'] = 'test'


@pytest.fixture
def api_gateway_event():
    """Generate API Gateway Lambda Event for user lookup"""
    return {
        "resource": "/users/{nickname}",
        "path": "/users/testuser",
        "httpMethod": "GET",
        "headers": {
            "Authorization": "Bearer test-token",
            "origin": "https://test.com",
            "Content-Type": "application/json"
        },
        "pathParameters": {
            "nickname": "testuser"
        },
        "requestContext": {
            "requestTime": "2023-01-01T12:00:00Z"
        }
    }


@pytest.fixture
def decoded_token():
    """Mock decoded JWT token"""
    return {
        'sub': 'test-user-123',
        'email': 'test@example.com',
        'iss': 'https://cognito-idp.us-east-1.amazonaws.com/test-pool-id'
    }


@patch('app.jwks_client')
@patch('app.jwt.decode')
@patch('app.User')
def test_successful_user_lookup(mock_user, mock_jwt_decode, mock_jwks_client, api_gateway_event, decoded_token):
    """Test successful user lookup by nickname"""
    from app import lambda_handler
    
    # Configure mocks for JWT validation
    mock_jwks_client.get_signing_key_from_jwt.return_value = Mock(key='test-key')
    mock_jwt_decode.return_value = decoded_token
    
    # Mock user lookup
    mock_user_instance = Mock()
    mock_user_instance.to_dict.return_value = {
        'cognito_id': 'test-user-123',
        'nickname': 'testuser',
        'image_url': 'https://test-bucket.s3.amazonaws.com/test-url',
        'created_at': '2023-01-01T10:00:00',
        'updated_at': '2023-01-01T12:00:00'
    }
    mock_user.get_by_nickname.return_value = mock_user_instance
    
    # Execute
    response = lambda_handler(api_gateway_event, None)
    
    # Verify response
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert 'user' in body
    assert body['user']['nickname'] == 'testuser'
    assert body['user']['cognito_id'] == 'test-user-123'
    assert 'retrieved_at' in body
    
    # Verify user lookup was called
    mock_user.get_by_nickname.assert_called_once_with('testuser')


def test_missing_authorization_header(api_gateway_event):
    """Test request without authorization header"""
    from app import lambda_handler
    
    del api_gateway_event['headers']['Authorization']
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 401
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'authorization' in body['error'].lower()


@patch('app.jwks_client')
@patch('app.jwt.decode')
def test_invalid_token(mock_jwt_decode, mock_jwks_client, api_gateway_event):
    """Test request with invalid JWT token"""
    from app import lambda_handler
    
    mock_jwks_client.get_signing_key_from_jwt.side_effect = Exception('Invalid token')
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 401
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'Invalid token' in body['error']


def test_options_request(api_gateway_event):
    """Test CORS preflight OPTIONS request"""
    from app import lambda_handler
    
    api_gateway_event['httpMethod'] = 'OPTIONS'
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 200
    assert 'Access-Control-Allow-Origin' in response['headers']
    assert 'Access-Control-Allow-Methods' in response['headers']
    assert response['body'] == ''


def test_missing_nickname_parameter(api_gateway_event):
    """Test request without nickname parameter"""
    from app import lambda_handler
    
    # Remove nickname parameter
    api_gateway_event['pathParameters'] = {}
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'Nickname path parameter is required' in body['error']
    assert 'usage' in body


def test_empty_path_parameters(api_gateway_event):
    """Test request with null path parameters"""
    from app import lambda_handler
    
    # Set path parameters to None
    api_gateway_event['pathParameters'] = None
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'Nickname path parameter is required' in body['error']


def test_invalid_nickname_too_short(api_gateway_event):
    """Test request with nickname that's too short"""
    from app import lambda_handler
    
    api_gateway_event['pathParameters']['nickname'] = 'ab'
    api_gateway_event['path'] = '/users/ab'
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'between 3 and 20 characters' in body['error']


def test_invalid_nickname_too_long(api_gateway_event):
    """Test request with nickname that's too long"""
    from app import lambda_handler
    
    long_nickname = 'a' * 21
    api_gateway_event['pathParameters']['nickname'] = long_nickname
    api_gateway_event['path'] = f'/users/{long_nickname}'
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'between 3 and 20 characters' in body['error']


@patch('app.jwks_client')
@patch('app.jwt.decode')
@patch('app.User')
def test_user_not_found(mock_user, mock_jwt_decode, mock_jwks_client, api_gateway_event, decoded_token):
    """Test lookup for non-existent user"""
    from app import lambda_handler
    
    # Configure mocks for JWT validation
    mock_jwks_client.get_signing_key_from_jwt.return_value = Mock(key='test-key')
    mock_jwt_decode.return_value = decoded_token
    
    # Mock user not found
    mock_user.get_by_nickname.return_value = None
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 404
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'User not found' in body['error']
    assert 'nickname' in body
    assert body['nickname'] == 'testuser'


@patch('app.User')
def test_database_error(mock_user, api_gateway_event):
    """Test handling of database errors"""
    from app import lambda_handler
    
    # Mock database error
    mock_user.get_by_nickname.side_effect = Exception('Database connection failed')
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 500
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'Internal server error' in body['error']
    assert 'details' in body


def test_post_method_not_allowed(api_gateway_event):
    """Test that POST method is not allowed"""
    from app import lambda_handler
    
    api_gateway_event['httpMethod'] = 'POST'
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 405
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'Method not allowed' in body['error']
    assert 'user lookup' in body['error']


def test_cors_allowed_origin(api_gateway_event):
    """Test CORS headers with allowed origin"""
    from app import lambda_handler, get_allowed_origin
    
    # Test with allowed origin
    api_gateway_event['headers']['origin'] = 'https://test.com'
    assert get_allowed_origin(api_gateway_event) == 'https://test.com'
    
    # Test with non-allowed origin
    api_gateway_event['headers']['origin'] = 'https://notallowed.com'
    # Should return first allowed origin as default
    result = get_allowed_origin(api_gateway_event)
    assert result in ['https://localhost:3000', 'https://test.com']
    
    # Test with no origin
    del api_gateway_event['headers']['origin']
    result = get_allowed_origin(api_gateway_event)
    assert result in ['https://localhost:3000', 'https://test.com']


def test_successful_lookup_with_minimal_user_data():
    """Test successful lookup with minimal user data"""
    from app import lambda_handler
    
    # Create minimal event
    event = {
        "httpMethod": "GET",
        "headers": {"origin": "https://test.com"},
        "pathParameters": {"nickname": "minimal"},
        "path": "/users/minimal",
        "requestContext": {"requestTime": "2023-01-01T12:00:00Z"}
    }
    
    with patch('app.User') as mock_user:
        # Mock minimal user data
        mock_user_instance = Mock()
        mock_user_instance.to_dict.return_value = {
            'cognito_id': 'minimal-user',
            'nickname': 'minimal',
            'image_url': None
        }
        mock_user.get_by_nickname.return_value = mock_user_instance
        
        response = lambda_handler(event, None)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['user']['nickname'] == 'minimal'
        assert body['user']['image_url'] is None