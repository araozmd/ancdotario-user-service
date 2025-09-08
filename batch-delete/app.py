import json
import os
import sys
import boto3
from botocore.exceptions import ClientError
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

# Add shared directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))
from models.user import User
from config import config
# Use simplified auth when API Gateway handles JWT validation
try:
    from auth_simplified import get_authenticated_user, create_response, create_error_response
except ImportError:
    # Fallback to full auth module if simplified not available
    from auth import get_authenticated_user, create_response, create_error_response

# AWS Services
s3_client = boto3.client('s3')

# Environment configuration
BUCKET_NAME = config.get_ssm_parameter('photo-bucket-name', os.environ.get('PHOTO_BUCKET_NAME'))

# Configuration for batch processing
MAX_BATCH_SIZE = 50  # Maximum users to process in a single request
MAX_CONCURRENT_DELETIONS = 5  # Maximum concurrent user deletions
INDIVIDUAL_DELETE_TIMEOUT = 30  # Timeout for individual user deletion in seconds


def lambda_handler(event, context):
    """
    Lambda handler for batch user deletion
    Handles POST requests to delete multiple user accounts and associated data
    """
    return handle_batch_deletion(event, context)


def handle_batch_deletion(event, context):
    """Handle POST request to delete multiple user accounts"""
    try:
        # Get authentication context from API Gateway
        claims, auth_error = get_authenticated_user(event)
        if auth_error:
            return auth_error
        
        requesting_user_id = claims['sub']
        print(f"Batch deletion request from user: {requesting_user_id}")
        
        # Parse request body
        if not event.get('body'):
            return create_error_response(
                400,
                'Request body is required',
                event,
                {'required_format': {'user_ids': ['user1', 'user2', 'user3']}}
            )
        
        try:
            body = json.loads(event['body'])
        except json.JSONDecodeError as e:
            return create_error_response(
                400,
                'Invalid JSON in request body',
                event,
                {'details': str(e)}
            )
        
        # Validate request format
        user_ids = body.get('user_ids', [])
        if not isinstance(user_ids, list):
            return create_error_response(
                400,
                'user_ids must be an array',
                event,
                {'received_type': type(user_ids).__name__}
            )
        
        if not user_ids:
            return create_error_response(
                400,
                'user_ids array cannot be empty',
                event,
                {'required_format': {'user_ids': ['user1', 'user2', 'user3']}}
            )
        
        if len(user_ids) > MAX_BATCH_SIZE:
            return create_error_response(
                400,
                f'Batch size exceeds maximum limit of {MAX_BATCH_SIZE}',
                event,
                {
                    'requested_count': len(user_ids),
                    'max_allowed': MAX_BATCH_SIZE,
                    'suggestion': 'Split into multiple smaller batches'
                }
            )
        
        # Remove duplicates while preserving order
        unique_user_ids = list(dict.fromkeys(user_ids))
        if len(unique_user_ids) != len(user_ids):
            print(f"Removed {len(user_ids) - len(unique_user_ids)} duplicate user IDs")
        
        # Check if test mode is enabled (bypasses ownership check)
        test_mode = body.get('test_mode', False)
        confirmation = body.get('confirm', False)
        deletion_reason = body.get('reason', 'Batch deletion requested')
        
        # Require confirmation for safety
        if not confirmation:
            return create_error_response(
                400,
                'Batch deletion requires confirmation',
                event,
                {
                    'usage': 'Include "confirm": true in request body',
                    'warning': 'This action cannot be undone',
                    'user_count': len(unique_user_ids),
                    'test_mode': test_mode
                }
            )
        
        print(f"Starting batch deletion: {len(unique_user_ids)} users, test_mode={test_mode}")
        
        # Validate user permissions and existence
        validation_results = validate_batch_users(
            unique_user_ids, 
            requesting_user_id, 
            test_mode
        )
        
        # If all users failed validation, return error
        if not validation_results['valid_users']:
            return create_error_response(
                400,
                'No valid users to delete',
                event,
                {
                    'validation_errors': validation_results['errors'],
                    'total_requested': len(unique_user_ids)
                }
            )
        
        # Process deletions concurrently for better performance
        deletion_results = process_batch_deletions(
            validation_results['valid_users'],
            deletion_reason,
            context
        )
        
        # Combine validation errors with deletion results
        all_errors = validation_results['errors'] + deletion_results['errors']
        
        # Prepare comprehensive response
        response_data = {
            'message': f'Batch deletion completed: {deletion_results["successful_count"]} successful, {len(all_errors)} failed',
            'summary': {
                'requested_count': len(unique_user_ids),
                'successful_count': deletion_results['successful_count'],
                'failed_count': len(all_errors),
                'total_photos_deleted': deletion_results['total_photos_deleted'],
                'processing_time_seconds': deletion_results['processing_time']
            },
            'successful_deletions': deletion_results['successful_deletions'],
            'errors': all_errors,
            'metadata': {
                'deletion_reason': deletion_reason,
                'test_mode': test_mode,
                'requesting_user': requesting_user_id,
                'deleted_at': event.get('requestContext', {}).get('requestTime'),
                'remaining_context_time_ms': context.get_remaining_time_in_millis() if context else None
            },
            'warnings': [
                'This action cannot be undone',
                'All associated photos have been permanently deleted from S3'
            ] if deletion_results['successful_count'] > 0 else []
        }
        
        # Determine response status code
        if deletion_results['successful_count'] == len(unique_user_ids):
            status_code = 200  # All successful
        elif deletion_results['successful_count'] > 0:
            status_code = 207  # Partial success (Multi-Status)
        else:
            status_code = 400  # All failed
        
        return create_response(
            status_code,
            json.dumps(response_data),
            event,
            ['POST']
        )
        
    except Exception as e:
        print(f"Unexpected error in batch deletion: {str(e)}")
        return create_error_response(
            500,
            'Internal server error during batch deletion',
            event,
            {
                'details': str(e),
                'remaining_context_time_ms': context.get_remaining_time_in_millis() if context else None
            }
        )


