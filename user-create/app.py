import json
import os
import sys
import re

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


def lambda_handler(event, context):
    """Lambda handler for user creation - handles POST /users"""
    try:
        # API Gateway already validated JWT token, extract user ID
        user_id = event['requestContext']['authorizer']['claims']['sub']
        
        # Check if user already exists
        try:
            existing_user = User.get(user_id)
            return create_error_response(
                409,
                'User already exists',
                event,
                {'user': existing_user.to_dict()}
            )
        except User.DoesNotExist:
            # User doesn't exist, continue with creation
            pass
        
        # Parse request body
        if not event.get('body'):
            return create_error_response(
                400,
                'Request body is required',
                event,
                {'usage': 'POST /users with {"nickname": "your_nickname"}'}
            )
        
        try:
            body = json.loads(event['body'])
        except json.JSONDecodeError:
            return create_error_response(
                400,
                'Invalid JSON in request body',
                event
            )
        
        # Extract and validate nickname
        nickname = body.get('nickname', '').strip()
        if not nickname:
            return create_error_response(
                400,
                'Nickname is required',
                event,
                {'usage': 'POST /users with {"nickname": "your_nickname"}'}
            )
        
        # Validate nickname format
        validation_error = validate_nickname(nickname)
        if validation_error:
            return create_error_response(400, validation_error, event)
        
        # Check if nickname is already taken
        existing_user_with_nickname = User.get_by_nickname(nickname)
        if existing_user_with_nickname:
            return create_error_response(
                409,
                'Nickname already taken',
                event,
                {'nickname': nickname}
            )
        
        # Extract optional email from JWT token claims
        email = event['requestContext']['authorizer']['claims'].get('email')
        
        # Create new user
        user = User(
            cognito_id=user_id,
            nickname=nickname,
            image_url=None  # No image initially
        )
        user.save()
        
        # Return success response
        return create_response(
            201,
            json.dumps({
                'message': 'User created successfully',
                'user': user.to_dict(),
                'created_at': event.get('requestContext', {}).get('requestTime')
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


def validate_nickname(nickname):
    """
    Validate nickname format and rules
    Returns error message if invalid, None if valid
    """
    # Length validation
    if len(nickname) < 3:
        return 'Nickname must be at least 3 characters long'
    
    if len(nickname) > 20:
        return 'Nickname must be no more than 20 characters long'
    
    # Character validation - allow alphanumeric, underscore, hyphen
    if not re.match(r'^[a-zA-Z0-9_-]+$', nickname):
        return 'Nickname can only contain letters, numbers, underscores, and hyphens'
    
    # Must start with letter or number
    if not re.match(r'^[a-zA-Z0-9]', nickname):
        return 'Nickname must start with a letter or number'
    
    # Must end with letter or number
    if not re.match(r'.*[a-zA-Z0-9]$', nickname):
        return 'Nickname must end with a letter or number'
    
    # No consecutive special characters
    if re.search(r'[_-]{2,}', nickname):
        return 'Nickname cannot contain consecutive underscores or hyphens'
    
    # Reserved words check (case insensitive)
    reserved_words = [
        'admin', 'administrator', 'root', 'system', 'user', 'api', 'www',
        'ftp', 'mail', 'email', 'support', 'help', 'info', 'contact',
        'about', 'profile', 'settings', 'account', 'login', 'register',
        'signup', 'signin', 'logout', 'password', 'forgot', 'reset',
        'test', 'demo', 'example', 'sample', 'null', 'undefined',
        'anonymous', 'guest', 'public', 'private'
    ]
    
    if nickname.lower() in reserved_words:
        return f'Nickname "{nickname}" is reserved and cannot be used'
    
    return None  # Valid nickname