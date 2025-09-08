import json
import base64
import os
import sys
import boto3
import logging

# Add shared directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))
from models.user import User
from config import config
# Simple response functions - no auth validation needed since API Gateway handles it
try:
    from auth_simplified import create_response, create_error_response
except ImportError:
    # Fallback to full auth module if simplified not available
    from auth import create_response, create_error_response

# Import commons service contracts (from CodeArtifact package)
try:
    from anecdotario_commons.contracts import PhotoContracts
    from anecdotario_commons.exceptions import ValidationError, ImageProcessingError, StorageError
except ImportError:
    # Fallback if commons package not available
    PhotoContracts = None
    ValidationError = Exception
    ImageProcessingError = Exception
    StorageError = Exception

# Initialize AWS clients
lambda_client = boto3.client('lambda')
s3_client = boto3.client('s3')

# Configuration
MAX_IMAGE_SIZE = config.get_int_parameter('max-image-size', 5242880)
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
COMMONS_PHOTO_FUNCTION = f"anecdotario-photo-upload-{ENVIRONMENT}"

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def upload_user_photo(image_data_b64, entity_id, nickname=None, uploaded_by=None):
    """
    Upload user photo using commons service Lambda function
    
    Args:
        image_data_b64: Base64 encoded image data (without data URL prefix)
        entity_id: User ID (Cognito sub)
        nickname: User nickname (optional, for new users)
        uploaded_by: User who uploaded (typically same as entity_id)
        
    Returns:
        Photo upload result data
        
    Raises:
        ValidationError, ImageProcessingError, StorageError: From commons service
    """
    # Prepare payload for commons service Lambda
    payload = {
        "image": f"data:image/jpeg;base64,{image_data_b64}",
        "entity_type": "user",
        "entity_id": entity_id,
        "photo_type": "profile",
        "uploaded_by": uploaded_by or entity_id,
        "upload_source": "user-service"
    }
    
    logger.info(f"Invoking commons photo service for entity: {entity_id}")
    
    try:
        # Invoke commons service Lambda function
        response = lambda_client.invoke(
            FunctionName=COMMONS_PHOTO_FUNCTION,
            InvocationType='RequestResponse',  # Synchronous invocation
            Payload=json.dumps(payload)
        )
        
        # Parse response
        response_payload = json.loads(response['Payload'].read())
        
        # Check for function errors
        if response.get('FunctionError'):
            logger.error(f"Commons service function error: {response_payload}")
            raise StorageError(f"Commons service error: {response_payload.get('errorMessage', 'Unknown error')}")
        
        # Check for application errors in response
        if not response_payload.get('success', False):
            error_type = response_payload.get('error_type', 'UnknownError')
            error_message = response_payload.get('error', 'Photo upload failed')
            
            # Map error types to appropriate exceptions
            if error_type == 'ValidationError':
                raise ValidationError(error_message)
            elif error_type == 'ImageProcessingError':
                raise ImageProcessingError(error_message)
            else:
                raise StorageError(error_message)
        
        logger.info(f"Photo upload successful: {response_payload.get('photo_id')}")
        return response_payload
        
    except Exception as e:
        logger.error(f"Failed to invoke commons photo service: {str(e)}")
        if isinstance(e, (ValidationError, ImageProcessingError, StorageError)):
            raise
        raise StorageError(f"Failed to invoke commons photo service: {str(e)}")


def update_user_with_photo_data(user, user_id, commons_response_data, nickname=None):
    """
    Update or create user record with photo data from commons service
    
    Args:
        user: Existing user model instance or None for new users
        user_id: Cognito user ID
        commons_response_data: Response data from commons service
        nickname: Nickname for new users
        
    Returns:
        Updated or created User model instance
    """
    images = commons_response_data.get('images', {})
    
    if user:
        # Update existing user
        print(f"Updating existing user record: {user.nickname}")
        user.thumbnail_url = images.get('thumbnail')
        user.image_url = images.get('thumbnail')  # Backward compatibility
        
        # Clear old S3 keys since commons service manages them now
        # We'll rely on the commons service's Photo model for S3 key tracking
        user.standard_s3_key = None
        user.high_res_s3_key = None
        
        user.save()
        print(f"User record updated successfully")
    else:
        # Create new user
        if not nickname:
            raise ValueError("Nickname is required for new user creation")
            
        print(f"Creating new user record with nickname: {nickname}")
        user = User(
            cognito_id=user_id,
            nickname=nickname,
            thumbnail_url=images.get('thumbnail'),
            image_url=images.get('thumbnail'),  # Backward compatibility
            standard_s3_key=None,  # Managed by commons service now
            high_res_s3_key=None   # Managed by commons service now
        )
        user.save()
        print(f"New user created successfully")
        
    return user