def validate_batch_users(user_ids: List[str], requesting_user_id: str, test_mode: bool) -> Dict[str, Any]:
    """
    Validate that users exist and can be deleted by the requesting user
    
    Args:
        user_ids: List of user IDs to validate
        requesting_user_id: ID of user making the request
        test_mode: If True, bypasses ownership checks
    
    Returns:
        Dict with valid_users list and errors list
    """
    valid_users = []
    errors = []
    
    print(f"Validating {len(user_ids)} users for deletion")
    
    for user_id in user_ids:
        try:
            # Check if user exists
            try:
                user = User.get(user_id)
            except User.DoesNotExist:
                errors.append({
                    'user_id': user_id,
                    'error': 'User not found',
                    'error_code': 'USER_NOT_FOUND'
                })
                continue
            
            # Security check: users can only delete their own account unless in test mode
            if not test_mode and user_id != requesting_user_id:
                errors.append({
                    'user_id': user_id,
                    'error': 'Unauthorized: You can only delete your own account',
                    'error_code': 'UNAUTHORIZED_DELETION'
                })
                continue
            
            # User passed all validations
            valid_users.append({
                'user_id': user_id,
                'user_data': user.to_dict(),
                'has_photos': bool(user.thumbnail_url or user.standard_s3_key or user.high_res_s3_key or user.image_url)
            })
            
        except Exception as e:
            errors.append({
                'user_id': user_id,
                'error': f'Validation failed: {str(e)}',
                'error_code': 'VALIDATION_ERROR'
            })
    
    print(f"Validation complete: {len(valid_users)} valid, {len(errors)} errors")
    
    return {
        'valid_users': valid_users,
        'errors': errors
    }


def process_batch_deletions(valid_users: List[Dict], deletion_reason: str, context) -> Dict[str, Any]:
    """
    Process multiple user deletions concurrently
    
    Args:
        valid_users: List of validated user data
        deletion_reason: Reason for deletion
        context: Lambda context for timeout monitoring
    
    Returns:
        Dict with deletion results
    """
    start_time = time.time()
    successful_deletions = []
    errors = []
    total_photos_deleted = 0
    
    print(f"Starting concurrent deletion of {len(valid_users)} users")
    
    # Use ThreadPoolExecutor for concurrent deletions
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_DELETIONS) as executor:
        # Submit all deletion tasks
        future_to_user = {
            executor.submit(
                delete_single_user_with_timeout,
                user_data,
                deletion_reason,
                context
            ): user_data for user_data in valid_users
        }
        
        # Collect results as they complete
        for future in as_completed(future_to_user):
            user_data = future_to_user[future]
            user_id = user_data['user_id']
            
            try:
                result = future.result(timeout=INDIVIDUAL_DELETE_TIMEOUT)
                if result['success']:
                    successful_deletions.append({
                        'user_id': user_id,
                        'deleted_user': result['user_data'],
                        'photos_deleted': result['photos_deleted'],
                        'cleanup_info': result.get('cleanup_info', {})
                    })
                    total_photos_deleted += result['photos_deleted']
                    print(f"Successfully deleted user {user_id}")
                else:
                    errors.append({
                        'user_id': user_id,
                        'error': result['error'],
                        'error_code': result.get('error_code', 'DELETION_FAILED')
                    })
                    print(f"Failed to delete user {user_id}: {result['error']}")
                    
            except Exception as e:
                errors.append({
                    'user_id': user_id,
                    'error': f'Deletion task failed: {str(e)}',
                    'error_code': 'TASK_EXECUTION_ERROR'
                })
                print(f"Task execution error for user {user_id}: {str(e)}")
    
    processing_time = round(time.time() - start_time, 2)
    print(f"Batch deletion completed in {processing_time}s: {len(successful_deletions)} successful, {len(errors)} errors")
    
    return {
        'successful_deletions': successful_deletions,
        'errors': errors,
        'successful_count': len(successful_deletions),
        'total_photos_deleted': total_photos_deleted,
        'processing_time': processing_time
    }


