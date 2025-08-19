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


def create_response(status_code: int, body: str, event: dict, allowed_methods: list = None) -> dict:
    """Create a Lambda response - CORS headers must be added by Lambda"""
    # API Gateway CORS configuration only handles OPTIONS requests automatically
    # For actual requests (GET, POST, DELETE), Lambda must return CORS headers
    
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',  # For dev, using wildcard
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Methods': 'GET,POST,DELETE,OPTIONS',
            'Access-Control-Allow-Credentials': 'false'
        },
        'body': body
    }


def create_error_response(status_code: int, message: str, event: dict, 
                         details: dict = None, allowed_methods: list = None) -> dict:
    """Create an error response - CORS is handled by API Gateway"""
    error_body = {
        'error': message,
        'statusCode': status_code
    }
    
    if details:
        error_body['details'] = details
    
    return create_response(status_code, json.dumps(error_body), event, allowed_methods)