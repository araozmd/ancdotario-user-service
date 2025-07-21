import json
import logging
from typing import Dict, Any, Optional

# Import User model
from models.user import User

# Import utilities
from utils.validation import (
    CreateUserRequest, 
    UpdateUserRequest, 
    validate_user_id,
    sanitize_query_params,
    validate_request_size,
    validate_content_type
)
from utils.security import (
    get_security_headers,
    validate_api_key,
    rate_limit_check,
    audit_log,
    mask_sensitive_data,
    validate_cors_origin
)

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def create_error_response(status_code: int, error_message: str, details: Optional[str] = None) -> Dict[str, Any]:
    """Create standardized error response."""
    error_body = {
        'error': error_message,
        'statusCode': status_code
    }
    if details:
        error_body['details'] = details
    
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            **get_security_headers()
        },
        'body': json.dumps(error_body)
    }


def create_success_response(data: Dict[str, Any], status_code: int = 200) -> Dict[str, Any]:
    """Create standardized success response."""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            **get_security_headers()
        },
        'body': json.dumps(data)
    }


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda function handler for API Gateway proxy integration.
    
    Args:
        event: API Gateway Lambda Proxy Input Format
        context: Lambda Context runtime methods and attributes
        
    Returns:
        API Gateway Lambda Proxy Output Format
        
    Event doc: https://docs.aws.amazon.com/apigateway/latest/developerguide/set-up-lambda-proxy-integrations.html#api-gateway-simple-proxy-for-lambda-input-format
    Return doc: https://docs.aws.amazon.com/apigateway/latest/developerguide/set-up-lambda-proxy-integrations.html
    """
    
    try:
        # Log masked event for debugging (avoid logging sensitive data)
        masked_event = mask_sensitive_data(event)
        logger.info(f"Processing request: {json.dumps(masked_event)}")
        
        # Extract request components
        http_method = event.get('httpMethod', 'GET')
        path = event.get('path', '/')
        headers = event.get('headers', {})
        query_params = event.get('queryStringParameters')
        body = event.get('body', '')
        
        # Security validations
        origin = headers.get('Origin')
        if origin and not validate_cors_origin(origin):
            return create_error_response(403, 'Invalid origin')
        
        # Validate request size
        if body:
            try:
                validate_request_size(body)
            except ValueError as e:
                return create_error_response(413, 'Request too large', str(e))
        
        # Basic rate limiting (placeholder)
        user_id = headers.get('X-User-ID', 'anonymous')
        if not rate_limit_check(user_id, http_method):
            return create_error_response(429, 'Rate limit exceeded')
        
        # Sanitize query parameters
        sanitized_params = sanitize_query_params(query_params)
        
        logger.info(f"Processing {http_method} request to {path}")
        
        # Handle different HTTP methods
        if http_method == 'GET':
            return handle_get_request(path, sanitized_params, headers)
        elif http_method == 'POST':
            return handle_post_request(path, body, headers)
        elif http_method == 'PUT':
            return handle_put_request(path, body, headers)
        elif http_method == 'DELETE':
            return handle_delete_request(path, headers)
        elif http_method == 'OPTIONS':
            return handle_options_request()
        else:
            return create_error_response(405, 'Method not allowed')
        
    except Exception as e:
        logger.error(f"Unhandled error: {str(e)}", exc_info=True)
        return create_error_response(500, 'Internal server error')


def handle_get_request(path: str, params: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """Handle GET requests."""
    if path == '/hello' or path == '/':
        # Simple health check endpoint
        return create_success_response({
            'message': 'User Service is running',
            'service': 'user-service',
            'version': '1.0.0'
        })
    
    return create_error_response(404, 'Endpoint not found')


def handle_post_request(path: str, body: str, headers: Dict[str, str]) -> Dict[str, Any]:
    """Handle POST requests."""
    try:
        # Validate content type for POST requests
        validate_content_type(headers)
        
        if not body:
            return create_error_response(400, 'Request body required')
        
        # Parse and validate request body
        try:
            request_data = json.loads(body)
        except json.JSONDecodeError:
            return create_error_response(400, 'Invalid JSON format')
        
        if path == '/users':
            # Create user endpoint
            try:
                user_request = CreateUserRequest(**request_data)
                # TODO: Implement actual user creation logic
                response_data = {
                    'message': 'User creation endpoint (not yet implemented)',
                    'data': user_request.dict()
                }
                audit_log('system', 'user_create_attempt', 'users', {'request': mask_sensitive_data(request_data)})
                return create_success_response(response_data, 201)
            except ValueError as e:
                return create_error_response(400, 'Validation error', str(e))
        
        return create_error_response(404, 'Endpoint not found')
        
    except ValueError as e:
        return create_error_response(400, 'Bad request', str(e))


def handle_put_request(path: str, body: str, headers: Dict[str, str]) -> Dict[str, Any]:
    """Handle PUT requests."""
    return create_error_response(501, 'PUT method not implemented yet')


def handle_delete_request(path: str, headers: Dict[str, str]) -> Dict[str, Any]:
    """Handle DELETE requests."""
    return create_error_response(501, 'DELETE method not implemented yet')


def handle_options_request() -> Dict[str, Any]:
    """Handle OPTIONS requests for CORS."""
    return {
        'statusCode': 200,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-User-ID',
            'Access-Control-Max-Age': '86400',
            **get_security_headers()
        },
        'body': ''
    }