def delete_single_user_with_timeout(user_data: Dict, deletion_reason: str, context) -> Dict[str, Any]:
    """
    Delete a single user with timeout protection
    
    Args:
        user_data: User data dict from validation
        deletion_reason: Reason for deletion
        context: Lambda context for timeout monitoring
    
    Returns:
        Dict with success flag and result data
    """
    user_id = user_data['user_id']
    
    try:
        # Check remaining Lambda execution time
        if context and context.get_remaining_time_in_millis() < 5000:  # 5 seconds buffer
            return {
                'success': False,
                'error': 'Insufficient time remaining for safe deletion',
                'error_code': 'TIMEOUT_RISK'
            }
        
        # Delete user photos from S3 if bucket is configured and user has photos
        photos_deleted = []
        cleanup_info = {}
        
        if BUCKET_NAME and user_data['has_photos']:
            try:
                print(f"Deleting photos for user {user_id}")
                photos_deleted = delete_user_photos(user_id)
                cleanup_info = {
                    'photos_deleted_count': len(photos_deleted),
                    'deleted_files': photos_deleted[:10] if len(photos_deleted) > 10 else photos_deleted,  # Limit response size
                    'truncated': len(photos_deleted) > 10
                }
                print(f"Deleted {len(photos_deleted)} photos for user {user_id}")
            except Exception as e:
                # Log warning but don't fail the user deletion
                error_msg = f"Failed to delete photos: {str(e)}"
                print(f"Warning during photo cleanup for user {user_id}: {error_msg}")
                cleanup_info = {
                    'photos_deleted_count': 0,
                    'cleanup_error': error_msg
                }
        
        # Get user instance and delete from database
        user = User.get(user_id)
        user_dict = user.to_dict()
        user.delete()
        
        print(f"Successfully deleted user {user_id} from database")
        
        return {
            'success': True,
            'user_data': user_dict,
            'photos_deleted': len(photos_deleted),
            'cleanup_info': cleanup_info
        }
        
    except User.DoesNotExist:
        return {
            'success': False,
            'error': 'User not found during deletion',
            'error_code': 'USER_NOT_FOUND'
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'error_code': 'DELETION_ERROR'
        }


def delete_user_photos(user_id: str) -> List[str]:
    """
    Delete all photos for a user from S3 using optimized batch operations
    Reuses the same logic from user-delete/app.py
    
    Args:
        user_id: User ID to delete photos for
    
    Returns:
        List of deleted S3 object keys
    """
    try:
        user_prefix = f"users/{user_id}/"
        print(f"Starting S3 cleanup for user: {user_prefix}")
        
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
                    all_objects.append({'Key': obj['Key']})
        
        if not all_objects:
            print(f"No photos found for user {user_id}")
            return []
        
        print(f"Found {len(all_objects)} photos to delete for user {user_id}")
        
        deleted_files = []
        
        # Batch delete objects (max 1000 per batch as per AWS limits)
        batch_size = 1000
        for i in range(0, len(all_objects), batch_size):
            batch = all_objects[i:i + batch_size]
            
            try:
                response = s3_client.delete_objects(
                    Bucket=BUCKET_NAME,
                    Delete={'Objects': batch}
                )
                
                # Track successful deletions
                for deleted in response.get('Deleted', []):
                    deleted_files.append(deleted['Key'])
                    
                # Log errors but continue processing
                for error in response.get('Errors', []):
                    print(f"S3 delete error for {error['Key']}: {error['Message']}")
                    
            except ClientError as e:
                print(f"Batch delete failed for user {user_id}: {str(e)}")
                
                # Fallback to individual deletes for this batch
                for obj in batch:
                    try:
                        s3_client.delete_object(Bucket=BUCKET_NAME, Key=obj['Key'])
                        deleted_files.append(obj['Key'])
                    except ClientError as del_e:
                        print(f"Individual delete failed for {obj['Key']}: {str(del_e)}")
        
        print(f"S3 cleanup complete for user {user_id}: {len(deleted_files)} files deleted")
        return deleted_files
        
    except Exception as e:
        print(f"Unexpected error during photo cleanup for user {user_id}: {str(e)}")
        return []