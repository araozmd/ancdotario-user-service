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
os.environ['PHOTO_BUCKET_NAME'] = 'test-bucket'


@pytest.fixture
def api_gateway_event():
    """Generate API Gateway Lambda Event for user deletion"""
    return {
        "resource": "/users/{userId}",
        "path": "/users/test-user-123",
        "httpMethod": "DELETE",
        "headers": {
            "Authorization": "Bearer test-token",
            "origin": "https://test.com",
            "Content-Type": "application/json"
        },
        "pathParameters": {
            "userId": "test-user-123"
        },
        "queryStringParameters": {
            "confirm": "true"
        },
        "body": json.dumps({"reason": "User requested account deletion"}),
        "isBase64Encoded": False,
        "requestContext": {
            "requestTime": "2023-01-01T12:00:00Z"
        }
    }


@pytest.fixture
def self_delete_event():
    """Generate API Gateway Lambda Event for self-deletion (no userId in path)"""
    return {
        "resource": "/users",
        "path": "/users",
        "httpMethod": "DELETE",
        "headers": {
            "Authorization": "Bearer test-token",
            "origin": "https://test.com",
            "Content-Type": "application/json"
        },
        "pathParameters": None,
        "queryStringParameters": {
            "confirm": "true"
        },
        "body": json.dumps({"reason": "Self-requested deletion"}),
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


@patch('app.s3_client')
@patch('app.User')
@patch('app.validate_request_auth')
def test_successful_user_deletion(mock_validate_auth, mock_user, mock_s3, api_gateway_event, decoded_token):
    """Test successful user deletion with photo cleanup"""
    from app import lambda_handler
    
    # Configure mocks
    mock_validate_auth.return_value = (decoded_token, None)
    
    # Mock existing user
    mock_user_instance = Mock()
    mock_user_instance.to_dict.return_value = {
        'cognito_id': 'test-user-123',
        'nickname': 'testuser',
        'image_url': 'https://test-bucket.s3.amazonaws.com/test-user-123/profile.jpg',
        'created_at': '2023-01-01T10:00:00',
        'updated_at': '2023-01-01T12:00:00'
    }
    mock_user.get.return_value = mock_user_instance
    
    # Mock S3 operations
    mock_s3.list_objects_v2.return_value = {
        'Contents': [
            {'Key': 'test-user-123/profile_20230101_12345.jpg'},
            {'Key': 'test-user-123/profile_20230102_67890.jpg'}
        ]
    }
    mock_s3.delete_object.return_value = {}
    
    # Execute
    response = lambda_handler(api_gateway_event, None)
    
    # Verify response
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert 'message' in body
    assert 'deleted_user' in body
    assert 'photos_deleted' in body
    assert body['message'] == 'User account deleted successfully'
    assert body['deleted_user']['cognito_id'] == 'test-user-123'
    assert len(body['photos_deleted']) == 2
    assert body['deletion_reason'] == 'User requested account deletion'
    
    # Verify user was deleted
    mock_user_instance.delete.assert_called_once()
    
    # Verify S3 cleanup
    mock_s3.list_objects_v2.assert_called_with(
        Bucket='test-bucket',
        Prefix='test-user-123/'
    )
    assert mock_s3.delete_object.call_count == 2


@patch('app.User')
@patch('app.validate_request_auth')
def test_successful_self_deletion(mock_validate_auth, mock_user, self_delete_event, decoded_token):
    """Test successful self-deletion without path parameter"""
    from app import lambda_handler
    
    # Configure mocks
    mock_validate_auth.return_value = (decoded_token, None)
    
    # Mock existing user
    mock_user_instance = Mock()
    mock_user_instance.to_dict.return_value = {
        'cognito_id': 'test-user-123',
        'nickname': 'testuser',
        'image_url': None
    }
    mock_user.get.return_value = mock_user_instance
    
    # Execute
    response = lambda_handler(self_delete_event, None)
    
    # Verify response
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['deleted_user']['cognito_id'] == 'test-user-123'
    assert body['deletion_reason'] == 'Self-requested deletion'
    
    # Verify user was deleted
    mock_user_instance.delete.assert_called_once()


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
def test_unauthorized_deletion_attempt(mock_validate_auth, mock_user, api_gateway_event, decoded_token):
    """Test attempt to delete another user's account"""
    from app import lambda_handler
    
    # Configure mocks - token belongs to different user
    different_token = decoded_token.copy()
    different_token['sub'] = 'different-user-456'
    mock_validate_auth.return_value = (different_token, None)
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 403
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'Unauthorized' in body['error']
    assert 'token_user_id' in body
    assert 'target_user_id' in body


@patch('app.User')
@patch('app.validate_request_auth')
def test_user_not_found(mock_validate_auth, mock_user, api_gateway_event, decoded_token):
    """Test deletion of non-existent user"""
    from app import lambda_handler
    
    # Configure mocks
    mock_validate_auth.return_value = (decoded_token, None)
    mock_user.get.side_effect = mock_user.DoesNotExist
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 404
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'User not found' in body['error']
    assert 'user_id' in body


@patch('app.User')
@patch('app.validate_request_auth')
def test_missing_confirmation_parameter(mock_validate_auth, mock_user, api_gateway_event, decoded_token):
    """Test deletion without confirmation parameter"""
    from app import lambda_handler
    
    # Configure mocks
    mock_validate_auth.return_value = (decoded_token, None)
    
    # Mock existing user
    mock_user_instance = Mock()
    mock_user_instance.to_dict.return_value = {
        'cognito_id': 'test-user-123',
        'nickname': 'testuser',
        'image_url': None
    }
    mock_user.get.return_value = mock_user_instance
    
    # Remove confirmation parameter
    api_gateway_event['queryStringParameters'] = {}
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'confirmation' in body['error']
    assert 'usage' in body
    assert 'warning' in body
    assert 'user' in body


@patch('app.User')
@patch('app.validate_request_auth')
def test_invalid_confirmation_value(mock_validate_auth, mock_user, api_gateway_event, decoded_token):
    """Test deletion with invalid confirmation value"""
    from app import lambda_handler
    
    # Configure mocks
    mock_validate_auth.return_value = (decoded_token, None)
    
    # Mock existing user
    mock_user_instance = Mock()
    mock_user_instance.to_dict.return_value = {
        'cognito_id': 'test-user-123',
        'nickname': 'testuser'
    }
    mock_user.get.return_value = mock_user_instance
    
    # Set invalid confirmation
    api_gateway_event['queryStringParameters']['confirm'] = 'false'
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'confirmation' in body['error']


def test_options_request(api_gateway_event):
    """Test CORS preflight OPTIONS request"""
    from app import lambda_handler
    
    api_gateway_event['httpMethod'] = 'OPTIONS'
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 200
    assert 'Access-Control-Allow-Origin' in response['headers']
    assert 'Access-Control-Allow-Methods' in response['headers']
    assert response['body'] == ''


def test_get_method_not_allowed(api_gateway_event):
    """Test that GET method is not allowed"""
    from app import lambda_handler
    
    api_gateway_event['httpMethod'] = 'GET'
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 405
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'Method not allowed' in body['error']


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


@patch('app.s3_client')
@patch('app.User')
@patch('app.validate_request_auth')
def test_deletion_with_s3_error(mock_validate_auth, mock_user, mock_s3, api_gateway_event, decoded_token):
    """Test user deletion when S3 photo cleanup fails"""
    from app import lambda_handler
    from botocore.exceptions import ClientError
    
    # Configure mocks
    mock_validate_auth.return_value = (decoded_token, None)
    
    # Mock existing user with photos
    mock_user_instance = Mock()
    mock_user_instance.to_dict.return_value = {
        'cognito_id': 'test-user-123',
        'nickname': 'testuser',
        'image_url': 'https://test-bucket.s3.amazonaws.com/test-user-123/profile.jpg'
    }
    mock_user.get.return_value = mock_user_instance
    
    # Mock S3 error
    mock_s3.list_objects_v2.side_effect = ClientError(
        {'Error': {'Code': 'NoSuchBucket', 'Message': 'Bucket does not exist'}},
        'ListObjectsV2'
    )
    
    # Execute - should succeed despite S3 error
    response = lambda_handler(api_gateway_event, None)
    
    # Verify response - user deletion should still succeed
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['message'] == 'User account deleted successfully'
    assert body['photos_deleted'] == []  # Empty due to S3 error
    
    # Verify user was still deleted
    mock_user_instance.delete.assert_called_once()


@patch('app.User')
@patch('app.validate_request_auth')
def test_deletion_without_body(mock_validate_auth, mock_user, api_gateway_event, decoded_token):
    """Test deletion without request body (reason is optional)"""
    from app import lambda_handler
    
    # Configure mocks
    mock_validate_auth.return_value = (decoded_token, None)
    
    # Mock existing user
    mock_user_instance = Mock()
    mock_user_instance.to_dict.return_value = {
        'cognito_id': 'test-user-123',
        'nickname': 'testuser',
        'image_url': None
    }
    mock_user.get.return_value = mock_user_instance
    
    # Remove body
    api_gateway_event['body'] = None
    
    # Execute
    response = lambda_handler(api_gateway_event, None)
    
    # Verify response
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['deletion_reason'] == 'User requested deletion'  # Default reason


@patch('app.User')
@patch('app.validate_request_auth')
def test_database_error_during_deletion(mock_validate_auth, mock_user, api_gateway_event, decoded_token):
    """Test handling of database errors during deletion"""
    from app import lambda_handler
    
    # Configure mocks
    mock_validate_auth.return_value = (decoded_token, None)
    
    # Mock existing user
    mock_user_instance = Mock()
    mock_user_instance.to_dict.return_value = {
        'cognito_id': 'test-user-123',
        'nickname': 'testuser'
    }
    mock_user_instance.delete.side_effect = Exception('Database connection failed')
    mock_user.get.return_value = mock_user_instance
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 500
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'Internal server error' in body['error']
    assert 'details' in body


@patch('app.s3_client')
def test_delete_user_photos_function(mock_s3):
    """Test the delete_user_photos function directly"""
    from app import delete_user_photos
    
    # Mock S3 responses
    mock_s3.list_objects_v2.return_value = {
        'Contents': [
            {'Key': 'test-user/profile1.jpg'},
            {'Key': 'test-user/profile2.jpg'}
        ]
    }
    mock_s3.delete_object.return_value = {}
    
    # Execute
    deleted_photos = delete_user_photos('test-user')
    
    # Verify
    assert len(deleted_photos) == 2
    assert 'test-user/profile1.jpg' in deleted_photos
    assert 'test-user/profile2.jpg' in deleted_photos
    
    # Verify S3 calls
    mock_s3.list_objects_v2.assert_called_with(
        Bucket='test-bucket',
        Prefix='test-user/'
    )
    assert mock_s3.delete_object.call_count == 2


@patch('app.s3_client')
def test_delete_user_photos_no_photos(mock_s3):
    """Test delete_user_photos when user has no photos"""
    from app import delete_user_photos
    
    # Mock S3 response with no contents
    mock_s3.list_objects_v2.return_value = {}
    
    # Execute
    deleted_photos = delete_user_photos('test-user')
    
    # Verify
    assert deleted_photos == []
    
    # Verify S3 was queried but no deletes occurred
    mock_s3.list_objects_v2.assert_called_once()
    mock_s3.delete_object.assert_not_called()