def lambda_handler(event, context):
    """Lambda handler for photo upload - handles POST /users/{userId}/photo"""
    try:
        # API Gateway already validated JWT token, extract user info
        token_user_id = event['requestContext']['authorizer']['claims']['sub']
        user_id = event['pathParameters']['userId']
        
        # Verify that the token belongs to the user trying to upload
        if token_user_id != user_id:
            return create_error_response(
                403, 
                'Unauthorized to upload photo for this user',
                event
            )
        
        # Parse request body
        if not event.get('body'):
            return create_error_response(
                400,
                'No image data provided',
                event
            )
        
        # Parse body JSON
        body_json = json.loads(event['body'])
        image_data = body_json.get('image')
        nickname = body_json.get('nickname')  # Extract nickname if provided
        
        if not image_data:
            return create_error_response(
                400,
                'No image data in request body',
                event
            )
        
        # Remove data URL prefix if present and extract base64 data
        if ',' in image_data:
            image_data_b64 = image_data.split(',')[1]
        else:
            image_data_b64 = image_data
            
        # Decode to check size (but we'll pass base64 to commons service)
        try:
            body = base64.b64decode(image_data_b64)
        except Exception:
            return create_error_response(
                400,
                'Invalid base64 image data',
                event
            )
        
        # Check file size
        if len(body) > MAX_IMAGE_SIZE:
            return create_error_response(
                400,
                'Image too large',
                event,
                {'max_size_mb': MAX_IMAGE_SIZE / 1024 / 1024}
            )
        
        # Get existing user (if any) for nickname validation
        user = None
        try:
            user = User.get(user_id)
            print(f"Found existing user: {user.nickname}")
        except User.DoesNotExist:
            print(f"User {user_id} not found, will create new user")
            
            # User doesn't exist, check if nickname was provided
            if not nickname:
                return create_error_response(
                    400,
                    'User not found. Please provide a nickname for first-time upload.',
                    event
                )
            
            # Check if nickname already exists
            print(f"Checking if nickname '{nickname}' is available")
            existing_user = User.get_by_nickname(nickname)
            if existing_user:
                return create_error_response(
                    409,
                    'Nickname already taken',
                    event
                )
        
        # Upload photo using commons PhotoService
        print(f"Uploading photo using commons PhotoService")
        try:
            commons_response = upload_user_photo(
                image_data_b64, 
                user_id, 
                nickname, 
                user_id
            )
            print(f"Photo upload successful: {commons_response.get('photo_id')}")
        except ValidationError as e:
            return create_error_response(
                400,
                'Photo validation failed',
                event,
                {'details': str(e)}
            )
        except (ImageProcessingError, StorageError) as e:
            return create_error_response(
                500,
                'Photo processing failed',
                event,
                {'details': str(e)}
            )
        except Exception as e:
            return create_error_response(
                500,
                'Photo upload failed',
                event,
                {'details': str(e)}
            )
        
        # Update or create user record with photo data from commons service
        try:
            user = update_user_with_photo_data(user, user_id, commons_response, nickname)
        except Exception as e:
            print(f"Failed to update user record: {str(e)}")
            return create_error_response(
                500,
                'Failed to update user record',
                event,
                {'details': str(e)}
            )
        
        # Generate presigned URLs for protected versions using commons photo data
        images = commons_response.get('images', {})
        if 'standard' in images or 'high_res' in images:
            # The commons service already provides presigned URLs
            print(f"Using presigned URLs from commons service")
        
        # Return success response with data from commons service
        response_data = {
            'message': 'Photo uploaded successfully',
            'images': images,
            'photo_url': images.get('thumbnail'),  # Backward compatibility
            'versions_created': commons_response.get('versions_created', 3),
            'size_reduction': commons_response.get('size_reduction', '0.0%'),
            'photo_id': commons_response.get('photo_id'),
            'commons_service': True,  # Indicate this was processed by commons service
            'cleanup': commons_response.get('cleanup', {}),
            'user': user.to_dict(include_presigned_urls=True, s3_client=s3_client)
        }
        
        response = create_response(
            200,
            json.dumps(response_data),
            event,
            ['POST']
        )
        
        print(f"Photo upload completed successfully via commons service - returning response")
        return response
        
    except Exception as e:
        return create_error_response(
            500,
            'Internal server error',
            event,
            {'details': str(e)}
        )