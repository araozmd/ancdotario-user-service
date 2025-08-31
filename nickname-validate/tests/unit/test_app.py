import json
import pytest
from unittest.mock import patch, Mock
import sys
import os

# Add parent directories to path for local imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from nickname_validate.app import lambda_handler


@pytest.fixture
def api_gateway_event():
    """Mock API Gateway event with JWT claims"""
    return {
        "requestContext": {
            "authorizer": {
                "claims": {
                    "sub": "user-123",
                    "email": "test@example.com"
                }
            }
        },
        "pathParameters": {
            "nickname": "testuser"
        },
        "queryStringParameters": {
            "entity_type": "user"
        }
    }


@pytest.fixture
def context():
    """Mock Lambda context"""
    context = Mock()
    context.aws_request_id = "test-request-123"
    return context


@patch('nickname_validate.app.NicknameContracts')
def test_nickname_validation_success(mock_contracts, api_gateway_event, context):
    """Test successful nickname validation"""
    # Mock commons service response
    mock_contracts.validate_nickname.return_value = {
        'success': True,
        'valid': True,
        'original': 'testuser',
        'normalized': 'testuser',
        'entity_type': 'user',
        'errors': [],
        'warnings': [],
        'hints': [],
        'message': 'Nickname is available and valid',
        'validation_passed': True,
        'error': ''
    }
    
    response = lambda_handler(api_gateway_event, context)
    
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['valid'] is True
    assert body['original'] == 'testuser'
    assert body['requested_by'] == 'user-123'
    assert body['service'] == 'user-service'


@patch('nickname_validate.app.NicknameContracts')
def test_nickname_validation_taken(mock_contracts, api_gateway_event, context):
    """Test nickname validation when nickname is taken"""
    # Mock commons service response for taken nickname
    mock_contracts.validate_nickname.return_value = {
        'success': True,
        'valid': False,
        'original': 'admin',
        'normalized': 'admin',
        'entity_type': 'user',
        'errors': ['Nickname "admin" is a reserved word'],
        'warnings': [],
        'hints': ['Try "admin_user", "admin2024", or "my_admin"'],
        'message': 'Nickname is not available',
        'validation_passed': False,
        'error': 'Nickname "admin" is a reserved word'
    }
    
    api_gateway_event['pathParameters']['nickname'] = 'admin'
    
    response = lambda_handler(api_gateway_event, context)
    
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['valid'] is False
    assert 'reserved word' in body['errors'][0]
    assert len(body['hints']) > 0


def test_missing_nickname_parameter(api_gateway_event, context):
    """Test missing nickname in path parameters"""
    api_gateway_event['pathParameters'] = {}
    
    response = lambda_handler(api_gateway_event, context)
    
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'Missing nickname parameter' in body['error']


def test_invalid_entity_type(api_gateway_event, context):
    """Test invalid entity_type parameter"""
    api_gateway_event['queryStringParameters']['entity_type'] = 'invalid'
    
    response = lambda_handler(api_gateway_event, context)
    
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'Invalid entity_type' in body['error']
    assert 'valid_types' in body


@patch('nickname_validate.app.NicknameContracts', None)
def test_commons_service_unavailable(api_gateway_event, context):
    """Test when commons service layer is not available"""
    response = lambda_handler(api_gateway_event, context)
    
    assert response['statusCode'] == 503
    body = json.loads(response['body'])
    assert 'service unavailable' in body['error'].lower()


def test_no_auth_context():
    """Test missing authentication context"""
    event = {
        "pathParameters": {"nickname": "test"},
        "queryStringParameters": {"entity_type": "user"}
    }
    
    response = lambda_handler(event, None)
    
    assert response['statusCode'] == 401
    body = json.loads(response['body'])
    assert 'Unauthorized' in body['error']