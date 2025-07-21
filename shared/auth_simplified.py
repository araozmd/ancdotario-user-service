"""
Simplified auth module for use with API Gateway JWT Authorizer.
When API Gateway handles JWT validation, the Lambda functions receive
the decoded token in the request context.
"""
import json
from typing import Dict, Tuple, Optional
from config import config


def get_authenticated_user(event: dict) -> Tuple[Optional[Dict], Optional[Dict]]:
    """
    Extract authenticated user information from API Gateway request context.
    
    When using API Gateway JWT Authorizer, the decoded token is available
    in event['requestContext']['authorizer']['claims']
    
    Args:
        event: Lambda event from API Gateway
        
    Returns:
        Tuple of (claims_dict, error_response)
        - claims_dict: Decoded JWT claims if authenticated
        - error_response: Error response dict if not authenticated
    """
    try:
        # Get claims from API Gateway authorizer context
        request_context = event.get('requestContext', {})
        authorizer = request_context.get('authorizer', {})
        claims = authorizer.get('claims', {})
        
        # Verify we have a user ID (sub claim)
        if not claims.get('sub'):
            return None, create_error_response(
                401,
                'Invalid authentication context',
                event
            )
        
        return claims, None
        
    except Exception as e:
        return None, create_error_response(
            401,
            'Failed to parse authentication context',
            event,
            {'details': str(e)}
        )


def handle_options_request(event: dict) -> dict:
    """
    Handle preflight OPTIONS request for CORS.
    API Gateway should handle this automatically with proper CORS configuration.
    """
    origin = get_allowed_origin(event)
    
    return {
        'statusCode': 200,
        'headers': {
            'Access-Control-Allow-Origin': origin,
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Methods': 'GET,POST,DELETE,OPTIONS',
            'Access-Control-Max-Age': '86400'
        },
        'body': ''
    }


def get_allowed_origin(event: dict) -> str:
    """Get the allowed origin for CORS based on request origin"""
    request_origin = event.get('headers', {}).get('origin', '')
    
    # Get allowed origins from config
    allowed_origins_str = config.get_parameter('allowed-origins', 
                                               default='https://localhost:3000,http://localhost:3000')
    allowed_origins = [origin.strip() for origin in allowed_origins_str.split(',')]
    
    # Return the request origin if it's in the allowed list, otherwise return the first allowed origin
    if request_origin in allowed_origins:
        return request_origin
    
    return allowed_origins[0] if allowed_origins else '*'


def create_response(status_code: int, body: str, event: dict, allowed_methods: list = None) -> dict:
    """Create a Lambda response with CORS headers"""
    origin = get_allowed_origin(event)
    
    response = {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': origin
        },
        'body': body
    }
    
    if allowed_methods:
        response['headers']['Access-Control-Allow-Methods'] = ','.join(allowed_methods)
    
    return response


def create_error_response(status_code: int, message: str, event: dict, 
                         details: dict = None, allowed_methods: list = None) -> dict:
    """Create an error response with CORS headers"""
    error_body = {
        'error': message,
        'statusCode': status_code
    }
    
    if details:
        error_body['details'] = details
    
    return create_response(status_code, json.dumps(error_body), event, allowed_methods)