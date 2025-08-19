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


def delete_user_photos_optimized(user, user_id, bucket_name):
    """
    Optimized photo cleanup - only scans S3 if user has existing photos in database
    
    For efficiency, this function first checks if the user has any photos tracked
    in the database. If so, it uses a targeted approach to clean up S3.
    
    Args:
        user: User model instance (can be None for new users)
        user_id: Cognito user ID 
        bucket_name: S3 bucket name
        
    Returns:
        dict: Cleanup results with deleted files and any errors
    """
    cleanup_result = {
        'deleted_files': [],
        'deletion_errors': [],
        'files_scanned': 0,
        'strategy': 'none'
    }
    
    if not bucket_name:
        return cleanup_result
    
    try:
        # Check if user has existing photos in database
        has_photos = user and (
            user.thumbnail_url or 
            user.standard_s3_key or 
            user.high_res_s3_key or 
            user.image_url
        )
        
        if not has_photos:
            # New user or no photos - skip S3 scan for performance
            cleanup_result['strategy'] = 'skip_no_photos'
            print(f"No existing photos for user {user_id}, skipping S3 cleanup")
            return cleanup_result
        
        # User has existing photos - use targeted cleanup
        cleanup_result['strategy'] = 'targeted'
        print(f"User has existing photos, performing targeted S3 cleanup")
        
        # First, delete known photo keys from database
        known_keys = []
        
        # Extract known S3 keys
        if user.standard_s3_key:
            known_keys.append(user.standard_s3_key)
        if user.high_res_s3_key:
            known_keys.append(user.high_res_s3_key)
            
        # Extract keys from URLs
        if user.thumbnail_url and 's3.amazonaws.com' in user.thumbnail_url:
            key = user.thumbnail_url.split('.s3.amazonaws.com/')[-1].split('?')[0]  # Remove query params
            known_keys.append(key)
            
        if user.image_url and 's3.amazonaws.com' in user.image_url and user.image_url != user.thumbnail_url:
            key = user.image_url.split('.s3.amazonaws.com/')[-1].split('?')[0]
            known_keys.append(key)
        
        # Batch delete known keys (much faster than individual deletes)
        if known_keys:
            delete_objects = [{'Key': key} for key in known_keys if key]
            
            if delete_objects:
                try:
                    response = s3_client.delete_objects(
                        Bucket=bucket_name,
                        Delete={'Objects': delete_objects}
                    )
                    
                    # Track successful deletions
                    for deleted in response.get('Deleted', []):
                        cleanup_result['deleted_files'].append(deleted['Key'])
                        
                    # Track errors
                    for error in response.get('Errors', []):
                        cleanup_result['deletion_errors'].append({
                            'key': error['Key'],
                            'error': error['Message'],
                            'error_code': error['Code']
                        })
                        
                    cleanup_result['files_scanned'] = len(delete_objects)
                    print(f"Batch deleted {len(cleanup_result['deleted_files'])} known photos")
                    
                except ClientError as e:
                    print(f"Batch delete failed: {str(e)}")
                    # Fallback to individual deletes for known keys
                    for key in known_keys:
                        if key:
                            try:
                                s3_client.delete_object(Bucket=bucket_name, Key=key)
                                cleanup_result['deleted_files'].append(key)
                                cleanup_result['files_scanned'] += 1
                            except ClientError as del_e:
                                cleanup_result['deletion_errors'].append({
                                    'key': key,
                                    'error': str(del_e),
                                    'error_code': del_e.response.get('Error', {}).get('Code', 'Unknown')
                                })
        
        # Quick scan for any orphaned files (limited to first 100 objects)
        # This catches files that might not be tracked in database
        user_prefix = f"users/{user_id}/"
        
        try:
            response = s3_client.list_objects_v2(
                Bucket=bucket_name,
                Prefix=user_prefix,
                MaxKeys=100  # Limit for performance
            )
            
            if 'Contents' in response:
                orphaned_keys = []
                for obj in response['Contents']:
                    key = obj['Key']
                    if key not in cleanup_result['deleted_files']:  # Not already deleted
                        orphaned_keys.append(key)
                
                # Batch delete orphaned files
                if orphaned_keys:
                    delete_objects = [{'Key': key} for key in orphaned_keys]
                    try:
                        response = s3_client.delete_objects(
                            Bucket=bucket_name,
                            Delete={'Objects': delete_objects}
                        )
                        
                        for deleted in response.get('Deleted', []):
                            cleanup_result['deleted_files'].append(deleted['Key'])
                            
                        for error in response.get('Errors', []):
                            cleanup_result['deletion_errors'].append({
                                'key': error['Key'],
                                'error': error['Message'],
                                'error_code': error['Code']
                            })
                            
                        cleanup_result['files_scanned'] += len(delete_objects)
                        print(f"Cleaned up {len(orphaned_keys)} orphaned files")
                        
                    except ClientError as e:
                        print(f"Orphaned file cleanup failed: {str(e)}")
                        
        except ClientError as e:
            print(f"Orphaned file scan failed: {str(e)}")
            # Non-critical error, continue
        
        print(f"Optimized cleanup complete: {len(cleanup_result['deleted_files'])} files deleted, "
              f"{len(cleanup_result['deletion_errors'])} errors, "
              f"{cleanup_result['files_scanned']} files scanned")
                        
    except Exception as e:
        print(f"Unexpected error during optimized photo cleanup: {str(e)}")
        cleanup_result['deletion_errors'].append({
            'operation': 'cleanup',
            'error': str(e),
            'error_code': 'UnexpectedError'
        })
    
    return cleanup_result


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
        print(f"Starting S3 upload for {len(image_versions)} image versions")
        
        try:
            for version_name, image_data in image_versions.items():
                filename = f"users/{user_id}/{version_name}_{timestamp}_{unique_id}.jpg"
                s3_keys[version_name] = filename
                print(f"Uploading {version_name} version: {filename} ({len(image_data)} bytes)")
                
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
                print(f"Successfully uploaded {version_name} to S3: {filename}")
                
                # Generate URLs based on version type
                if version_name == 'thumbnail':
                    # Thumbnail is publicly accessible
                    image_urls[f"{version_name}_url"] = f"https://{PHOTO_BUCKET_NAME}.s3.amazonaws.com/{filename}"
                    print(f"Generated public thumbnail URL: {image_urls[f'{version_name}_url']}")
                else:
                    # Standard and high_res require presigned URLs (7 days expiry)
                    presigned_url = s3_client.generate_presigned_url(
                        'get_object',
                        Params={'Bucket': PHOTO_BUCKET_NAME, 'Key': filename},
                        ExpiresIn=604800  # 7 days in seconds
                    )
                    image_urls[f"{version_name}_url"] = presigned_url
                    print(f"Generated presigned URL for {version_name}: {len(presigned_url)} chars")
            
            print(f"All S3 uploads completed successfully. Total URLs generated: {len(image_urls)}")
            
        except ClientError as e:
            return create_error_response(
                500,
                'Failed to upload image',
                event,
                {'details': str(e)}
            )
        
        # Update or create user record with image URLs and S3 keys
        cleanup_result = {'deleted_files': [], 'deletion_errors': [], 'files_scanned': 0}
        print(f"Starting database operations for user: {user_id}")
        
        try:
            # Try to get existing user
            user = User.get(user_id)
            print(f"Found existing user: {user.nickname}")
            
            # Optimized cleanup: Smart deletion based on database state
            # This is much faster than comprehensive scanning
            cleanup_result = delete_user_photos_optimized(user, user_id, PHOTO_BUCKET_NAME)
            
            # Update thumbnail URL (public) and S3 keys (for presigned URLs)
            user.thumbnail_url = image_urls.get('thumbnail_url')
            user.standard_s3_key = s3_keys.get('standard')
            user.high_res_s3_key = s3_keys.get('high_res')
            user.image_url = image_urls.get('thumbnail_url')  # Backward compatibility - use public thumbnail
            print(f"Updating user record with new photo URLs")
            user.save()
            print(f"User record updated successfully")
        except User.DoesNotExist:
            print(f"User {user_id} not found, creating new user")
            
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
            
            # For new users, no cleanup needed (optimized)
            cleanup_result = delete_user_photos_optimized(None, user_id, PHOTO_BUCKET_NAME)
            
            # Create new user with thumbnail URL and S3 keys
            print(f"Creating new user record with nickname: {nickname}")
            user = User(
                cognito_id=user_id,
                nickname=nickname,
                thumbnail_url=image_urls.get('thumbnail_url'),
                standard_s3_key=s3_keys.get('standard'),
                high_res_s3_key=s3_keys.get('high_res'),
                image_url=image_urls.get('thumbnail_url')  # Backward compatibility - use public thumbnail
            )
            user.save()
            print(f"New user created successfully")
        
        # Calculate total size reduction across all versions
        total_optimized_size = sum(len(data) for data in image_versions.values())
        size_reduction = f"{(1 - total_optimized_size / len(body)) * 100:.1f}%"
        
        print(f"Preparing success response with {len(image_urls)} image URLs")
        print(f"Response data: versions={len(image_versions)}, size_reduction={size_reduction}")
        
        # Return success response with all image versions
        # Include presigned URLs since user is authenticated
        response = create_response(
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
                'cleanup': {
                    'files_scanned': cleanup_result['files_scanned'],
                    'files_deleted': len(cleanup_result['deleted_files']),
                    'deleted_files': cleanup_result['deleted_files'] if cleanup_result['deleted_files'] else None,
                    'deletion_errors': cleanup_result['deletion_errors'] if cleanup_result['deletion_errors'] else None
                },
                'user': user.to_dict(include_presigned_urls=True, s3_client=s3_client)
            }),
            event,
            ['POST']
        )
        
        print(f"Photo upload completed successfully - returning response")
        return response
        
    except Exception as e:
        return create_error_response(
            500,
            'Internal server error',
            event,
            {'details': str(e)}
        )