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
    
    # Simple response functions as fallback
    def create_response(status_code: int, body: dict) -> dict:
        return {
            'statusCode': status_code,
            'headers': {'Content-Type': 'application/json'},
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
    
    GET /users/validate-nickname/{nickname}?entity_type=user
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
        
        # Extract query parameters
        query_params = event.get('queryStringParameters') or {}
        entity_type = query_params.get('entity_type', 'user')
        
        # Validate entity_type (v1.0.4: campaigns removed - only users and orgs have nicknames)
        valid_entity_types = ['user', 'org']
        if entity_type not in valid_entity_types:
            return create_response(
                400,
                {
                    'error': 'Invalid entity_type',
                    'message': f'entity_type must be one of: {", ".join(valid_entity_types)}',
                    'valid_types': valid_entity_types
                }
            )
        
        logger.info(f"Validating nickname '{nickname}' for entity_type '{entity_type}'")
        
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
            
            # For Lambda-to-Lambda, the response is the direct return value (no HTTP wrapper)
            # The response should contain validation results directly
            
            # Add metadata to successful response
            response_payload.update({
                'requested_by': 'anonymous',  # No auth required for nickname validation
                'timestamp': context.aws_request_id if context else None,
                'service': 'user-service'
            })
            
            # Return success response with validation results
            return create_response(200, response_payload)
            
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