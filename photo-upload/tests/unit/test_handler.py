import json
import pytest
import base64
import os
import sys
from unittest.mock import patch, MagicMock, Mock
from PIL import Image
import io

# Add paths for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared'))

# Set environment variables before importing handler
os.environ['PHOTO_BUCKET_NAME'] = 'test-bucket'
os.environ['PARAMETER_STORE_PREFIX'] = '/anecdotario/test/user-service'
os.environ['ENVIRONMENT'] = 'test'


@pytest.fixture
def api_gateway_event():
    """Generate API Gateway Lambda Event"""
    return {
        "resource": "/users/{userId}/photo",
        "path": "/users/test-user-123/photo",
        "httpMethod": "POST",
        "headers": {
            "Authorization": "Bearer test-token",
            "origin": "https://test.com",
            "Content-Type": "application/json"
        },
        "pathParameters": {
            "userId": "test-user-123"
        },
        "body": None,
        "isBase64Encoded": False
    }


@pytest.fixture
def sample_image_base64():
    """Create a sample image and return as base64"""
    img = Image.new('RGB', (100, 100), color='red')
    buffer = io.BytesIO()
    img.save(buffer, format='JPEG')
    img_bytes = buffer.getvalue()
    return base64.b64encode(img_bytes).decode('utf-8')


@pytest.fixture
def decoded_token():
    """Mock decoded JWT token"""
    return {
        'sub': 'test-user-123',
        'email': 'test@example.com',
        'iss': 'https://cognito-idp.us-east-1.amazonaws.com/test-pool-id'
    }


@patch('app.User')
@patch('app.jwks_client')
@patch('app.jwt.decode')
@patch('app.s3_client')
def test_successful_photo_upload_existing_user(mock_s3, mock_jwt_decode, mock_jwks_client, mock_user,
                                             api_gateway_event, sample_image_base64, decoded_token):
    """Test successful photo upload for existing user"""
    from app import lambda_handler
    
    # Configure mocks
    mock_jwks_client.get_signing_key_from_jwt.return_value = Mock(key='test-key')
    mock_jwt_decode.return_value = decoded_token
    
    mock_s3.put_object.return_value = {}
    mock_s3.generate_presigned_url.return_value = 'https://test-bucket.s3.amazonaws.com/test-url'
    
    # Mock existing user
    mock_user_instance = Mock()
    mock_user_instance.to_dict.return_value = {'cognito_id': 'test-user-123', 'nickname': 'testuser'}
    mock_user.get.return_value = mock_user_instance
    
    # Add image to event body
    api_gateway_event['body'] = json.dumps({
        'image': f'data:image/jpeg;base64,{sample_image_base64}'
    })
    
    # Execute
    response = lambda_handler(api_gateway_event, None)
    
    # Verify response
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert 'photo_url' in body
    assert 's3_key' in body
    assert 'message' in body
    assert 'user' in body
    assert body['message'] == 'Photo uploaded successfully'
    
    # Verify S3 upload was called
    mock_s3.put_object.assert_called_once()
    call_args = mock_s3.put_object.call_args[1]
    assert call_args['Bucket'] == 'test-bucket'
    assert 'test-user-123/profile_' in call_args['Key']
    assert call_args['ContentType'] == 'image/jpeg'
    
    # Verify user was updated
    mock_user_instance.save.assert_called_once()


def test_options_request(api_gateway_event):
    """Test CORS preflight OPTIONS request"""
    from app import lambda_handler
    
    api_gateway_event['httpMethod'] = 'OPTIONS'
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 200
    assert 'Access-Control-Allow-Origin' in response['headers']
    assert 'Access-Control-Allow-Methods' in response['headers']
    assert response['body'] == ''


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
    assert body['error'] == 'Invalid token'


@patch('app.jwks_client')
@patch('app.jwt.decode')
def test_unauthorized_user(mock_jwt_decode, mock_jwks_client, api_gateway_event, decoded_token):
    """Test request from user trying to upload to another user's profile"""
    from app import lambda_handler
    
    # Configure mocks
    mock_jwks_client.get_signing_key_from_jwt.return_value = Mock(key='test-key')
    decoded_token['sub'] = 'different-user-456'
    mock_jwt_decode.return_value = decoded_token
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 403
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'Unauthorized' in body['error']


@patch('app.jwks_client')
@patch('app.jwt.decode')
def test_no_image_data(mock_jwt_decode, mock_jwks_client, api_gateway_event, decoded_token):
    """Test request without image data"""
    from app import lambda_handler
    
    # Configure mocks
    mock_jwks_client.get_signing_key_from_jwt.return_value = Mock(key='test-key')
    mock_jwt_decode.return_value = decoded_token
    
    api_gateway_event['body'] = json.dumps({})
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'No image data' in body['error']


@patch('app.jwks_client')
@patch('app.jwt.decode')
def test_image_too_large(mock_jwt_decode, mock_jwks_client, api_gateway_event, decoded_token):
    """Test upload of image that exceeds size limit"""
    from app import lambda_handler
    
    # Configure mocks
    mock_jwks_client.get_signing_key_from_jwt.return_value = Mock(key='test-key')
    mock_jwt_decode.return_value = decoded_token
    
    # Create large image
    large_image = b'x' * (6 * 1024 * 1024)  # 6MB
    large_image_base64 = base64.b64encode(large_image).decode('utf-8')
    
    api_gateway_event['body'] = json.dumps({
        'image': f'data:image/jpeg;base64,{large_image_base64}'
    })
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'too large' in body['error'].lower()


