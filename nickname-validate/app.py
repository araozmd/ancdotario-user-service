import json
import logging
import boto3
import os
from typing import Dict, Any, Optional

# Import from CodeArtifact package
try:
    from anecdotario_commons.contracts import NicknameContracts
    from anecdotario_commons.exceptions import ValidationError
    from anecdotario_commons.response import create_response, create_error_response
    COMMONS_AVAILABLE = True
except ImportError:
    # Fallback if commons package not available
    NicknameContracts = None
    ValidationError = Exception
    COMMONS_AVAILABLE = False
    
    # Simple response functions as fallback with CORS headers for anonymous endpoints
    def create_response(status_code: int, body: dict) -> dict:
        return {
            'statusCode': status_code,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET,OPTIONS'
            },
            'body': json.dumps(body)
        }
    
    def create_error_response(status_code: int, message: str, details: dict = None) -> dict:
        return create_response(status_code, {
            'error': message,
            'statusCode': status_code,
            'details': details
        })

# Initialize AWS clients
lambda_client = boto3.client('lambda')

# Configuration
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
COMMONS_NICKNAME_FUNCTION = f"anecdotario-nickname-validate-{ENVIRONMENT}"

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Validate nickname availability and format using Commons Service
    
    GET /users/validate-nickname/{nickname}
    
    Note: This endpoint is specifically for USER nickname validation.
    Organizations have their own validation service (anecdotario-org-service).
    """
    try:
        # No authentication required - this is an anonymous endpoint for registration flow
        # CORS configuration in API Gateway restricts origins (staging/prod only allow specific domains)
        
        # Extract path parameters
        path_params = event.get('pathParameters') or {}
        nickname = path_params.get('nickname')
        
        if not nickname:
            return create_response(
                400,
                {
                    'error': 'Missing nickname parameter',
                    'message': 'Nickname is required in path: /users/validate-nickname/{nickname}'
                }
            )
        
        # User Service only validates USER nicknames (constant entity_type)
        # Organizations have their own dedicated validation service
        entity_type = 'user'  # Constant - this service is user-specific
        
        # Note: We ignore any entity_type query parameter for backward compatibility,
        # but this endpoint always validates as 'user' since it's in the User Service
        
        logger.info(f"Validating USER nickname '{nickname}' (entity_type='{entity_type}')")
        
        # Call commons service nickname validation via Lambda invocation
        try:
            # Prepare payload for commons service Lambda (direct format as per documentation)
            payload = {
                "nickname": nickname,
                "entity_type": entity_type
            }
            
            logger.info(f"Invoking commons nickname validation service for: {nickname}")
            
            # Invoke commons service Lambda function
            response = lambda_client.invoke(
                FunctionName=COMMONS_NICKNAME_FUNCTION,
                InvocationType='RequestResponse',  # Synchronous invocation
                Payload=json.dumps(payload)
            )
            
            # Parse response from Lambda (direct format as per documentation)
            response_payload = json.loads(response['Payload'].read())
            logger.info(f"Commons service response: {response_payload}")
            
            # Check for function errors
            if response.get('FunctionError'):
                logger.error(f"Commons service function error: {response_payload}")
                raise Exception(f"Commons service error: {response_payload.get('errorMessage', 'Unknown error')}")
            
            # The commons service is returning API Gateway format even for direct invocation
            # Parse the actual validation results from the body
            if response_payload.get('statusCode') == 200:
                # Parse successful validation response
                validation_data = json.loads(response_payload['body'])
                
                # Add metadata to successful response
                validation_data.update({
                    'requested_by': 'anonymous',  # No auth required for nickname validation
                    'timestamp': context.aws_request_id if context else None,
                    'service': 'user-service',
                    'entity_type': 'user'  # Always user for this service
                })
                
                # Return clean API Gateway response with CORS
                return create_response(200, validation_data)
            else:
                # Parse error response from commons service
                error_data = json.loads(response_payload.get('body', '{}'))
                error_message = error_data.get('error', 'Nickname validation failed')
                raise ValidationError(error_message)
            
        except ValidationError as e:
            logger.error(f"Validation error: {str(e)}")
            return create_response(
                400,
                {
                    'error': 'Validation failed',
                    'message': str(e),
                    'error_type': 'ValidationError',
                    'commons_service': True
                }
            )
        except Exception as e:
            logger.error(f"Commons service error: {str(e)}")
            return create_response(
                500,
                {
                    'error': 'Nickname validation service error',
                    'message': 'Failed to validate nickname via commons service',
                    'details': str(e),
                    'commons_service': True
                }
            )
        
    except Exception as e:
        logger.error(f"Unexpected error in nickname validation: {str(e)}")
        return create_response(
            500,
            {
                'error': 'Internal server error',
                'message': 'An unexpected error occurred during nickname validation'
            }
        )


def get_validation_rules(entity_type: str = 'user') -> Dict[str, Any]:
    """
    Get validation rules for nickname formatting
    
    Helper function that can be called from other endpoints
    """
    if not NicknameContracts:
        return {
            'error': 'Commons service unavailable',
            'rules': None
        }
    
    try:
        return NicknameContracts.get_validation_rules(entity_type=entity_type)
    except Exception as e:
        logger.error(f"Failed to get validation rules: {str(e)}")
        return {
            'error': str(e),
            'rules': None
        }