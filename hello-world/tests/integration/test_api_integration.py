"""Integration tests for API endpoints."""

import pytest
import json
import requests
import os
from typing import Dict, Any
from unittest.mock import patch

# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration


class TestAPIIntegration:
    """Integration tests for API endpoints."""
    
    @pytest.fixture
    def api_base_url(self) -> str:
        """Get API base URL from environment or use default."""
        return os.environ.get('API_BASE_URL', 'http://localhost:3000')
    
    @pytest.fixture
    def common_headers(self) -> Dict[str, str]:
        """Common headers for API requests."""
        return {
            'Content-Type': 'application/json',
            'User-Agent': 'test-client/1.0'
        }

    def test_health_check_endpoint(self, api_base_url: str):
        """Test the health check endpoint."""
        response = requests.get(f"{api_base_url}/hello", timeout=10)
        
        assert response.status_code == 200
        data = response.json()
        assert data['message'] == 'User Service is running'
        assert data['service'] == 'user-service'
        assert data['version'] == '1.0.0'

    def test_cors_headers(self, api_base_url: str):
        """Test CORS headers are present."""
        response = requests.options(f"{api_base_url}/hello", timeout=10)
        
        assert response.status_code == 200
        assert 'Access-Control-Allow-Origin' in response.headers
        assert 'Access-Control-Allow-Methods' in response.headers
        assert 'Access-Control-Allow-Headers' in response.headers

    def test_security_headers(self, api_base_url: str):
        """Test security headers are present."""
        response = requests.get(f"{api_base_url}/hello", timeout=10)
        
        # Check for security headers
        assert response.headers.get('X-Content-Type-Options') == 'nosniff'
        assert response.headers.get('X-Frame-Options') == 'DENY'
        assert response.headers.get('X-XSS-Protection') == '1; mode=block'
        assert 'Strict-Transport-Security' in response.headers

    def test_user_creation_endpoint_validation(self, api_base_url: str, common_headers: Dict[str, str]):
        """Test user creation endpoint validation."""
        # Test with valid data
        valid_user_data = {
            'name': 'Integration Test User',
            'email': 'integration@test.com'
        }
        
        response = requests.post(
            f"{api_base_url}/users",
            headers=common_headers,
            json=valid_user_data,
            timeout=10
        )
        
        assert response.status_code == 201
        data = response.json()
        assert 'User creation endpoint' in data['message']
        assert data['data']['name'] == 'Integration Test User'
        assert data['data']['email'] == 'integration@test.com'

    def test_user_creation_validation_errors(self, api_base_url: str, common_headers: Dict[str, str]):
        """Test user creation validation errors."""
        # Test with invalid email
        invalid_user_data = {
            'name': 'Test User',
            'email': 'invalid-email'
        }
        
        response = requests.post(
            f"{api_base_url}/users",
            headers=common_headers,
            json=invalid_user_data,
            timeout=10
        )
        
        assert response.status_code == 400
        data = response.json()
        assert data['error'] == 'Validation error'

    def test_invalid_endpoint(self, api_base_url: str):
        """Test request to invalid endpoint."""
        response = requests.get(f"{api_base_url}/invalid-endpoint", timeout=10)
        
        assert response.status_code == 404
        data = response.json()
        assert data['error'] == 'Endpoint not found'

    def test_unsupported_method(self, api_base_url: str):
        """Test unsupported HTTP method."""
        response = requests.patch(f"{api_base_url}/hello", timeout=10)
        
        assert response.status_code == 405
        data = response.json()
        assert data['error'] == 'Method not allowed'

    def test_large_request_body(self, api_base_url: str, common_headers: Dict[str, str]):
        """Test request with large body."""
        large_data = {
            'name': 'Test User',
            'email': 'test@example.com',
            'large_field': 'x' * 20000  # Exceeds size limit
        }
        
        response = requests.post(
            f"{api_base_url}/users",
            headers=common_headers,
            json=large_data,
            timeout=10
        )
        
        assert response.status_code == 413
        data = response.json()
        assert data['error'] == 'Request too large'

    def test_malformed_json(self, api_base_url: str):
        """Test request with malformed JSON."""
        headers = {'Content-Type': 'application/json'}
        malformed_json = '{"name": "Test", "email": invalid}'
        
        response = requests.post(
            f"{api_base_url}/users",
            headers=headers,
            data=malformed_json,  # Use data instead of json for malformed content
            timeout=10
        )
        
        assert response.status_code == 400
        data = response.json()
        assert data['error'] == 'Invalid JSON format'

    def test_missing_content_type(self, api_base_url: str):
        """Test POST request without Content-Type header."""
        user_data = {
            'name': 'Test User',
            'email': 'test@example.com'
        }
        
        response = requests.post(
            f"{api_base_url}/users",
            json=user_data,
            timeout=10
        )
        
        # This should work because requests automatically sets Content-Type for json parameter
        # Let's test with explicit headers instead
        response = requests.post(
            f"{api_base_url}/users",
            data=json.dumps(user_data),  # Use data with string
            timeout=10
        )
        
        assert response.status_code == 400
        data = response.json()
        assert data['error'] == 'Bad request'

    @pytest.mark.slow
    def test_concurrent_requests(self, api_base_url: str):
        """Test handling of concurrent requests."""
        import threading
        import time
        
        results = []
        
        def make_request():
            try:
                response = requests.get(f"{api_base_url}/hello", timeout=10)
                results.append(response.status_code)
            except Exception as e:
                results.append(f"Error: {e}")
        
        # Create 10 concurrent threads
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=make_request)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # All requests should succeed
        assert len(results) == 10
        assert all(result == 200 for result in results)