@patch('app.User')
@patch('app.jwks_client')
@patch('app.jwt.decode')
def test_invalid_image_format(mock_jwt_decode, mock_jwks_client, mock_user, api_gateway_event, decoded_token):
    """Test upload of invalid image data"""
    from app import lambda_handler
    
    # Configure mocks
    mock_jwks_client.get_signing_key_from_jwt.return_value = Mock(key='test-key')
    mock_jwt_decode.return_value = decoded_token
    
    # Invalid image data
    invalid_data = base64.b64encode(b'not an image').decode('utf-8')
    
    api_gateway_event['body'] = json.dumps({
        'image': invalid_data
    })
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'Invalid image' in body['error']


@patch('app.User')
@patch('app.jwks_client')
@patch('app.jwt.decode')
@patch('app.s3_client')
def test_s3_upload_failure(mock_s3, mock_jwt_decode, mock_jwks_client, mock_user,
                          api_gateway_event, sample_image_base64, decoded_token):
    """Test handling of S3 upload failure"""
    from app import lambda_handler
    from botocore.exceptions import ClientError
    
    # Configure mocks
    mock_jwks_client.get_signing_key_from_jwt.return_value = Mock(key='test-key')
    mock_jwt_decode.return_value = decoded_token
    
    # Mock S3 failure
    mock_s3.put_object.side_effect = ClientError(
        {'Error': {'Code': 'NoSuchBucket', 'Message': 'Bucket does not exist'}},
        'PutObject'
    )
    
    api_gateway_event['body'] = json.dumps({
        'image': f'data:image/jpeg;base64,{sample_image_base64}'
    })
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 500
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'Failed to upload' in body['error']


@patch('app.User')
@patch('app.jwks_client')
@patch('app.jwt.decode')
@patch('app.s3_client')
def test_successful_photo_upload_new_user(mock_s3, mock_jwt_decode, mock_jwks_client, mock_user,
                                          api_gateway_event, sample_image_base64, decoded_token):
    """Test successful photo upload for new user with nickname"""
    from app import lambda_handler
    
    # Configure mocks
    mock_jwks_client.get_signing_key_from_jwt.return_value = Mock(key='test-key')
    mock_jwt_decode.return_value = decoded_token
    
    mock_s3.put_object.return_value = {}
    mock_s3.generate_presigned_url.return_value = 'https://test-bucket.s3.amazonaws.com/test-url'
    
    # Mock user not found
    mock_user.get.side_effect = mock_user.DoesNotExist
    mock_user.get_by_nickname.return_value = None  # Nickname not taken
    
    # Mock new user instance
    mock_user_instance = Mock()
    mock_user_instance.to_dict.return_value = {
        'cognito_id': 'test-user-123',
        'nickname': 'newuser',
        'image_url': 'https://test-bucket.s3.amazonaws.com/test-url'
    }
    mock_user.return_value = mock_user_instance
    
    # Add image and nickname to event body
    api_gateway_event['body'] = json.dumps({
        'image': f'data:image/jpeg;base64,{sample_image_base64}',
        'nickname': 'newuser'
    })
    
    # Execute
    response = lambda_handler(api_gateway_event, None)
    
    # Verify response
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert 'photo_url' in body
    assert 'user' in body
    assert body['user']['nickname'] == 'newuser'
    
    # Verify new user was created
    mock_user.assert_called_with(
        cognito_id='test-user-123',
        nickname='newuser',
        image_url='https://test-bucket.s3.amazonaws.com/test-url'
    )
    mock_user_instance.save.assert_called_once()


@patch('app.User')
@patch('app.jwks_client')
@patch('app.jwt.decode')
@patch('app.s3_client')
def test_photo_upload_new_user_without_nickname(mock_s3, mock_jwt_decode, mock_jwks_client, mock_user,
                                                api_gateway_event, sample_image_base64, decoded_token):
    """Test photo upload for new user without nickname fails"""
    from app import lambda_handler
    
    # Configure mocks
    mock_jwks_client.get_signing_key_from_jwt.return_value = Mock(key='test-key')
    mock_jwt_decode.return_value = decoded_token
    
    # Mock user not found
    mock_user.get.side_effect = mock_user.DoesNotExist
    
    # Add image without nickname
    api_gateway_event['body'] = json.dumps({
        'image': f'data:image/jpeg;base64,{sample_image_base64}'
    })
    
    # Execute
    response = lambda_handler(api_gateway_event, None)
    
    # Verify response
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'nickname' in body['error'].lower()


def test_get_method_not_allowed(api_gateway_event):
    """Test that GET method is not allowed on photo upload endpoint"""
    from app import lambda_handler
    
    api_gateway_event['httpMethod'] = 'GET'
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 405
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'Method not allowed' in body['error']
    assert 'photo uploads' in body['error']


def test_cors_allowed_origin(api_gateway_event):
    """Test CORS headers with allowed origin"""
    from app import lambda_handler, get_allowed_origin
    
    # Test with allowed origin
    assert get_allowed_origin(api_gateway_event) == 'https://test.com'
    
    # Test with non-allowed origin
    api_gateway_event['headers']['origin'] = 'https://notallowed.com'
    assert get_allowed_origin(api_gateway_event) == 'https://test.com'
    
    # Test with no origin
    del api_gateway_event['headers']['origin']
    assert get_allowed_origin(api_gateway_event) == 'https://test.com'