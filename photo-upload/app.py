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
# Simple response functions - no auth validation needed since API Gateway handles it
try:
    from auth_simplified import create_response, create_error_response
except ImportError:
    # Fallback to full auth module if simplified not available
    from auth import create_response, create_error_response


s3_client = boto3.client('s3')
cognito_client = boto3.client('cognito-idp')

# Critical configuration from SSM (environment-specific/sensitive)
PHOTO_BUCKET_NAME = config.get_ssm_parameter('photo-bucket-name', os.environ.get('PHOTO_BUCKET_NAME'))

# Static configuration from local .env files
MAX_IMAGE_SIZE = config.get_int_parameter('max-image-size', 5242880)
JPEG_QUALITY = config.get_int_parameter('image-jpeg-quality', 85)
WEBP_QUALITY = config.get_int_parameter('image-webp-quality', 85)
ENABLE_WEBP = config.get_bool_parameter('enable-webp-support', True)

# Multi-version image settings
THUMBNAIL_SIZE = config.get_int_parameter('thumbnail-size', 150)
STANDARD_SIZE = config.get_int_parameter('standard-size', 320)
HIGH_RES_SIZE = config.get_int_parameter('high-res-size', 800)
THUMBNAIL_QUALITY = config.get_int_parameter('thumbnail-quality', 80)
STANDARD_QUALITY = config.get_int_parameter('standard-quality', 85)
HIGH_RES_QUALITY = config.get_int_parameter('high-res-quality', 90)

# Security and application settings from local .env files
ALLOWED_EXTENSIONS = set(config.get_list_parameter('allowed-image-extensions', default=['.jpg', '.jpeg', '.png', '.gif']))


def create_image_versions(image_data):
    """
    Create multiple versions of an image (Instagram-style)
    Returns: dict with thumbnail, standard, and high_res image data
    """
    versions = {}
    
    try:
        # Open and process the original image
        image = Image.open(io.BytesIO(image_data))
        
        # Strip EXIF data for privacy and size reduction
        if hasattr(image, '_getexif') and image._getexif():
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
        
        # Create versions
        version_configs = [
            ('thumbnail', THUMBNAIL_SIZE, THUMBNAIL_QUALITY),
            ('standard', STANDARD_SIZE, STANDARD_QUALITY),
            ('high_res', HIGH_RES_SIZE, HIGH_RES_QUALITY)
        ]
        
        for version_name, size, quality in version_configs:
            # Create a copy for this version
            version_image = image.copy()
            
            # Resize to square aspect ratio (crop center if needed)
            # Instagram-style: crop to square from center
            width, height = version_image.size
            min_dimension = min(width, height)
            
            # Crop to square from center
            left = (width - min_dimension) // 2
            top = (height - min_dimension) // 2
            right = left + min_dimension
            bottom = top + min_dimension
            
            version_image = version_image.crop((left, top, right, bottom))
            
            # Resize to target size
            version_image = version_image.resize((size, size), Image.Resampling.LANCZOS)
            
            # Save to bytes
            output_buffer = io.BytesIO()
            version_image.save(
                output_buffer, 
                format='JPEG', 
                quality=quality, 
                optimize=True, 
                progressive=True
            )
            
            versions[version_name] = output_buffer.getvalue()
        
        return versions
        
    except Exception as e:
        raise ValueError(f"Failed to process image: {str(e)}")


