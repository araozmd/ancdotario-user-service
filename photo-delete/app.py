import json
import os
import sys
import boto3
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


def lambda_handler(event, context):
    """
    Lambda handler for photo deletion - handles DELETE /users/{userId}/photo
    Deletes all photo versions from S3 and clears user photo URLs
    """
    try:
        # API Gateway already validated JWT token, extract user ID
        user_id = event['requestContext']['authorizer']['claims']['sub']
        
        # Get user ID from path parameters
        path_params = event.get('pathParameters') or {}
        target_user_id = path_params.get('userId')
        
        if not target_user_id:
            return create_error_response(
                400,
                'User ID is required',
                event
            )
        
        # Security check: users can only delete their own photos
        if target_user_id != user_id:
            return create_error_response(
                403,
                'Unauthorized: You can only delete your own photos',
                event,
                {
                    'token_user_id': user_id,
                    'target_user_id': target_user_id
                }
            )
        
        # Get user from database
        try:
            user = User.get(target_user_id)
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
            return create_response(
                200,
                json.dumps({
                    'message': 'No photos to delete',
                    'user_id': target_user_id
                }),
                event,
                ['DELETE']
            )
        
        # Delete all photo versions from S3
        deleted_files = []
        deletion_errors = []
        
        if BUCKET_NAME:
            # List all objects with the user's prefix
            try:
                response = s3_client.list_objects_v2(
                    Bucket=BUCKET_NAME,
                    Prefix=f"users/{target_user_id}/"
                )
                
                if 'Contents' in response:
                    # Delete each photo
                    for obj in response['Contents']:
                        try:
                            s3_client.delete_object(
                                Bucket=BUCKET_NAME,
                                Key=obj['Key']
                            )
                            deleted_files.append(obj['Key'])
                        except ClientError as e:
                            deletion_errors.append({
                                'key': obj['Key'],
                                'error': str(e)
                            })
                    
                    # Handle pagination if there are many photos
                    while response.get('IsTruncated'):
                        continuation_token = response.get('NextContinuationToken')
                        response = s3_client.list_objects_v2(
                            Bucket=BUCKET_NAME,
                            Prefix=f"users/{target_user_id}/",
                            ContinuationToken=continuation_token
                        )
                        
                        if 'Contents' in response:
                            for obj in response['Contents']:
                                try:
                                    s3_client.delete_object(
                                        Bucket=BUCKET_NAME,
                                        Key=obj['Key']
                                    )
                                    deleted_files.append(obj['Key'])
                                except ClientError as e:
                                    deletion_errors.append({
                                        'key': obj['Key'],
                                        'error': str(e)
                                    })
                                    
            except ClientError as e:
                print(f"Error listing S3 objects: {str(e)}")
                # Continue to clear database even if S3 operation fails
        
        # Clear photo URLs from user record
        user.thumbnail_url = None
        user.standard_s3_key = None
        user.high_res_s3_key = None
        user.image_url = None
        user.save()
        
        # Return success response
        return create_response(
            200,
            json.dumps({
                'message': 'Photos deleted successfully',
                'user_id': target_user_id,
                'deleted_files': deleted_files,
                'deletion_errors': deletion_errors if deletion_errors else None,
                'deleted_at': event.get('requestContext', {}).get('requestTime')
            }),
            event,
            ['DELETE']
        )
        
    except Exception as e:
        return create_error_response(
            500,
            'Internal server error',
            event,
            {'details': str(e)}
        )