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
        validation_result = validate_nickname(nickname)
        if validation_result:
            return create_error_response(
                400, 
                validation_result['error'], 
                event,
                {'hints': validation_result['hints']}
            )
        
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
            nickname_normalized=nickname.lower(),  # Store normalized version for uniqueness
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
    Validate nickname format and rules with detailed error hints
    Returns dict with 'error' and 'hints' if invalid, None if valid
    """
    hints = []
    
    # Length validation (3-30 characters)
    if len(nickname) < 3:
        return {
            'error': 'Nickname is too short',
            'hints': ['Nickname must be between 3-30 characters long']
        }
    
    if len(nickname) > 30:
        return {
            'error': 'Nickname is too long', 
            'hints': ['Nickname must be between 3-30 characters long']
        }
    
    # Character validation - only lowercase letters, digits, single underscore
    if not re.match(r'^[a-z0-9_]+$', nickname):
        invalid_chars = set(nickname) - set('abcdefghijklmnopqrstuvwxyz0123456789_')
        if invalid_chars:
            return {
                'error': 'Nickname contains invalid characters',
                'hints': [
                    'Only lowercase letters (a-z), digits (0-9), and underscores (_) are allowed',
                    f'Invalid characters found: {", ".join(sorted(invalid_chars))}'
                ]
            }
    
    # Cannot start with underscore
    if nickname.startswith('_'):
        return {
            'error': 'Nickname cannot start with underscore',
            'hints': ['Nickname must start with a letter (a-z) or digit (0-9)']
        }
    
    # Cannot end with underscore
    if nickname.endswith('_'):
        return {
            'error': 'Nickname cannot end with underscore',
            'hints': ['Nickname must end with a letter (a-z) or digit (0-9)']
        }
    
    # No consecutive underscores
    if '__' in nickname:
        return {
            'error': 'Nickname contains consecutive underscores',
            'hints': ['Only single underscores are allowed (no consecutive underscores like "__")']
        }
    
    # Cannot start with digit (optional restriction to avoid confusion)
    if nickname[0].isdigit():
        return {
            'error': 'Nickname cannot start with a number',
            'hints': ['Nickname must start with a letter (a-z)']
        }
    
    # Reserved words check (case insensitive, comprehensive list) - check first before confusing chars
    reserved_words = [
        # System/Admin
        'admin', 'administrator', 'root', 'system', 'user', 'mod', 'moderator',
        
        # Technical
        'api', 'www', 'ftp', 'mail', 'email', 'smtp', 'pop', 'imap',
        'dns', 'ssl', 'tls', 'http', 'https', 'tcp', 'udp', 'ip',
        
        # Support/Contact
        'support', 'help', 'info', 'contact', 'service', 'team',
        
        # Navigation/Pages
        'about', 'profile', 'settings', 'account', 'dashboard', 'home',
        'search', 'browse', 'explore', 'discover',
        
        # Authentication
        'login', 'register', 'signup', 'signin', 'logout', 'signout',
        'password', 'forgot', 'reset', 'verify', 'confirm', 'activate',
        
        # Content/Actions
        'post', 'comment', 'reply', 'share', 'like', 'follow', 'unfollow',
        'create', 'edit', 'delete', 'update', 'save', 'cancel',
        
        # Testing/Development
        'test', 'demo', 'example', 'sample', 'debug', 'staging', 'dev',
        
        # Generic/Reserved
        'null', 'undefined', 'none', 'empty', 'blank', 'default',
        'anonymous', 'guest', 'public', 'private', 'temp', 'tmp',
        
        # Anecdotario-specific
        'anecdotario', 'anecdote', 'story', 'campaign', 'organization', 'org',
        'notification', 'comment', 'photo', 'image', 'upload'
    ]
    
    if nickname.lower() in reserved_words:
        return {
            'error': 'Nickname is reserved',
            'hints': [
                f'"{nickname}" is a reserved word and cannot be used',
                'Please choose a different nickname'
            ]
        }
    
    # Check for confusing lookalikes (basic homoglyph filtering) - after reserved words
    confusing_patterns = {
        r'[il1|]': 'Contains confusing characters that look similar (i, l, 1, |)',
        r'[o0]': 'Contains confusing characters that look similar (o, 0)',
        r'rn': 'Contains "rn" which can be confused with "m"',
        r'[vw]': 'Contains characters that can be visually confused (v, w)'
    }
    
    for pattern, message in confusing_patterns.items():
        if re.search(pattern, nickname):
            return {
                'error': 'Nickname contains potentially confusing characters',
                'hints': [message, 'Please choose characters that are clearly distinguishable']
            }
    
    return None  # Valid nickname