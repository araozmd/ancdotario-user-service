import json
import base64
import os
import sys
import boto3
from PIL import Image
from PIL.ExifTags import TAGS
import io
from datetime import datetime
import uuid
from botocore.exceptions import ClientError

# Add shared directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))
from models.user import User
from config import config
# Use simplified auth when API Gateway handles JWT validation
try:
    from auth_simplified import get_authenticated_user, handle_options_request, create_response, create_error_response
except ImportError:
    # Fallback to full auth module if simplified not available
    from auth import validate_request_auth as get_authenticated_user, handle_options_request, create_response, create_error_response


s3_client = boto3.client('s3')
cognito_client = boto3.client('cognito-idp')

# Critical configuration from SSM (environment-specific/sensitive)
PHOTO_BUCKET_NAME = config.get_ssm_parameter('photo-bucket-name', os.environ.get('PHOTO_BUCKET_NAME'))

# Static configuration from local .env files
MAX_IMAGE_SIZE = config.get_int_parameter('max-image-size', 5242880)
MAX_WIDTH = config.get_int_parameter('image-max-width', 1920)
MAX_HEIGHT = config.get_int_parameter('image-max-height', 1080)
JPEG_QUALITY = config.get_int_parameter('image-jpeg-quality', 85)
WEBP_QUALITY = config.get_int_parameter('image-webp-quality', 85)
ENABLE_WEBP = config.get_bool_parameter('enable-webp-support', True)

# Security and application settings from local .env files
ALLOWED_EXTENSIONS = set(config.get_list_parameter('allowed-image-extensions', default=['.jpg', '.jpeg', '.png', '.gif']))
JWT_TOKEN_EXPIRY_TOLERANCE = config.get_int_parameter('jwt-token-expiry-tolerance', 300)


def lambda_handler(event, context):
    """Lambda handler for photo upload"""
    
    # Handle preflight OPTIONS request
    if event['httpMethod'] == 'OPTIONS':
        return handle_options_request(event)
    
    # Only handle POST requests for photo upload
    if event['httpMethod'] == 'POST':
        return handle_photo_upload(event)
    
    return create_error_response(
        405, 
        'Method not allowed. This endpoint only supports photo uploads.',
        event,
        ['POST']
    )


def handle_photo_upload(event):
    """Handle POST request for photo upload"""
    try:
        # Get authenticated user from API Gateway context
        claims, error_response = get_authenticated_user(event)
        if error_response:
            return error_response
        
        # Extract user ID from path
        user_id = event['pathParameters']['userId']
        
        # Verify that the token belongs to the user trying to upload
        token_user_id = claims.get('sub')
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
        body_json = {}
        nickname = None
        
        # Check if body is base64 encoded
        if event.get('isBase64Encoded', False):
            body = base64.b64decode(event['body'])
        else:
            # Assume the body contains a JSON with base64 image data
            body_json = json.loads(event['body'])
            image_data = body_json.get('image')
            nickname = body_json.get('nickname')  # Extract nickname if provided
            
            if not image_data:
                return create_error_response(
                    400,
                    'No image data in request body',
                    event
                )
            
            # Remove data URL prefix if present
            if ',' in image_data:
                image_data = image_data.split(',')[1]
            
            body = base64.b64decode(image_data)
        
        # Check file size
        if len(body) > MAX_IMAGE_SIZE:
            return create_error_response(
                400,
                'Image too large',
                event,
                {'max_size_mb': MAX_IMAGE_SIZE / 1024 / 1024}
            )
        
        # Process and optimize image
        try:
            image = Image.open(io.BytesIO(body))
            
            # Strip EXIF data for privacy and size reduction
            # Remove EXIF data by copying image data
            if hasattr(image, '_getexif') and image._getexif():
                # Create a new image without EXIF data
                data = list(image.getdata())
                image_without_exif = Image.new(image.mode, image.size)
                image_without_exif.putdata(data)
                image = image_without_exif
            
            # Convert RGBA to RGB if necessary
            if image.mode in ('RGBA', 'LA'):
                background = Image.new('RGB', image.size, (255, 255, 255))
                background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
                image = background
            elif image.mode not in ('RGB', 'L'):
                image = image.convert('RGB')
            
            # Resize if necessary
            image.thumbnail((MAX_WIDTH, MAX_HEIGHT), Image.Resampling.LANCZOS)
            
            # Determine format based on Accept header (check if client supports WebP)
            accept_header = event.get('headers', {}).get('Accept', '')
            use_webp = ENABLE_WEBP and 'image/webp' in accept_header
            
            # Save optimized image to bytes
            output_buffer = io.BytesIO()
            if use_webp:
                image.save(output_buffer, format='WEBP', quality=WEBP_QUALITY, optimize=True, method=6)
                image_format = 'webp'
                content_type = 'image/webp'
            else:
                # Use progressive JPEG for better perceived loading performance
                image.save(output_buffer, format='JPEG', quality=JPEG_QUALITY, optimize=True, progressive=True)
                image_format = 'jpeg'
                content_type = 'image/jpeg'
            optimized_image = output_buffer.getvalue()
            
        except Exception as e:
            return create_error_response(
                400,
                'Invalid image format',
                event,
                {'details': str(e)}
            )
        
        # Generate unique filename
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        unique_id = str(uuid.uuid4())[:8]
        extension = 'webp' if use_webp else 'jpg'
        filename = f"{user_id}/profile_{timestamp}_{unique_id}.{extension}"
        
        # Upload to S3
        try:
            s3_client.put_object(
                Bucket=PHOTO_BUCKET_NAME,
                Key=filename,
                Body=optimized_image,
                ContentType=content_type,
                Metadata={
                    'user_id': user_id,
                    'upload_timestamp': datetime.utcnow().isoformat(),
                    'original_size': str(len(body)),
                    'optimized_size': str(len(optimized_image)),
                    'format': image_format
                }
            )
            
            # Generate public URL for the uploaded image
            photo_url = f"https://{PHOTO_BUCKET_NAME}.s3.amazonaws.com/{filename}"
            
        except ClientError as e:
            return create_error_response(
                500,
                'Failed to upload image',
                event,
                {'details': str(e)}
            )
        
        # Update or create user record with image URL
        try:
            # Try to get existing user
            user = User.get(user_id)
            user.image_url = photo_url
            user.save()
        except User.DoesNotExist:
            # User doesn't exist, check if nickname was provided
            if not nickname:
                return create_error_response(
                    400,
                    'User not found. Please provide a nickname for first-time upload.',
                    event
                )
            
            # Check if nickname already exists
            existing_user = User.get_by_nickname(nickname)
            if existing_user:
                return create_error_response(
                    409,
                    'Nickname already taken',
                    event
                )
            
            # Create new user
            user = User(
                cognito_id=user_id,
                nickname=nickname,
                image_url=photo_url
            )
            user.save()
        
        # Return success response
        return create_response(
            200,
            json.dumps({
                'message': 'Photo uploaded successfully',
                'photo_url': photo_url,
                's3_key': filename,
                'size_reduction': f"{(1 - len(optimized_image) / len(body)) * 100:.1f}%",
                'image_format': image_format,
                'user': user.to_dict()
            }),
            event,
            ['POST']
        )
        
    except Exception as e:
        return create_error_response(
            500,
            'Internal server error',
            event,
            {'details': str(e)}
        )