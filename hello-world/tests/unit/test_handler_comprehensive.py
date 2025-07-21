"""Comprehensive tests for the Lambda handler."""

import pytest
import json
from unittest.mock import Mock, patch
import sys
import os

# Add the parent directory to the path so we can import app
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from app import (
    lambda_handler,
    create_error_response,
    create_success_response,
    handle_get_request,
    handle_post_request,
    handle_options_request,
)


class TestLambdaHandlerComprehensive:
    """Comprehensive test cases for the main Lambda handler."""
    
    def test_successful_get_request(self):
        """Test successful GET request to /hello endpoint."""
        event = {
            'httpMethod': 'GET',
            'path': '/hello',
            'headers': {},
            'queryStringParameters': None,
            'body': None
        }
        context = Mock()
        
        result = lambda_handler(event, context)
        
        assert result['statusCode'] == 200
        assert 'body' in result
        response_body = json.loads(result['body'])
        assert response_body['message'] == 'User Service is running'
        assert response_body['service'] == 'user-service'

    def test_post_request_with_valid_data(self):
        """Test POST request with valid user data."""
        event = {
            'httpMethod': 'POST',
            'path': '/users',
            'headers': {'Content-Type': 'application/json'},
            'queryStringParameters': None,
            'body': json.dumps({
                'name': 'John Doe',
                'email': 'john@example.com'
            })
        }
        context = Mock()
        
        result = lambda_handler(event, context)
        
        assert result['statusCode'] == 201
        response_body = json.loads(result['body'])
        assert 'User creation endpoint' in response_body['message']

    def test_post_request_with_invalid_data(self):
        """Test POST request with invalid user data."""
        event = {
            'httpMethod': 'POST',
            'path': '/users',
            'headers': {'Content-Type': 'application/json'},
            'queryStringParameters': None,
            'body': json.dumps({
                'name': '',  # Empty name should fail validation
                'email': 'invalid-email'  # Invalid email format
            })
        }
        context = Mock()
        
        result = lambda_handler(event, context)
        
        assert result['statusCode'] == 400
        response_body = json.loads(result['body'])
        assert response_body['error'] == 'Validation error'

    def test_unsupported_method(self):
        """Test unsupported HTTP method."""
        event = {
            'httpMethod': 'PATCH',
            'path': '/hello',
            'headers': {},
            'queryStringParameters': None,
            'body': None
        }
        context = Mock()
        
        result = lambda_handler(event, context)
        
        assert result['statusCode'] == 405
        response_body = json.loads(result['body'])
        assert response_body['error'] == 'Method not allowed'

    def test_large_request_body(self):
        """Test request with body exceeding size limit."""
        large_body = 'x' * 20000  # Exceeds 10KB limit
        event = {
            'httpMethod': 'POST',
            'path': '/users',
            'headers': {'Content-Type': 'application/json'},
            'queryStringParameters': None,
            'body': large_body
        }
        context = Mock()
        
        result = lambda_handler(event, context)
        
        assert result['statusCode'] == 413
        response_body = json.loads(result['body'])
        assert response_body['error'] == 'Request too large'

    def test_invalid_cors_origin(self):
        """Test request with invalid CORS origin."""
        with patch('app.validate_cors_origin', return_value=False):
            event = {
                'httpMethod': 'GET',
                'path': '/hello',
                'headers': {'Origin': 'https://malicious.com'},
                'queryStringParameters': None,
                'body': None
            }
            context = Mock()
            
            result = lambda_handler(event, context)
            
            assert result['statusCode'] == 403
            response_body = json.loads(result['body'])
            assert response_body['error'] == 'Invalid origin'

    def test_options_request(self):
        """Test OPTIONS request for CORS preflight."""
        event = {
            'httpMethod': 'OPTIONS',
            'path': '/hello',
            'headers': {},
            'queryStringParameters': None,
            'body': None
        }
        context = Mock()
        
        result = lambda_handler(event, context)
        
        assert result['statusCode'] == 200
        assert 'Access-Control-Allow-Origin' in result['headers']
        assert 'Access-Control-Allow-Methods' in result['headers']

    def test_unhandled_exception(self):
        """Test handling of unhandled exceptions."""
        with patch('app.handle_get_request', side_effect=Exception('Unexpected error')):
            event = {
                'httpMethod': 'GET',
                'path': '/hello',
                'headers': {},
                'queryStringParameters': None,
                'body': None
            }
            context = Mock()
            
            result = lambda_handler(event, context)
            
            assert result['statusCode'] == 500
            response_body = json.loads(result['body'])
            assert response_body['error'] == 'Internal server error'

    def test_security_headers_present(self):
        """Test that security headers are present in responses."""
        event = {
            'httpMethod': 'GET',
            'path': '/hello',
            'headers': {},
            'queryStringParameters': None,
            'body': None
        }
        context = Mock()
        
        result = lambda_handler(event, context)
        
        # Check for security headers
        assert 'X-Content-Type-Options' in result['headers']
        assert 'X-Frame-Options' in result['headers']
        assert 'X-XSS-Protection' in result['headers']


