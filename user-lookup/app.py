import json
import os
import sys

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


def lambda_handler(event, context):
    """
    Lambda handler for user lookup by nickname
    Lightweight function optimized for read operations
    """
    
    # Handle preflight OPTIONS request
    if event['httpMethod'] == 'OPTIONS':
        return handle_options_request(event)
    
    # Only handle GET requests for user lookup
    if event['httpMethod'] == 'GET':
        return handle_user_lookup(event)
    
    return create_error_response(
        405,
        'Method not allowed. This endpoint only supports user lookup.',
        event,
        ['GET']
    )




def handle_user_lookup(event):
    """Handle GET request to retrieve user by nickname"""
    try:
        # Get authenticated user from API Gateway context
        claims, error_response = get_authenticated_user(event)
        if error_response:
            return error_response
        
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
        
        # Return user information
        return create_response(
            200,
            json.dumps({
                'user': user.to_dict(),
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