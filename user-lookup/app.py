import json
import os
import sys
import boto3

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

# Initialize S3 client for presigned URL generation
s3_client = boto3.client('s3')


def lambda_handler(event, context):
    """Lambda handler for user lookup - handles GET /users/by-nickname/{nickname}"""
    try:
        # API Gateway already validated JWT token
        # Get nickname from path parameters
        path_params = event.get('pathParameters') or {}
        nickname = path_params.get('nickname')
        
        if not nickname:
            return create_error_response(
                400,
                'Nickname path parameter is required',
                event,
                {'usage': 'GET /users/{nickname} with Authorization header'}
            )
        
        # Validate nickname format (basic validation)
        if len(nickname) < 3 or len(nickname) > 20:
            return create_error_response(
                400,
                'Nickname must be between 3 and 20 characters',
                event
            )
        
        # Look up user by nickname
        user = User.get_by_nickname(nickname)
        if not user:
            return create_error_response(
                404,
                'User not found',
                event,
                {'nickname': nickname}
            )
        
        # Check if user is authenticated (JWT token is already validated by API Gateway)
        is_authenticated = event.get('requestContext', {}).get('authorizer', {}).get('claims') is not None
        
        # Return user information with presigned URLs if authenticated
        return create_response(
            200,
            json.dumps({
                'user': user.to_dict(
                    include_presigned_urls=is_authenticated,
                    s3_client=s3_client if is_authenticated else None
                ),
                'retrieved_at': event.get('requestContext', {}).get('requestTime')
            }),
            event,
            ['GET']
        )
        
    except Exception as e:
        return create_error_response(
            500,
            'Internal server error',
            event,
            {'details': str(e)}
        )