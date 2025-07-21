"""
Shared authentication module for JWT validation and CORS handling
"""
import jwt
from jwt import PyJWKClient
from config import config


class CognitoJWTValidator:
    """JWT validator for AWS Cognito tokens"""
    
    def __init__(self):
        self.cognito_user_pool_id = config.get_cognito_parameter('user-pool-id')
        self.aws_region = config.get_cognito_parameter('region', 'us-east-1')
        
        # Initialize JWKS client
        jwks_url = f'https://cognito-idp.{self.aws_region}.amazonaws.com/{self.cognito_user_pool_id}/.well-known/jwks.json'
        self.jwks_client = PyJWKClient(jwks_url)
    
    def validate_token(self, event):
        """
        Validate JWT token from Authorization header
        Returns: (decoded_token, error_message)
        """
        auth_header = event.get('headers', {}).get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return None, 'Missing or invalid authorization header'
        
        token = auth_header[7:]  # Remove 'Bearer ' prefix
        
        try:
            signing_key = self.jwks_client.get_signing_key_from_jwt(token)
            decoded_token = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=None,  # No audience validation
                issuer=f'https://cognito-idp.{self.aws_region}.amazonaws.com/{self.cognito_user_pool_id}'
            )
            return decoded_token, None
        except Exception as e:
            return None, f'Invalid token: {str(e)}'


class CORSHandler:
    """CORS handling utilities"""
    
    def __init__(self):
        # Configuration for CORS
        self.allowed_origins = config.get_list_parameter('allowed-origins', default=['https://localhost:3000'])
        
        # Optional: Allow SSM override for CORS origins
        try:
            ssm_origins = config.get_ssm_parameter('allowed-origins')
            self.allowed_origins = ssm_origins.split(',') if ssm_origins else self.allowed_origins
        except ValueError:
            # No SSM override, use local .env file values
            pass
    
    def get_allowed_origin(self, event):
        """Get the allowed origin based on the request origin"""
        origin = event.get('headers', {}).get('origin', '')
        if origin in self.allowed_origins:
            return origin
        # Default to first allowed origin if no match
        return self.allowed_origins[0] if self.allowed_origins else '*'
    
    def get_headers(self, event, additional_methods=None):
        """Get standard CORS headers"""
        methods = ['OPTIONS']
        if additional_methods:
            methods.extend(additional_methods)
        
        return {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': self.get_allowed_origin(event),
            'Access-Control-Allow-Headers': 'Content-Type,Authorization',
            'Access-Control-Allow-Methods': ','.join(methods)
        }


# Shared instances
jwt_validator = CognitoJWTValidator()
cors_handler = CORSHandler()


def create_response(status_code, body, event, additional_methods=None):
    """Create standardized API Gateway response"""
    return {
        'statusCode': status_code,
        'headers': cors_handler.get_headers(event, additional_methods),
        'body': body
    }


def create_error_response(status_code, error_message, event, additional_data=None):
    """Create standardized error response"""
    import json
    
    error_body = {'error': error_message}
    if additional_data:
        error_body.update(additional_data)
    
    return create_response(status_code, json.dumps(error_body), event)


def validate_request_auth(event):
    """
    Validate request authentication
    Returns: (decoded_token, error_response)
    """
    decoded_token, error = jwt_validator.validate_token(event)
    if error:
        return None, create_error_response(401, error, event)
    return decoded_token, None


def handle_options_request(event):
    """Handle CORS preflight OPTIONS request"""
    return create_response(200, '', event)