class TestResponseHelpers:
    """Test cases for response helper functions."""

    def test_create_error_response(self):
        """Test error response creation."""
        response = create_error_response(400, 'Bad Request', 'Invalid input')
        
        assert response['statusCode'] == 400
        assert response['headers']['Content-Type'] == 'application/json'
        
        body = json.loads(response['body'])
        assert body['error'] == 'Bad Request'
        assert body['statusCode'] == 400
        assert body['details'] == 'Invalid input'

    def test_create_error_response_without_details(self):
        """Test error response creation without details."""
        response = create_error_response(404, 'Not Found')
        
        body = json.loads(response['body'])
        assert body['error'] == 'Not Found'
        assert 'details' not in body

    def test_create_success_response(self):
        """Test success response creation."""
        data = {'message': 'Success', 'id': '123'}
        response = create_success_response(data, 201)
        
        assert response['statusCode'] == 201
        assert response['headers']['Content-Type'] == 'application/json'
        
        body = json.loads(response['body'])
        assert body == data

    def test_create_success_response_default_status(self):
        """Test success response with default status code."""
        data = {'message': 'Success'}
        response = create_success_response(data)
        
        assert response['statusCode'] == 200


class TestRouteHandlers:
    """Test cases for individual route handlers."""

    def test_handle_get_request_hello(self):
        """Test GET request to /hello endpoint."""
        response = handle_get_request('/hello', {}, {})
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['message'] == 'User Service is running'

    def test_handle_get_request_root(self):
        """Test GET request to root endpoint."""
        response = handle_get_request('/', {}, {})
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['message'] == 'User Service is running'

    def test_handle_get_request_not_found(self):
        """Test GET request to non-existent endpoint."""
        response = handle_get_request('/nonexistent', {}, {})
        
        assert response['statusCode'] == 404
        body = json.loads(response['body'])
        assert body['error'] == 'Endpoint not found'

    def test_handle_post_request_missing_body(self):
        """Test POST request without body."""
        response = handle_post_request('/users', '', {'Content-Type': 'application/json'})
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error'] == 'Request body required'

    def test_handle_post_request_invalid_json(self):
        """Test POST request with invalid JSON."""
        response = handle_post_request('/users', 'invalid json', {'Content-Type': 'application/json'})
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error'] == 'Invalid JSON format'

    def test_handle_post_request_wrong_content_type(self):
        """Test POST request with wrong content type."""
        response = handle_post_request('/users', '{}', {'Content-Type': 'text/plain'})
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error'] == 'Bad request'

    def test_handle_options_request(self):
        """Test OPTIONS request handler."""
        response = handle_options_request()
        
        assert response['statusCode'] == 200
        assert response['body'] == ''
        assert 'Access-Control-Allow-Origin' in response['headers']
        assert 'Access-Control-Allow-Methods' in response['headers']
        assert 'Access-Control-Allow-Headers' in response['headers']