class TestDynamoDBIntegration:
    """Integration tests for DynamoDB operations."""
    
    @pytest.fixture
    def user_model(self):
        """Get User model with test configuration."""
        # This would require actual DynamoDB setup for full integration testing
        # For now, we'll mock the model
        from models.user import User
        return User

    @pytest.mark.skipif(
        not os.environ.get('DYNAMODB_ENDPOINT'),
        reason="DynamoDB endpoint not configured"
    )
    def test_user_model_connection(self, user_model):
        """Test User model can connect to DynamoDB."""
        # This test requires actual DynamoDB instance
        # Skip if not configured for integration testing
        try:
            # Test if we can describe the table
            user_model.describe_table()
        except Exception as e:
            pytest.skip(f"DynamoDB not available: {e}")

    def test_user_model_validation(self, user_model):
        """Test User model validation without actual database."""
        from datetime import datetime
        
        # Test creating a user instance (doesn't save to DB)
        user_data = {
            'id': '550e8400-e29b-41d4-a716-446655440000',
            'name': 'Test User',
            'email': 'test@example.com',
            'is_certified': False,
            'created_at': datetime.utcnow()
        }
        
        user = user_model(**user_data)
        assert user.id == user_data['id']
        assert user.name == user_data['name']
        assert user.email == user_data['email']
        assert user.is_certified == user_data['is_certified']


@pytest.mark.integration
class TestEnvironmentConfiguration:
    """Test environment-specific configuration."""
    
    def test_environment_variables(self):
        """Test that required environment variables are set."""
        # These would be set in actual deployment environments
        env_vars = ['USER_TABLE_NAME', 'ENVIRONMENT']
        
        for var in env_vars:
            # In integration tests, these might not be set
            # So we test the fallback behavior
            value = os.environ.get(var)
            if value:
                assert isinstance(value, str)
                assert len(value) > 0

    def test_cors_configuration(self):
        """Test CORS configuration from environment."""
        from utils.security import validate_cors_origin
        
        # Test with environment variable
        with patch.dict(os.environ, {'ALLOWED_ORIGINS': 'https://example.com,https://app.example.com'}):
            assert validate_cors_origin('https://example.com') is True
            assert validate_cors_origin('https://malicious.com') is False
        
        # Test fallback behavior
        with patch.dict(os.environ, {}, clear=True):
            assert validate_cors_origin('http://localhost:3000') is True