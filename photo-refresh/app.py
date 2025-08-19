import json
import os
import sys
import boto3
from datetime import datetime, timedelta
from botocore.exceptions import ClientError

# Add shared directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))
from models.user import User
from config import config
# Use simplified auth when API Gateway handles JWT validation
try:
    from auth_simplified import create_response, create_error_response
except ImportError:
    # Fallback to full auth module if simplified not available
    from auth import create_response, create_error_response

# AWS Services
s3_client = boto3.client('s3')

# Environment configuration
BUCKET_NAME = config.get_ssm_parameter('photo-bucket-name', os.environ.get('PHOTO_BUCKET_NAME'))

# Presigned URL settings
PRESIGNED_URL_EXPIRY = 604800  # 7 days in seconds


def lambda_handler(event, context):
    """
    Lambda handler for photo URL refresh - handles GET /users/{userId}/photo/refresh
    Generates fresh presigned URLs for existing photos without re-uploading
    """
    try:
        # API Gateway already validated JWT token, extract user ID
        token_user_id = event['requestContext']['authorizer']['claims']['sub']
        
        # Get user ID from path parameters
        path_params = event.get('pathParameters') or {}
        target_user_id = path_params.get('userId')
        
        if not target_user_id:
            return create_error_response(
                400,
                'User ID is required',
                event
            )
        
        # Security check: users can only refresh their own photo URLs
        if target_user_id != token_user_id:
            return create_error_response(
                403,
                'Unauthorized: You can only refresh your own photo URLs',
                event,
                {
                    'token_user_id': token_user_id,
                    'target_user_id': target_user_id
                }
            )
        
        print(f"Refreshing photo URLs for user: {target_user_id}")
        
        # Get user from database
        try:
            user = User.get(target_user_id)
            print(f"Found user: {user.nickname}")
        except User.DoesNotExist:
            return create_error_response(
                404,
                'User not found',
                event,
                {'user_id': target_user_id}
            )
        
        # Check if user has any photos
        has_photos = (
            user.thumbnail_url or 
            user.standard_s3_key or 
            user.high_res_s3_key or 
            user.image_url
        )
        
        if not has_photos:
            return create_error_response(
                404,
                'No photos found for this user',
                event,
                {'user_id': target_user_id}
            )
        
        print(f"User has photos - generating fresh URLs")
        
        # Generate fresh URLs
        refreshed_urls = {}
        errors = []
        
        # Thumbnail URL (public, never expires)
        if user.thumbnail_url:
            refreshed_urls['thumbnail'] = user.thumbnail_url
            print(f"Thumbnail URL (public): {user.thumbnail_url}")
        
        # Standard image (presigned URL)
        if user.standard_s3_key and BUCKET_NAME:
            try:
                # First verify the file exists
                s3_client.head_object(Bucket=BUCKET_NAME, Key=user.standard_s3_key)
                
                presigned_url = s3_client.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': BUCKET_NAME, 'Key': user.standard_s3_key},
                    ExpiresIn=PRESIGNED_URL_EXPIRY
                )
                refreshed_urls['standard'] = presigned_url
                print(f"Generated fresh standard presigned URL ({len(presigned_url)} chars)")
                
            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code', 'Unknown')
                if error_code == 'NoSuchKey':
                    errors.append({
                        'version': 'standard',
                        'error': 'File not found in S3',
                        'key': user.standard_s3_key
                    })
                    print(f"Standard image file not found: {user.standard_s3_key}")
                else:
                    errors.append({
                        'version': 'standard',
                        'error': str(e),
                        'key': user.standard_s3_key
                    })
                    print(f"Error generating standard URL: {str(e)}")
        
        # High-res image (presigned URL)
        if user.high_res_s3_key and BUCKET_NAME:
            try:
                # First verify the file exists
                s3_client.head_object(Bucket=BUCKET_NAME, Key=user.high_res_s3_key)
                
                presigned_url = s3_client.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': BUCKET_NAME, 'Key': user.high_res_s3_key},
                    ExpiresIn=PRESIGNED_URL_EXPIRY
                )
                refreshed_urls['high_res'] = presigned_url
                print(f"Generated fresh high_res presigned URL ({len(presigned_url)} chars)")
                
            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code', 'Unknown')
                if error_code == 'NoSuchKey':
                    errors.append({
                        'version': 'high_res',
                        'error': 'File not found in S3',
                        'key': user.high_res_s3_key
                    })
                    print(f"High-res image file not found: {user.high_res_s3_key}")
                else:
                    errors.append({
                        'version': 'high_res',
                        'error': str(e),
                        'key': user.high_res_s3_key
                    })
                    print(f"Error generating high_res URL: {str(e)}")
        
        # Check if we generated any URLs
        if not refreshed_urls:
            return create_error_response(
                404,
                'No valid photos found to refresh',
                event,
                {
                    'user_id': target_user_id,
                    'errors': errors
                }
            )
        
        # Calculate expiry time for response
        expires_at = datetime.utcnow() + timedelta(seconds=PRESIGNED_URL_EXPIRY)
        
        print(f"Successfully refreshed {len(refreshed_urls)} photo URLs")
        
        # Return success response with refreshed URLs
        response_data = {
            'message': 'Photo URLs refreshed successfully',
            'images': refreshed_urls,
            'expires_at': expires_at.isoformat() + 'Z',
            'expires_in_seconds': PRESIGNED_URL_EXPIRY,
            'refreshed_at': datetime.utcnow().isoformat() + 'Z'
        }
        
        # Include errors if any occurred (partial success)
        if errors:
            response_data['errors'] = errors
            response_data['message'] = f'Photo URLs partially refreshed ({len(refreshed_urls)} successful, {len(errors)} errors)'
        
        return create_response(
            200,
            json.dumps(response_data),
            event,
            ['GET']
        )
        
    except Exception as e:
        print(f"Unexpected error during URL refresh: {str(e)}")
        return create_error_response(
            500,
            'Internal server error',
            event,
            {'details': str(e)}
        )