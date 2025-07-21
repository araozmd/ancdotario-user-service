import json
import os
import sys
import boto3
from botocore.exceptions import ClientError

# Add shared directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))
from models.user import User
from config import config
from auth import validate_request_auth, handle_options_request, create_response, create_error_response

# AWS Services
s3_client = boto3.client('s3')

# Environment configuration
BUCKET_NAME = config.get_ssm_parameter('photo-bucket-name', os.environ.get('PHOTO_BUCKET_NAME'))


def lambda_handler(event, context):
    """
    Lambda handler for user deletion
    Handles DELETE requests to remove user accounts and associated data
    """
    
    # Handle preflight OPTIONS request
    if event['httpMethod'] == 'OPTIONS':
        return handle_options_request(event)
    
    # Only handle DELETE requests for user deletion
    if event['httpMethod'] == 'DELETE':
        return handle_user_deletion(event)
    
    return create_error_response(
        405,
        'Method not allowed. This endpoint only supports user deletion.',
        event,
        ['DELETE']
    )


def handle_user_deletion(event):
    """Handle DELETE request to remove a user account"""
    try:
        # Validate JWT token
        decoded_token, error_response = validate_request_auth(event)
        if error_response:
            return error_response
        
        # Extract user ID from JWT token
        user_id = decoded_token.get('sub')
        if not user_id:
            return create_error_response(
                400,
                'Invalid token: missing user ID',
                event
            )
        
        # Get user ID from path parameters (if provided)
        path_params = event.get('pathParameters') or {}
        target_user_id = path_params.get('userId')
        
        # If no userId in path, use token user_id (self-deletion)
        if not target_user_id:
            target_user_id = user_id
        
        # Security check: users can only delete their own account
        # (unless we implement admin functionality later)
        if target_user_id != user_id:
            return create_error_response(
                403,
                'Unauthorized: You can only delete your own account',
                event,
                {
                    'token_user_id': user_id,
                    'target_user_id': target_user_id
                }
            )
        
        # Check if user exists
        try:
            user = User.get(target_user_id)
        except User.DoesNotExist:
            return create_error_response(
                404,
                'User not found',
                event,
                {'user_id': target_user_id}
            )
        
        # Store user data for response before deletion
        user_data = user.to_dict()
        
        # Check for confirmation parameter (safety measure)
        query_params = event.get('queryStringParameters') or {}
        confirmation = query_params.get('confirm', '').lower()
        
        if confirmation != 'true':
            return create_error_response(
                400,
                'Account deletion requires confirmation',
                event,
                {
                    'usage': 'DELETE /users/{userId}?confirm=true',
                    'warning': 'This action cannot be undone',
                    'user': user_data
                }
            )
        
        # Optional: Parse request body for additional confirmation
        deletion_reason = None
        if event.get('body'):
            try:
                body = json.loads(event['body'])
                deletion_reason = body.get('reason', 'User requested deletion')
            except json.JSONDecodeError:
                # Body is optional, continue without it
                pass
        
        # Delete user photos from S3 (if bucket is configured)
        photos_deleted = []
        if BUCKET_NAME and user.image_url:
            try:
                photos_deleted = delete_user_photos(target_user_id)
            except Exception as e:
                # Log error but don't fail the user deletion
                print(f"Warning: Failed to delete user photos: {str(e)}")
        
        # Delete user from database
        user.delete()
        
        # Return success response
        return create_response(
            200,
            json.dumps({
                'message': 'User account deleted successfully',
                'deleted_user': user_data,
                'photos_deleted': photos_deleted,
                'deletion_reason': deletion_reason or 'User requested deletion',
                'deleted_at': event.get('requestContext', {}).get('requestTime'),
                'warning': 'This action cannot be undone'
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


def delete_user_photos(user_id):
    """
    Delete all photos for a user from S3
    Returns list of deleted photo keys
    """
    deleted_photos = []
    
    try:
        # List all objects with the user's prefix
        response = s3_client.list_objects_v2(
            Bucket=BUCKET_NAME,
            Prefix=f"{user_id}/"
        )
        
        if 'Contents' not in response:
            return deleted_photos  # No photos found
        
        # Delete each photo
        for obj in response['Contents']:
            try:
                s3_client.delete_object(
                    Bucket=BUCKET_NAME,
                    Key=obj['Key']
                )
                deleted_photos.append(obj['Key'])
            except ClientError as e:
                print(f"Failed to delete photo {obj['Key']}: {str(e)}")
                # Continue deleting other photos
        
        # If there are many photos, handle pagination
        while response.get('IsTruncated'):
            continuation_token = response.get('NextContinuationToken')
            response = s3_client.list_objects_v2(
                Bucket=BUCKET_NAME,
                Prefix=f"{user_id}/",
                ContinuationToken=continuation_token
            )
            
            if 'Contents' in response:
                for obj in response['Contents']:
                    try:
                        s3_client.delete_object(
                            Bucket=BUCKET_NAME,
                            Key=obj['Key']
                        )
                        deleted_photos.append(obj['Key'])
                    except ClientError as e:
                        print(f"Failed to delete photo {obj['Key']}: {str(e)}")
        
    except ClientError as e:
        print(f"Failed to list user photos: {str(e)}")
        raise
    
    return deleted_photos