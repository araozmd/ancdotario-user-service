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
    Lambda handler for user deletion
    Handles DELETE requests to remove user accounts and associated data
    """
    return handle_user_deletion(event)


def handle_user_deletion(event):
    """Handle DELETE request to remove a user account"""
    try:
        # API Gateway already validated JWT token, extract user ID
        user_id = event['requestContext']['authorizer']['claims']['sub']
        
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
        photo_cleanup_errors = []
        
        # Check if user has any images (thumbnail, standard, or high-res)
        has_images = user.thumbnail_url or user.standard_s3_key or user.high_res_s3_key or user.image_url
        
        if BUCKET_NAME and has_images:
            try:
                print(f"User has photos, starting S3 cleanup for deletion")
                photos_deleted = delete_user_photos(target_user_id)
                print(f"S3 cleanup completed: {len(photos_deleted)} files deleted")
            except Exception as e:
                # Log error but don't fail the user deletion
                error_msg = f"Failed to delete user photos: {str(e)}"
                print(f"Warning: {error_msg}")
                photo_cleanup_errors.append(error_msg)
        elif has_images:
            warning_msg = "User has photos but S3 bucket not configured - photos not deleted"
            print(f"Warning: {warning_msg}")
            photo_cleanup_errors.append(warning_msg)
        else:
            print(f"User has no photos to delete")
        
        # Delete user from database
        print(f"Deleting user record from database")
        user.delete()
        print(f"User account deletion completed successfully")
        
        # Prepare response data
        response_data = {
            'message': 'User account deleted successfully',
            'deleted_user': user_data,
            'cleanup': {
                'photos_deleted': len(photos_deleted),
                'deleted_files': photos_deleted if photos_deleted else None,
                'cleanup_errors': photo_cleanup_errors if photo_cleanup_errors else None
            },
            'deletion_reason': deletion_reason or 'User requested deletion',
            'deleted_at': event.get('requestContext', {}).get('requestTime'),
            'warning': 'This action cannot be undone'
        }
        
        # Include legacy field for backward compatibility
        response_data['photos_deleted'] = photos_deleted
        
        # Return success response
        return create_response(
            200,
            json.dumps(response_data),
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
    Delete all photos for a user from S3 using optimized batch operations
    Returns comprehensive cleanup results
    """
    cleanup_result = {
        'deleted_files': [],
        'deletion_errors': [],
        'files_scanned': 0,
        'batches_processed': 0
    }
    
    try:
        user_prefix = f"users/{user_id}/"
        print(f"Starting comprehensive S3 cleanup for user deletion: {user_prefix}")
        
        # Use paginator to handle large numbers of photos efficiently
        paginator = s3_client.get_paginator('list_objects_v2')
        page_iterator = paginator.paginate(
            Bucket=BUCKET_NAME,
            Prefix=user_prefix
        )
        
        # Process all pages and collect objects for batch deletion
        all_objects = []
        for page in page_iterator:
            if 'Contents' in page:
                for obj in page['Contents']:
                    cleanup_result['files_scanned'] += 1
                    all_objects.append({'Key': obj['Key']})
        
        if not all_objects:
            print(f"No photos found for user {user_id}")
            return cleanup_result
        
        print(f"Found {len(all_objects)} photos to delete for user {user_id}")
        
        # Batch delete objects (max 1000 per batch as per AWS limits)
        batch_size = 1000
        for i in range(0, len(all_objects), batch_size):
            batch = all_objects[i:i + batch_size]
            cleanup_result['batches_processed'] += 1
            
            try:
                print(f"Processing batch {cleanup_result['batches_processed']}: {len(batch)} files")
                
                response = s3_client.delete_objects(
                    Bucket=BUCKET_NAME,
                    Delete={'Objects': batch}
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
                    print(f"Batch delete error for {error['Key']}: {error['Message']}")
                    
            except ClientError as e:
                print(f"Batch delete failed for batch {cleanup_result['batches_processed']}: {str(e)}")
                
                # Fallback to individual deletes for this batch
                print(f"Falling back to individual deletes for {len(batch)} files")
                for obj in batch:
                    try:
                        s3_client.delete_object(Bucket=BUCKET_NAME, Key=obj['Key'])
                        cleanup_result['deleted_files'].append(obj['Key'])
                    except ClientError as del_e:
                        cleanup_result['deletion_errors'].append({
                            'key': obj['Key'],
                            'error': str(del_e),
                            'error_code': del_e.response.get('Error', {}).get('Code', 'Unknown')
                        })
                        print(f"Individual delete failed for {obj['Key']}: {str(del_e)}")
        
        print(f"User deletion cleanup complete: {len(cleanup_result['deleted_files'])} files deleted, "
              f"{len(cleanup_result['deletion_errors'])} errors, "
              f"{cleanup_result['files_scanned']} files scanned, "
              f"{cleanup_result['batches_processed']} batches processed")
        
    except ClientError as e:
        print(f"Failed to scan S3 for user photos: {str(e)}")
        cleanup_result['deletion_errors'].append({
            'operation': 'scan',
            'error': str(e),
            'error_code': e.response.get('Error', {}).get('Code', 'Unknown')
        })
    except Exception as e:
        print(f"Unexpected error during user photo cleanup: {str(e)}")
        cleanup_result['deletion_errors'].append({
            'operation': 'cleanup',
            'error': str(e),
            'error_code': 'UnexpectedError'
        })
    
    # Return list of deleted files for backward compatibility
    return cleanup_result['deleted_files']