def delete_existing_photos(user, bucket_name):
    """
    Delete existing photo files from S3 when updating a user's photo
    
    Args:
        user: User model instance with existing photo data
        bucket_name: S3 bucket name
        
    Returns:
        list: List of deleted S3 keys
    """
    deleted_files = []
    
    if not bucket_name:
        return deleted_files
    
    try:
        # Get existing S3 keys from user record
        existing_keys = []
        
        # Extract S3 keys from URLs and direct keys
        if user.thumbnail_url and 's3.amazonaws.com' in user.thumbnail_url:
            # Extract key from URL: https://bucket.s3.amazonaws.com/path/file.jpg
            key = user.thumbnail_url.split('.s3.amazonaws.com/')[-1]
            existing_keys.append(key)
        
        if user.standard_s3_key:
            existing_keys.append(user.standard_s3_key)
            
        if user.high_res_s3_key:
            existing_keys.append(user.high_res_s3_key)
        
        # Also check legacy image_url
        if user.image_url and 's3.amazonaws.com' in user.image_url:
            key = user.image_url.split('.s3.amazonaws.com/')[-1]
            if key not in existing_keys:
                existing_keys.append(key)
        
        # Delete each existing file
        for key in existing_keys:
            if key:  # Ensure key is not empty
                try:
                    s3_client.delete_object(
                        Bucket=bucket_name,
                        Key=key
                    )
                    deleted_files.append(key)
                    print(f"Deleted old photo: {key}")
                except ClientError as e:
                    print(f"Failed to delete old photo {key}: {str(e)}")
                    # Continue with other deletions
                    
    except Exception as e:
        print(f"Error during old photo cleanup: {str(e)}")
        # Don't fail the upload if cleanup fails
    
    return deleted_files


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
        
        # Create multiple image versions (Instagram-style)
        try:
            image_versions = create_image_versions(body)
        except ValueError as e:
            return create_error_response(
                400,
                'Failed to process image',
                event,
                {'error': str(e)}
            )
        
        # Generate unique filename base
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        unique_id = str(uuid.uuid4())[:8]
        
        # Upload all versions to S3 and collect URLs
        image_urls = {}
        s3_keys = {}  # Store S3 keys for database
        try:
            for version_name, image_data in image_versions.items():
                filename = f"users/{user_id}/{version_name}_{timestamp}_{unique_id}.jpg"
                s3_keys[version_name] = filename
                
                s3_client.put_object(
                    Bucket=PHOTO_BUCKET_NAME,
                    Key=filename,
                    Body=image_data,
                    ContentType='image/jpeg',
                    CacheControl='max-age=31536000',  # 1 year cache
                    Metadata={
                        'user_id': user_id,
                        'version': version_name,
                        'upload_timestamp': datetime.utcnow().isoformat(),
                        'original_size': str(len(body)),
                        'optimized_size': str(len(image_data))
                    }
                )
                
                # Generate URLs based on version type
                if version_name == 'thumbnail':
                    # Thumbnail is publicly accessible
                    image_urls[f"{version_name}_url"] = f"https://{PHOTO_BUCKET_NAME}.s3.amazonaws.com/{filename}"
                else:
                    # Standard and high_res require presigned URLs (7 days expiry)
                    presigned_url = s3_client.generate_presigned_url(
                        'get_object',
                        Params={'Bucket': PHOTO_BUCKET_NAME, 'Key': filename},
                        ExpiresIn=604800  # 7 days in seconds
                    )
                    image_urls[f"{version_name}_url"] = presigned_url
            
        except ClientError as e:
            return create_error_response(
                500,
                'Failed to upload image',
                event,
                {'details': str(e)}
            )
        
        # Update or create user record with image URLs and S3 keys
        deleted_old_files = []
        try:
            # Try to get existing user
            user = User.get(user_id)
            
            # Delete old photos before updating with new URLs
            deleted_old_files = delete_existing_photos(user, PHOTO_BUCKET_NAME)
            
            # Update thumbnail URL (public) and S3 keys (for presigned URLs)
            user.thumbnail_url = image_urls.get('thumbnail_url')
            user.standard_s3_key = s3_keys.get('standard')
            user.high_res_s3_key = s3_keys.get('high_res')
            user.image_url = image_urls.get('thumbnail_url')  # Backward compatibility - use public thumbnail
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
            
            # Create new user with thumbnail URL and S3 keys
            user = User(
                cognito_id=user_id,
                nickname=nickname,
                thumbnail_url=image_urls.get('thumbnail_url'),
                standard_s3_key=s3_keys.get('standard'),
                high_res_s3_key=s3_keys.get('high_res'),
                image_url=image_urls.get('thumbnail_url')  # Backward compatibility - use public thumbnail
            )
            user.save()
        
        # Calculate total size reduction across all versions
        total_optimized_size = sum(len(data) for data in image_versions.values())
        size_reduction = f"{(1 - total_optimized_size / len(body)) * 100:.1f}%"
        
        # Return success response with all image versions
        # Include presigned URLs since user is authenticated
        return create_response(
            200,
            json.dumps({
                'message': 'Photo uploaded successfully',
                'images': {
                    'thumbnail': image_urls.get('thumbnail_url'),
                    'standard': image_urls.get('standard_url'),  # Presigned URL
                    'high_res': image_urls.get('high_res_url')   # Presigned URL
                },
                'photo_url': image_urls.get('thumbnail_url'),  # Backward compatibility - public thumbnail
                'versions_created': len(image_versions),
                'size_reduction': size_reduction,
                'old_files_deleted': deleted_old_files if deleted_old_files else None,
                'user': user.to_dict(include_presigned_urls=True, s3_client=s3_client)
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