import json
import pytest
import os
import sys
from unittest.mock import patch, MagicMock, Mock

# Add paths for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared'))

# Set environment variables before importing handler
os.environ['PARAMETER_STORE_PREFIX'] = '/anecdotario/test/user-service'
os.environ['ENVIRONMENT'] = 'test'


@pytest.fixture
def api_gateway_event():
    """Generate API Gateway Lambda Event for user creation"""
    return {
        "resource": "/users",
        "path": "/users",
        "httpMethod": "POST",
        "headers": {
            "Authorization": "Bearer test-token",
            "origin": "https://test.com",
            "Content-Type": "application/json"
        },
        "body": json.dumps({"nickname": "testuser"}),
        "isBase64Encoded": False,
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


@patch('app.User')
@patch('app.validate_request_auth')
def test_successful_user_creation(mock_validate_auth, mock_user, api_gateway_event, decoded_token):
    """Test successful user creation"""
    from app import lambda_handler
    
    # Configure mocks
    mock_validate_auth.return_value = (decoded_token, None)
    
    # Mock user doesn't exist
    mock_user.get.side_effect = mock_user.DoesNotExist
    mock_user.get_by_nickname.return_value = None  # Nickname not taken
    
    # Mock new user instance
    mock_user_instance = Mock()
    mock_user_instance.to_dict.return_value = {
        'cognito_id': 'test-user-123',
        'nickname': 'testuser',
        'image_url': None,
        'created_at': '2023-01-01T12:00:00',
        'updated_at': '2023-01-01T12:00:00'
    }
    mock_user.return_value = mock_user_instance
    
    # Execute
    response = lambda_handler(api_gateway_event, None)
    
    # Verify response
    assert response['statusCode'] == 201
    body = json.loads(response['body'])
    assert 'message' in body
    assert 'user' in body
    assert body['message'] == 'User created successfully'
    assert body['user']['nickname'] == 'testuser'
    assert body['user']['cognito_id'] == 'test-user-123'
    
    # Verify user was created
    mock_user.assert_called_with(
        cognito_id='test-user-123',
        nickname='testuser',
        image_url=None
    )
    mock_user_instance.save.assert_called_once()


@patch('app.validate_request_auth')
def test_missing_authorization_header(mock_validate_auth, api_gateway_event):
    """Test request without authorization header"""
    from app import lambda_handler
    
    # Mock auth failure
    error_response = {
        'statusCode': 401,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps({'error': 'Missing authorization header'})
    }
    mock_validate_auth.return_value = (None, error_response)
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 401
    body = json.loads(response['body'])
    assert 'error' in body


@patch('app.User')
@patch('app.validate_request_auth')
def test_user_already_exists(mock_validate_auth, mock_user, api_gateway_event, decoded_token):
    """Test creation when user already exists"""
    from app import lambda_handler
    
    # Configure mocks
    mock_validate_auth.return_value = (decoded_token, None)
    
    # Mock existing user
    mock_user_instance = Mock()
    mock_user_instance.to_dict.return_value = {
        'cognito_id': 'test-user-123',
        'nickname': 'existinguser',
        'image_url': None
    }
    mock_user.get.return_value = mock_user_instance
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 409
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'already exists' in body['error']
    assert 'user' in body


def test_options_request(api_gateway_event):
    """Test CORS preflight OPTIONS request"""
    from app import lambda_handler
    
    api_gateway_event['httpMethod'] = 'OPTIONS'
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 200
    assert 'Access-Control-Allow-Origin' in response['headers']
    assert 'Access-Control-Allow-Methods' in response['headers']
    assert response['body'] == ''


@patch('app.validate_request_auth')
def test_missing_request_body(mock_validate_auth, api_gateway_event, decoded_token):
    """Test request without body"""
    from app import lambda_handler
    
    mock_validate_auth.return_value = (decoded_token, None)
    api_gateway_event['body'] = None
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'Request body is required' in body['error']
    assert 'usage' in body


@patch('app.validate_request_auth')
def test_invalid_json_body(mock_validate_auth, api_gateway_event, decoded_token):
    """Test request with invalid JSON body"""
    from app import lambda_handler
    
    mock_validate_auth.return_value = (decoded_token, None)
    api_gateway_event['body'] = 'invalid json'
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'Invalid JSON' in body['error']


@patch('app.validate_request_auth')
def test_missing_nickname(mock_validate_auth, api_gateway_event, decoded_token):
    """Test request without nickname"""
    from app import lambda_handler
    
    mock_validate_auth.return_value = (decoded_token, None)
    api_gateway_event['body'] = json.dumps({})
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'Nickname is required' in body['error']


@patch('app.User')
@patch('app.validate_request_auth')
def test_nickname_already_taken(mock_validate_auth, mock_user, api_gateway_event, decoded_token):
    """Test creation when nickname is already taken"""
    from app import lambda_handler
    
    # Configure mocks
    mock_validate_auth.return_value = (decoded_token, None)
    
    # Mock user doesn't exist but nickname is taken
    mock_user.get.side_effect = mock_user.DoesNotExist
    
    # Mock existing user with same nickname
    mock_existing_user = Mock()
    mock_user.get_by_nickname.return_value = mock_existing_user
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 409
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'already taken' in body['error']
    assert 'nickname' in body


@pytest.mark.parametrize("invalid_nickname,expected_error", [
    ("ab", "at least 3 characters"),
    ("a" * 21, "no more than 20 characters"),
    ("test@user", "can only contain letters"),
    ("_testuser", "must start with a letter"),
    ("testuser_", "must end with a letter"),
    ("test__user", "consecutive underscores"),
    ("admin", "reserved and cannot be used"),
    ("root", "reserved and cannot be used"),
])
@patch('app.User')
@patch('app.validate_request_auth')
def test_invalid_nickname_formats(mock_validate_auth, mock_user, api_gateway_event, decoded_token,
                                 invalid_nickname, expected_error):
    """Test various invalid nickname formats"""
    from app import lambda_handler
    
    # Configure mocks
    mock_validate_auth.return_value = (decoded_token, None)
    mock_user.get.side_effect = mock_user.DoesNotExist
    
    # Set invalid nickname
    api_gateway_event['body'] = json.dumps({"nickname": invalid_nickname})
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'error' in body
    assert expected_error in body['error']


@patch('app.validate_request_auth')
def test_missing_user_id_in_token(mock_validate_auth, api_gateway_event):
    """Test token without user ID (sub)"""
    from app import lambda_handler
    
    # Token without 'sub' field
    invalid_token = {'email': 'test@example.com'}
    mock_validate_auth.return_value = (invalid_token, None)
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'missing user ID' in body['error']


def test_get_method_not_allowed(api_gateway_event):
    """Test that GET method is not allowed"""
    from app import lambda_handler
    
    api_gateway_event['httpMethod'] = 'GET'
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 405
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'Method not allowed' in body['error']


@patch('app.User')
@patch('app.validate_request_auth')
def test_database_error(mock_validate_auth, mock_user, api_gateway_event, decoded_token):
    """Test handling of database errors"""
    from app import lambda_handler
    
    # Configure mocks
    mock_validate_auth.return_value = (decoded_token, None)
    mock_user.get.side_effect = mock_user.DoesNotExist
    mock_user.get_by_nickname.return_value = None
    
    # Mock database error during save
    mock_user_instance = Mock()
    mock_user_instance.save.side_effect = Exception('Database connection failed')
    mock_user.return_value = mock_user_instance
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 500
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'Internal server error' in body['error']
    assert 'details' in body


def test_validate_nickname_function():
    """Test the validate_nickname function directly"""
    from app import validate_nickname
    
    # Valid nicknames
    assert validate_nickname("testuser") is None
    assert validate_nickname("user123") is None
    assert validate_nickname("test_user") is None
    assert validate_nickname("test-user") is None
    
    # Invalid nicknames
    assert "at least 3 characters" in validate_nickname("ab")
    assert "no more than 20 characters" in validate_nickname("a" * 21)
    assert "can only contain" in validate_nickname("test@user")
    assert "must start with" in validate_nickname("_test")
    assert "must end with" in validate_nickname("test_")
    assert "consecutive" in validate_nickname("test__user")
    assert "reserved" in validate_nickname("admin")