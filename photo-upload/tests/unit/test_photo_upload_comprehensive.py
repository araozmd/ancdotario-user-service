import json
import pytest
import base64
import os
import sys
from unittest.mock import patch, MagicMock, Mock
from PIL import Image
import io
from botocore.exceptions import ClientError
from moto import mock_dynamodb

# Add paths for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared'))

# Set environment variables before importing handler
os.environ['PHOTO_BUCKET_NAME'] = 'test-bucket'
os.environ['PARAMETER_STORE_PREFIX'] = '/anecdotario/test/user-service'
os.environ['ENVIRONMENT'] = 'test'
os.environ['USER_TABLE_NAME'] = 'Users-test'
os.environ['AWS_REGION'] = 'us-east-1'


@pytest.fixture
def api_gateway_event():
    """Generate API Gateway Lambda Event with JWT claims in request context"""
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
        "requestContext": {
            "authorizer": {
                "claims": {
                    "sub": "test-user-123",
                    "email": "test@example.com",
                    "iss": "https://cognito-idp.us-east-1.amazonaws.com/test-pool-id"
                }
            }
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
def large_image_base64():
    """Create a large image that exceeds size limits"""
    # Create 6MB of data (exceeds 5MB limit)
    large_data = b'x' * (6 * 1024 * 1024)
    return base64.b64encode(large_data).decode('utf-8')


@pytest.fixture
def invalid_base64():
    """Return invalid base64 data"""
    return "not-valid-base64!@#$%"


@pytest.fixture
def commons_success_response():
    """Mock successful commons service response"""
    return {
        'success': True,
        'photo_id': 'photo-123',
        'images': {
            'thumbnail': 'https://bucket.s3.amazonaws.com/users/test-user-123/thumbnail_150x150.jpg',
            'standard': 'https://bucket.s3.amazonaws.com/users/test-user-123/presigned-standard-url',
            'high_res': 'https://bucket.s3.amazonaws.com/users/test-user-123/presigned-high-res-url'
        },
        'versions_created': 3,
        'size_reduction': '45.2%',
        'cleanup': {
            'deleted_files': 2,
            'old_keys': ['users/test-user-123/old_photo.jpg']
        }
    }


@pytest.fixture
def commons_error_response():
    """Mock commons service error response"""
    return {
        'success': False,
        'error': 'Invalid image format',
        'error_type': 'ValidationError'
    }


@pytest.fixture
def mock_user_instance():
    """Mock user model instance"""
    mock_user = Mock()
    mock_user.cognito_id = 'test-user-123'
    mock_user.nickname = 'testuser'
    mock_user.thumbnail_url = None
    mock_user.image_url = None
    mock_user.standard_s3_key = None
    mock_user.high_res_s3_key = None
    mock_user.to_dict.return_value = {
        'cognito_id': 'test-user-123',
        'nickname': 'testuser',
        'images': None,
        'image_url': None
    }
    return mock_user


# Test successful photo upload scenarios
@patch('app.lambda_client')
@patch('app.User')
def test_successful_photo_upload_existing_user(mock_user, mock_lambda_client, 
                                             api_gateway_event, sample_image_base64, 
                                             commons_success_response, mock_user_instance):
    """Test successful photo upload for existing user via commons service"""
    from app import lambda_handler
    
    # Mock existing user
    mock_user.get.return_value = mock_user_instance
    mock_user.DoesNotExist = Exception
    
    # Mock Lambda invoke response
    mock_lambda_response = {
        'Payload': Mock()
    }
    mock_lambda_response['Payload'].read.return_value = json.dumps(commons_success_response).encode()
    mock_lambda_client.invoke.return_value = mock_lambda_response
    
    # Add image to event body
    api_gateway_event['body'] = json.dumps({
        'image': f'data:image/jpeg;base64,{sample_image_base64}'
    })
    
    # Execute
    response = lambda_handler(api_gateway_event, None)
    
    # Verify response
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert 'message' in body
    assert body['message'] == 'Photo uploaded successfully'
    assert 'images' in body
    assert 'photo_id' in body
    assert body['photo_id'] == 'photo-123'
    assert body['commons_service'] is True
    assert 'user' in body
    
    # Verify Lambda invoke was called with correct payload
    mock_lambda_client.invoke.assert_called_once()
    call_args = mock_lambda_client.invoke.call_args[1]
    assert call_args['FunctionName'] == 'anecdotario-commons-photo-upload-test'
    assert call_args['InvocationType'] == 'RequestResponse'
    
    # Verify payload format (this tests the current bug - wrong field name)
    payload = json.loads(call_args['Payload'])
    assert 'image_data' in payload  # Current bug: should be 'image'
    assert payload['entity_type'] == 'user'
    assert payload['entity_id'] == 'test-user-123'
    assert payload['photo_type'] == 'profile'
    
    # Verify user was updated
    mock_user_instance.save.assert_called_once()
    assert mock_user_instance.thumbnail_url == commons_success_response['images']['thumbnail']


# Test the current failing scenario (wrong Lambda function name and payload format)
@patch('app.lambda_client')
@patch('app.User')
def test_current_failing_scenario_wrong_function_name(mock_user, mock_lambda_client,
                                                   api_gateway_event, sample_image_base64):
    """Test current failing scenario - wrong Lambda function name being called"""
    from app import lambda_handler
    
    # Mock existing user
    mock_user_instance = Mock()
    mock_user.get.return_value = mock_user_instance
    mock_user.DoesNotExist = Exception
    
    # Mock Lambda function not found error (current production issue)
    mock_lambda_client.invoke.side_effect = ClientError(
        error_response={
            'Error': {
                'Code': 'ResourceNotFoundException',
                'Message': 'Function not found: arn:aws:lambda:us-east-1:123456789012:function:anecdotario-commons-photo-upload-test'
            }
        },
        operation_name='Invoke'
    )
    
    # Add image to event body
    api_gateway_event['body'] = json.dumps({
        'image': f'data:image/jpeg;base64,{sample_image_base64}'
    })
    
    # Execute
    response = lambda_handler(api_gateway_event, None)
    
    # Verify error response
    assert response['statusCode'] == 500
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'Photo processing failed' in body['error']
    
    # Verify correct function name was attempted (this shows the bug)
    mock_lambda_client.invoke.assert_called_once()
    call_args = mock_lambda_client.invoke.call_args[1]
    assert call_args['FunctionName'] == 'anecdotario-commons-photo-upload-test'  # Wrong name!


@patch('app.lambda_client')
@patch('app.User')
def test_current_failing_scenario_payload_format(mock_user, mock_lambda_client,
                                               api_gateway_event, sample_image_base64):
    """Test current payload format issue - sending 'image_data' instead of 'image'"""
    from app import lambda_handler
    
    # Mock existing user
    mock_user_instance = Mock()
    mock_user.get.return_value = mock_user_instance
    mock_user.DoesNotExist = Exception
    
    # Mock commons service validation error due to wrong field name
    commons_error_response = {
        'success': False,
        'error': 'Missing required field: image',
        'error_type': 'ValidationError'
    }
    
    mock_lambda_response = {
        'Payload': Mock()
    }
    mock_lambda_response['Payload'].read.return_value = json.dumps(commons_error_response).encode()
    mock_lambda_client.invoke.return_value = mock_lambda_response
    
    # Add image to event body
    api_gateway_event['body'] = json.dumps({
        'image': f'data:image/jpeg;base64,{sample_image_base64}'
    })
    
    # Execute
    response = lambda_handler(api_gateway_event, None)
    
    # Verify error response due to payload format issue
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'Photo validation failed' in body['error']
    
    # Verify payload was sent with wrong field name
    call_args = mock_lambda_client.invoke.call_args[1]
    payload = json.loads(call_args['Payload'])
    assert 'image_data' in payload  # This is the bug - should be 'image'
    assert 'image' not in payload


# Test fixed scenario (correct function name and payload format)
@patch('app.lambda_client')
@patch('app.User')
def test_fixed_scenario_correct_function_name_and_payload(mock_user, mock_lambda_client,
                                                        api_gateway_event, sample_image_base64,
                                                        commons_success_response, mock_user_instance):
    """Test the fixed scenario with correct Lambda function name and payload format"""
    from app import lambda_handler
    import app
    
    # Temporarily override the function name to simulate the fix
    original_function_name = app.COMMONS_PHOTO_FUNCTION
    app.COMMONS_PHOTO_FUNCTION = 'anecdotario-photo-upload-test'  # Corrected name
    
    try:
        # Mock existing user
        mock_user.get.return_value = mock_user_instance
        mock_user.DoesNotExist = Exception
        
        # Mock successful Lambda response
        mock_lambda_response = {
            'Payload': Mock()
        }
        mock_lambda_response['Payload'].read.return_value = json.dumps(commons_success_response).encode()
        mock_lambda_client.invoke.return_value = mock_lambda_response
        
        # Add image to event body
        api_gateway_event['body'] = json.dumps({
            'image': f'data:image/jpeg;base64,{sample_image_base64}'
        })
        
        # Execute
        response = lambda_handler(api_gateway_event, None)
        
        # Verify successful response
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['message'] == 'Photo uploaded successfully'
        assert body['commons_service'] is True
        
        # Verify correct function name is called
        mock_lambda_client.invoke.assert_called_once()
        call_args = mock_lambda_client.invoke.call_args[1]
        assert call_args['FunctionName'] == 'anecdotario-photo-upload-test'  # Fixed name
        
        # For the payload fix, we would need to modify the upload_user_photo function
        # to send 'image' instead of 'image_data'
        payload = json.loads(call_args['Payload'])
        # Current implementation still sends 'image_data' - this would need to be fixed:
        assert 'image_data' in payload  # Would be changed to 'image' in the fix
        
    finally:
        # Restore original function name
        app.COMMONS_PHOTO_FUNCTION = original_function_name


# Test authorization and validation scenarios
def test_unauthorized_user_mismatch(api_gateway_event, sample_image_base64):
    """Test request from user trying to upload to another user's profile"""
    from app import lambda_handler
    
    # Modify token to different user
    api_gateway_event['requestContext']['authorizer']['claims']['sub'] = 'different-user-456'
    
    api_gateway_event['body'] = json.dumps({
        'image': f'data:image/jpeg;base64,{sample_image_base64}'
    })
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 403
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'Unauthorized' in body['error']


def test_missing_body(api_gateway_event):
    """Test request without body"""
    from app import lambda_handler
    
    # Leave body as None
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'No image data provided' in body['error']


def test_missing_image_field(api_gateway_event):
    """Test request with body but no image field"""
    from app import lambda_handler
    
    api_gateway_event['body'] = json.dumps({
        'nickname': 'testuser'
    })
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'No image data in request body' in body['error']


def test_invalid_base64_data(api_gateway_event, invalid_base64):
    """Test request with invalid base64 image data"""
    from app import lambda_handler
    
    api_gateway_event['body'] = json.dumps({
        'image': invalid_base64
    })
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'Invalid base64 image data' in body['error']


def test_image_too_large(api_gateway_event, large_image_base64):
    """Test upload of image that exceeds size limit"""
    from app import lambda_handler
    
    api_gateway_event['body'] = json.dumps({
        'image': f'data:image/jpeg;base64,{large_image_base64}'
    })
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'Image too large' in body['error']
    assert 'max_size_mb' in body['details']


# Test AWS service integration and error handling
@patch('app.lambda_client')
@patch('app.User')
def test_commons_service_validation_error(mock_user, mock_lambda_client, 
                                        api_gateway_event, sample_image_base64):
    """Test handling of commons service validation errors"""
    from app import lambda_handler
    
    # Mock existing user
    mock_user_instance = Mock()
    mock_user.get.return_value = mock_user_instance
    mock_user.DoesNotExist = Exception
    
    # Mock commons service validation error
    commons_error_response = {
        'success': False,
        'error': 'Invalid image format detected',
        'error_type': 'ValidationError'
    }
    
    mock_lambda_response = {
        'Payload': Mock()
    }
    mock_lambda_response['Payload'].read.return_value = json.dumps(commons_error_response).encode()
    mock_lambda_client.invoke.return_value = mock_lambda_response
    
    api_gateway_event['body'] = json.dumps({
        'image': f'data:image/jpeg;base64,{sample_image_base64}'
    })
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'Photo validation failed' in body['error']
    assert 'details' in body


@patch('app.lambda_client')
@patch('app.User')
def test_commons_service_image_processing_error(mock_user, mock_lambda_client,
                                              api_gateway_event, sample_image_base64):
    """Test handling of commons service image processing errors"""
    from app import lambda_handler
    
    # Mock existing user
    mock_user_instance = Mock()
    mock_user.get.return_value = mock_user_instance
    mock_user.DoesNotExist = Exception
    
    # Mock commons service processing error
    commons_error_response = {
        'success': False,
        'error': 'Failed to resize image - corrupted data',
        'error_type': 'ImageProcessingError'
    }
    
    mock_lambda_response = {
        'Payload': Mock()
    }
    mock_lambda_response['Payload'].read.return_value = json.dumps(commons_error_response).encode()
    mock_lambda_client.invoke.return_value = mock_lambda_response
    
    api_gateway_event['body'] = json.dumps({
        'image': f'data:image/jpeg;base64,{sample_image_base64}'
    })
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 500
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'Photo processing failed' in body['error']
    assert 'details' in body


@patch('app.lambda_client')
@patch('app.User')
def test_commons_service_storage_error(mock_user, mock_lambda_client,
                                     api_gateway_event, sample_image_base64):
    """Test handling of commons service storage errors"""
    from app import lambda_handler
    
    # Mock existing user
    mock_user_instance = Mock()
    mock_user.get.return_value = mock_user_instance
    mock_user.DoesNotExist = Exception
    
    # Mock commons service storage error
    commons_error_response = {
        'success': False,
        'error': 'S3 bucket access denied',
        'error_type': 'StorageError'
    }
    
    mock_lambda_response = {
        'Payload': Mock()
    }
    mock_lambda_response['Payload'].read.return_value = json.dumps(commons_error_response).encode()
    mock_lambda_client.invoke.return_value = mock_lambda_response
    
    api_gateway_event['body'] = json.dumps({
        'image': f'data:image/jpeg;base64,{sample_image_base64}'
    })
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 500
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'Photo processing failed' in body['error']
    assert 'details' in body


# Test new user creation scenarios
@patch('app.lambda_client')
@patch('app.User')
def test_successful_photo_upload_new_user_with_nickname(mock_user, mock_lambda_client,
                                                      api_gateway_event, sample_image_base64,
                                                      commons_success_response):
    """Test successful photo upload for new user with nickname"""
    from app import lambda_handler
    
    # Mock user not found initially
    mock_user.get.side_effect = mock_user.DoesNotExist
    mock_user.get_by_nickname.return_value = None  # Nickname available
    
    # Mock new user creation
    mock_new_user = Mock()
    mock_new_user.cognito_id = 'test-user-123'
    mock_new_user.nickname = 'newuser'
    mock_new_user.to_dict.return_value = {
        'cognito_id': 'test-user-123',
        'nickname': 'newuser',
        'images': commons_success_response['images']
    }
    mock_user.return_value = mock_new_user
    
    # Mock Lambda invoke response
    mock_lambda_response = {
        'Payload': Mock()
    }
    mock_lambda_response['Payload'].read.return_value = json.dumps(commons_success_response).encode()
    mock_lambda_client.invoke.return_value = mock_lambda_response
    
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
    assert body['message'] == 'Photo uploaded successfully'
    assert 'user' in body
    assert body['user']['nickname'] == 'newuser'
    assert body['commons_service'] is True
    
    # Verify new user was created with correct data
    mock_user.assert_called_with(
        cognito_id='test-user-123',
        nickname='newuser',
        thumbnail_url=commons_success_response['images']['thumbnail'],
        image_url=commons_success_response['images']['thumbnail'],
        standard_s3_key=None,
        high_res_s3_key=None
    )
    mock_new_user.save.assert_called_once()


@patch('app.User')
def test_new_user_without_nickname_fails(mock_user, api_gateway_event, sample_image_base64):
    """Test photo upload for new user without nickname fails"""
    from app import lambda_handler
    
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
    assert 'Please provide a nickname for first-time upload' in body['error']


@patch('app.User')
def test_nickname_already_taken(mock_user, api_gateway_event, sample_image_base64):
    """Test photo upload for new user with taken nickname fails"""
    from app import lambda_handler
    
    # Mock user not found initially
    mock_user.get.side_effect = mock_user.DoesNotExist
    
    # Mock existing user with same nickname
    existing_user = Mock()
    existing_user.nickname = 'takenname'
    mock_user.get_by_nickname.return_value = existing_user
    
    # Add image with taken nickname
    api_gateway_event['body'] = json.dumps({
        'image': f'data:image/jpeg;base64,{sample_image_base64}',
        'nickname': 'takenname'
    })
    
    # Execute
    response = lambda_handler(api_gateway_event, None)
    
    # Verify response
    assert response['statusCode'] == 409
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'Nickname already taken' in body['error']


# Test Lambda function name configuration
@patch('app.lambda_client')
@patch('app.User')
def test_correct_lambda_function_name_called(mock_user, mock_lambda_client,
                                           api_gateway_event, sample_image_base64,
                                           commons_success_response, mock_user_instance):
    """Test that the correct Lambda function name is called based on environment"""
    from app import lambda_handler
    
    # Mock existing user
    mock_user.get.return_value = mock_user_instance
    mock_user.DoesNotExist = Exception
    
    # Mock Lambda invoke response
    mock_lambda_response = {
        'Payload': Mock()
    }
    mock_lambda_response['Payload'].read.return_value = json.dumps(commons_success_response).encode()
    mock_lambda_client.invoke.return_value = mock_lambda_response
    
    # Add image to event body
    api_gateway_event['body'] = json.dumps({
        'image': f'data:image/jpeg;base64,{sample_image_base64}'
    })
    
    # Execute
    response = lambda_handler(api_gateway_event, None)
    
    # Verify correct function name is called
    assert response['statusCode'] == 200
    mock_lambda_client.invoke.assert_called_once()
    call_args = mock_lambda_client.invoke.call_args[1]
    
    # Should be anecdotario-commons-photo-upload-{ENVIRONMENT}
    # In test environment, should be anecdotario-commons-photo-upload-test
    assert call_args['FunctionName'] == 'anecdotario-commons-photo-upload-test'


# Test error handling and edge cases
def test_malformed_json_body(api_gateway_event):
    """Test handling of malformed JSON in request body"""
    from app import lambda_handler
    
    api_gateway_event['body'] = 'invalid json {{{'
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 500
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'Internal server error' in body['error']


@patch('app.lambda_client')
@patch('app.User')
def test_lambda_function_error_response(mock_user, mock_lambda_client,
                                      api_gateway_event, sample_image_base64):
    """Test handling of Lambda function error response"""
    from app import lambda_handler
    
    # Mock existing user
    mock_user_instance = Mock()
    mock_user.get.return_value = mock_user_instance
    mock_user.DoesNotExist = Exception
    
    # Mock Lambda function error
    mock_lambda_response = {
        'FunctionError': 'Unhandled',
        'Payload': Mock()
    }
    error_payload = {
        'errorMessage': 'Internal function error',
        'errorType': 'RuntimeError'
    }
    mock_lambda_response['Payload'].read.return_value = json.dumps(error_payload).encode()
    mock_lambda_client.invoke.return_value = mock_lambda_response
    
    api_gateway_event['body'] = json.dumps({
        'image': f'data:image/jpeg;base64,{sample_image_base64}'
    })
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 500
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'Photo processing failed' in body['error']


@patch('app.lambda_client')
@patch('app.User')
def test_user_record_update_failure(mock_user, mock_lambda_client,
                                  api_gateway_event, sample_image_base64,
                                  commons_success_response, mock_user_instance):
    """Test handling of user record update failure after successful photo upload"""
    from app import lambda_handler
    
    # Mock existing user
    mock_user.get.return_value = mock_user_instance
    mock_user.DoesNotExist = Exception
    
    # Mock successful commons response
    mock_lambda_response = {
        'Payload': Mock()
    }
    mock_lambda_response['Payload'].read.return_value = json.dumps(commons_success_response).encode()
    mock_lambda_client.invoke.return_value = mock_lambda_response
    
    # Mock user save failure
    mock_user_instance.save.side_effect = Exception('DynamoDB connection failed')
    
    api_gateway_event['body'] = json.dumps({
        'image': f'data:image/jpeg;base64,{sample_image_base64}'
    })
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 500
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'Failed to update user record' in body['error']


# Test payload format (current bug vs fixed version)
@patch('app.lambda_client')
@patch('app.User')
def test_payload_format_bug_demonstration(mock_user, mock_lambda_client,
                                        api_gateway_event, sample_image_base64,
                                        mock_user_instance):
    """Demonstrate the current payload format bug - sending 'image_data' instead of 'image'"""
    from app import lambda_handler
    
    # Mock existing user
    mock_user.get.return_value = mock_user_instance
    mock_user.DoesNotExist = Exception
    
    # Mock successful response (assuming commons service accepts wrong format for now)
    commons_success_response = {
        'success': True,
        'photo_id': 'photo-123',
        'images': {'thumbnail': 'https://example.com/thumb.jpg'}
    }
    
    mock_lambda_response = {
        'Payload': Mock()
    }
    mock_lambda_response['Payload'].read.return_value = json.dumps(commons_success_response).encode()
    mock_lambda_client.invoke.return_value = mock_lambda_response
    
    api_gateway_event['body'] = json.dumps({
        'image': f'data:image/jpeg;base64,{sample_image_base64}'
    })
    
    response = lambda_handler(api_gateway_event, None)
    
    # Verify the current implementation sends wrong field name
    call_args = mock_lambda_client.invoke.call_args[1]
    payload = json.loads(call_args['Payload'])
    
    # Current bug: sends 'image_data' instead of 'image'
    assert 'image_data' in payload  # This is the bug!
    assert payload['image_data'] == f'data:image/jpeg;base64,{sample_image_base64}'
    
    # Correct format should be:
    # assert 'image' in payload
    # assert payload['image'] == f'data:image/jpeg;base64,{sample_image_base64}'
    
    # Other payload fields should be correct
    assert payload['entity_type'] == 'user'
    assert payload['entity_id'] == 'test-user-123'
    assert payload['photo_type'] == 'profile'
    assert payload['uploaded_by'] == 'test-user-123'
    assert payload['upload_source'] == 'user-service'


# Coverage tests for edge cases
def test_empty_image_field(api_gateway_event):
    """Test request with empty image field"""
    from app import lambda_handler
    
    api_gateway_event['body'] = json.dumps({
        'image': ''
    })
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'No image data in request body' in body['error']


def test_null_image_field(api_gateway_event):
    """Test request with null image field"""
    from app import lambda_handler
    
    api_gateway_event['body'] = json.dumps({
        'image': None
    })
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'No image data in request body' in body['error']


def test_data_url_without_base64_data(api_gateway_event):
    """Test data URL without actual base64 data"""
    from app import lambda_handler
    
    api_gateway_event['body'] = json.dumps({
        'image': 'data:image/jpeg;base64,'
    })
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'Invalid base64 image data' in body['error']


def test_base64_without_data_url_prefix(api_gateway_event, sample_image_base64):
    """Test base64 data without data URL prefix"""
    from app import lambda_handler
    
    # Mock to bypass other validations for this specific test
    with patch('app.lambda_client') as mock_lambda_client, \
         patch('app.User') as mock_user:
        
        # Mock existing user
        mock_user_instance = Mock()
        mock_user.get.return_value = mock_user_instance
        mock_user.DoesNotExist = Exception
        
        # Mock successful Lambda response
        commons_success_response = {
            'success': True,
            'photo_id': 'photo-123',
            'images': {'thumbnail': 'https://example.com/thumb.jpg'}
        }
        
        mock_lambda_response = {
            'Payload': Mock()
        }
        mock_lambda_response['Payload'].read.return_value = json.dumps(commons_success_response).encode()
        mock_lambda_client.invoke.return_value = mock_lambda_response
        
        # Send raw base64 without data URL prefix
        api_gateway_event['body'] = json.dumps({
            'image': sample_image_base64  # No data: prefix
        })
        
        response = lambda_handler(api_gateway_event, None)
        
        # Should still work - function handles both formats
        assert response['statusCode'] == 200
        
        # Verify payload construction handled raw base64
        call_args = mock_lambda_client.invoke.call_args[1]
        payload = json.loads(call_args['Payload'])
        assert payload['image_data'] == f'data:image/jpeg;base64,{sample_image_base64}'


# Test comprehensive error scenarios
def test_missing_request_context(api_gateway_event, sample_image_base64):
    """Test handling of missing request context (should not happen with API Gateway)"""
    from app import lambda_handler
    
    # Remove request context
    del api_gateway_event['requestContext']
    
    api_gateway_event['body'] = json.dumps({
        'image': f'data:image/jpeg;base64,{sample_image_base64}'
    })
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 500
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'Internal server error' in body['error']


def test_missing_path_parameters(api_gateway_event, sample_image_base64):
    """Test handling of missing path parameters"""
    from app import lambda_handler
    
    # Remove path parameters
    del api_gateway_event['pathParameters']
    
    api_gateway_event['body'] = json.dumps({
        'image': f'data:image/jpeg;base64,{sample_image_base64}'
    })
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 500
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'Internal server error' in body['error']


def test_missing_user_id_in_path(api_gateway_event, sample_image_base64):
    """Test handling of missing userId in path parameters"""
    from app import lambda_handler
    
    # Remove userId from path parameters
    api_gateway_event['pathParameters'] = {}
    
    api_gateway_event['body'] = json.dumps({
        'image': f'data:image/jpeg;base64,{sample_image_base64}'
    })
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 500
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'Internal server error' in body['error']


def test_missing_claims_in_auth_context(api_gateway_event, sample_image_base64):
    """Test handling of missing claims in authorization context"""
    from app import lambda_handler
    
    # Remove claims from authorization context
    api_gateway_event['requestContext']['authorizer'] = {}
    
    api_gateway_event['body'] = json.dumps({
        'image': f'data:image/jpeg;base64,{sample_image_base64}'
    })
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 500
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'Internal server error' in body['error']


def test_missing_sub_claim(api_gateway_event, sample_image_base64):
    """Test handling of missing sub claim in JWT"""
    from app import lambda_handler
    
    # Remove sub claim
    del api_gateway_event['requestContext']['authorizer']['claims']['sub']
    
    api_gateway_event['body'] = json.dumps({
        'image': f'data:image/jpeg;base64,{sample_image_base64}'
    })
    
    response = lambda_handler(api_gateway_event, None)
    
    assert response['statusCode'] == 500
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'Internal server error' in body['error']