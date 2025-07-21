import pytest
import json
from unittest.mock import Mock
import sys
import os

# Add the parent directory to the path so we can import app
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from app import lambda_handler


class TestLambdaHandler:
    """Test cases for the Lambda handler function"""
    
    def test_successful_response(self):
        """Test that the handler returns a successful response"""
        # Arrange
        event = {
            'httpMethod': 'GET',
            'path': '/hello',
            'headers': {},
            'queryStringParameters': None,
            'body': None
        }
        context = Mock()
        
        # Act
        result = lambda_handler(event, context)
        
        # Assert
        assert isinstance(result, dict)
        assert result['statusCode'] == 200
        assert 'body' in result
        assert isinstance(result['body'], str)
        
        # Parse the JSON body
        response_body = json.loads(result['body'])
        assert isinstance(response_body, dict)
        assert response_body['message'] == 'hello world'
        assert response_body['method'] == 'GET'
        assert response_body['path'] == '/hello'
    
    def test_response_headers(self):
        """Test that the response includes proper headers"""
        # Arrange
        event = {
            'httpMethod': 'POST',
            'path': '/test',
            'headers': {},
            'queryStringParameters': None,
            'body': None
        }
        context = Mock()
        
        # Act
        result = lambda_handler(event, context)
        
        # Assert
        assert 'headers' in result
        headers = result['headers']
        assert headers['Content-Type'] == 'application/json'
        assert headers['Access-Control-Allow-Origin'] == '*'
        assert 'Access-Control-Allow-Headers' in headers
        assert 'Access-Control-Allow-Methods' in headers
    
    def test_different_http_methods(self):
        """Test that the handler works with different HTTP methods"""
        methods = ['GET', 'POST', 'PUT', 'DELETE']
        context = Mock()
        
        for method in methods:
            # Arrange
            event = {
                'httpMethod': method,
                'path': f'/{method.lower()}',
                'headers': {},
                'queryStringParameters': None,
                'body': None
            }
            
            # Act
            result = lambda_handler(event, context)
            
            # Assert
            assert result['statusCode'] == 200
            response_body = json.loads(result['body'])
            assert response_body['method'] == method
            assert response_body['path'] == f'/{method.lower()}'
    
    def test_missing_event_fields(self):
        """Test that the handler handles missing event fields gracefully"""
        # Arrange
        event = {}  # Empty event
        context = Mock()
        
        # Act
        result = lambda_handler(event, context)
        
        # Assert
        assert result['statusCode'] == 200
        response_body = json.loads(result['body'])
        assert response_body['method'] == 'GET'  # Default value
        assert response_body['path'] == '/'  # Default value
    
    def test_json_response_structure(self):
        """Test that the JSON response has the expected structure"""
        # Arrange
        event = {
            'httpMethod': 'GET',
            'path': '/test',
            'headers': {},
            'queryStringParameters': None,
            'body': None
        }
        context = Mock()
        
        # Act
        result = lambda_handler(event, context)
        
        # Assert
        response_body = json.loads(result['body'])
        expected_keys = ['message', 'method', 'path']
        for key in expected_keys:
            assert key in response_body
        
        assert response_body['message'] == 'hello world'