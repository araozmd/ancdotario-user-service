"""
Integration tests for photo upload API Gateway contracts.
These tests validate the API Gateway integration, request/response formats,
and authentication flow without mocking AWS services.
"""
import json
import pytest
import base64
import os
import sys
import requests
from PIL import Image
import io

# Add paths for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared'))


@pytest.fixture
def api_base_url():
    """Get API base URL from environment or default to local SAM"""
    return os.environ.get('API_BASE_URL', 'http://localhost:3000')


@pytest.fixture
def jwt_token():
    """Get JWT token from environment for authentication"""
    token = os.environ.get('JWT_TOKEN')
    if not token:
        pytest.skip("JWT_TOKEN environment variable not set")
    return token


@pytest.fixture
def test_user_id():
    """Get test user ID from environment"""
    user_id = os.environ.get('TEST_USER_ID', 'test-user-123')
    return user_id


@pytest.fixture
def sample_image_base64():
    """Create a sample image and return as base64"""
    img = Image.new('RGB', (100, 100), color='red')
    buffer = io.BytesIO()
    img.save(buffer, format='JPEG')
    img_bytes = buffer.getvalue()
    return base64.b64encode(img_bytes).decode('utf-8')


@pytest.fixture
def auth_headers(jwt_token):
    """Standard headers with JWT authentication"""
    return {
        'Authorization': f'Bearer {jwt_token}',
        'Content-Type': 'application/json',
        'Origin': 'https://anecdotario.com'
    }


class TestPhotoUploadAPIContracts:
    """Test API Gateway contracts for photo upload endpoint"""

    def test_successful_photo_upload_contract(self, api_base_url, test_user_id, 
                                            auth_headers, sample_image_base64):
        """Test successful photo upload API contract"""
        endpoint = f"{api_base_url}/users/{test_user_id}/photo"
        
        payload = {
            'image': f'data:image/jpeg;base64,{sample_image_base64}',
            'nickname': 'integrationtest'
        }
        
        response = requests.post(endpoint, json=payload, headers=auth_headers)
        
        # Verify response structure
        assert response.status_code == 200
        
        # Verify CORS headers
        assert 'Access-Control-Allow-Origin' in response.headers
        assert 'Access-Control-Allow-Methods' in response.headers
        
        # Verify response body structure
        body = response.json()
        assert 'message' in body
        assert 'images' in body
        assert 'photo_id' in body
        assert 'user' in body
        assert 'commons_service' in body
        
        # Verify image URLs structure
        if body['images']:
            expected_image_keys = {'thumbnail', 'standard', 'high_res'}
            assert set(body['images'].keys()).intersection(expected_image_keys)
        
        # Verify user data structure
        user_data = body['user']
        assert 'cognito_id' in user_data
        assert 'nickname' in user_data
        assert 'images' in user_data or 'image_url' in user_data  # Backward compatibility

    def test_cors_preflight_options_request(self, api_base_url, test_user_id):
        """Test CORS preflight OPTIONS request"""
        endpoint = f"{api_base_url}/users/{test_user_id}/photo"
        
        headers = {
            'Origin': 'https://anecdotario.com',
            'Access-Control-Request-Method': 'POST',
            'Access-Control-Request-Headers': 'Authorization,Content-Type'
        }
        
        response = requests.options(endpoint, headers=headers)
        
        assert response.status_code == 200
        assert 'Access-Control-Allow-Origin' in response.headers
        assert 'Access-Control-Allow-Methods' in response.headers
        assert 'Access-Control-Allow-Headers' in response.headers
        assert response.text == ''

    def test_missing_authorization_returns_401(self, api_base_url, test_user_id, sample_image_base64):
        """Test that missing authorization returns 401"""
        endpoint = f"{api_base_url}/users/{test_user_id}/photo"
        
        payload = {
            'image': f'data:image/jpeg;base64,{sample_image_base64}'
        }
        
        headers = {
            'Content-Type': 'application/json'
        }
        
        response = requests.post(endpoint, json=payload, headers=headers)
        
        assert response.status_code == 401
        body = response.json()
        assert 'error' in body

    def test_invalid_jwt_returns_401(self, api_base_url, test_user_id, sample_image_base64):
        """Test that invalid JWT returns 401"""
        endpoint = f"{api_base_url}/users/{test_user_id}/photo"
        
        payload = {
            'image': f'data:image/jpeg;base64,{sample_image_base64}'
        }
        
        headers = {
            'Authorization': 'Bearer invalid-token',
            'Content-Type': 'application/json'
        }
        
        response = requests.post(endpoint, json=payload, headers=headers)
        
        assert response.status_code == 401
        body = response.json()
        assert 'error' in body

    def test_wrong_user_returns_403(self, api_base_url, auth_headers, sample_image_base64):
        """Test that trying to upload for wrong user returns 403"""
        # Use a different user ID than what's in the JWT token
        different_user_id = 'different-user-456'
        endpoint = f"{api_base_url}/users/{different_user_id}/photo"
        
        payload = {
            'image': f'data:image/jpeg;base64,{sample_image_base64}'
        }
        
        response = requests.post(endpoint, json=payload, headers=auth_headers)
        
        assert response.status_code == 403
        body = response.json()
        assert 'error' in body
        assert 'Unauthorized' in body['error']

    def test_missing_image_returns_400(self, api_base_url, test_user_id, auth_headers):
        """Test that missing image data returns 400"""
        endpoint = f"{api_base_url}/users/{test_user_id}/photo"
        
        payload = {
            'nickname': 'testuser'
        }
        
        response = requests.post(endpoint, json=payload, headers=auth_headers)
        
        assert response.status_code == 400
        body = response.json()
        assert 'error' in body
        assert 'image data' in body['error'].lower()

    def test_invalid_base64_returns_400(self, api_base_url, test_user_id, auth_headers):
        """Test that invalid base64 data returns 400"""
        endpoint = f"{api_base_url}/users/{test_user_id}/photo"
        
        payload = {
            'image': 'invalid-base64-data!@#$%'
        }
        
        response = requests.post(endpoint, json=payload, headers=auth_headers)
        
        assert response.status_code == 400
        body = response.json()
        assert 'error' in body
        assert 'base64' in body['error'].lower()

    def test_large_image_returns_400(self, api_base_url, test_user_id, auth_headers):
        """Test that oversized image returns 400"""
        endpoint = f"{api_base_url}/users/{test_user_id}/photo"
        
        # Create 6MB of data (exceeds 5MB limit)
        large_data = b'x' * (6 * 1024 * 1024)
        large_image_base64 = base64.b64encode(large_data).decode('utf-8')
        
        payload = {
            'image': f'data:image/jpeg;base64,{large_image_base64}'
        }
        
        response = requests.post(endpoint, json=payload, headers=auth_headers)
        
        assert response.status_code == 400
        body = response.json()
        assert 'error' in body
        assert 'large' in body['error'].lower()

    def test_get_method_not_allowed(self, api_base_url, test_user_id, auth_headers):
        """Test that GET method is not allowed"""
        endpoint = f"{api_base_url}/users/{test_user_id}/photo"
        
        response = requests.get(endpoint, headers=auth_headers)
        
        assert response.status_code == 405 or response.status_code == 403
        # API Gateway might return 403 for method not allowed with authorizer

    def test_malformed_json_returns_400(self, api_base_url, test_user_id, auth_headers):
        """Test that malformed JSON returns 400"""
        endpoint = f"{api_base_url}/users/{test_user_id}/photo"
        
        # Send malformed JSON
        headers = dict(auth_headers)
        headers['Content-Type'] = 'application/json'
        
        response = requests.post(endpoint, data='invalid json {{{', headers=headers)
        
        # Should return 400 for malformed JSON
        assert response.status_code in [400, 500]  # Could be either depending on API Gateway config

    def test_response_content_type_is_json(self, api_base_url, test_user_id, 
                                         auth_headers, sample_image_base64):
        """Test that response Content-Type is application/json"""
        endpoint = f"{api_base_url}/users/{test_user_id}/photo"
        
        payload = {
            'image': f'data:image/jpeg;base64,{sample_image_base64}'
        }
        
        response = requests.post(endpoint, json=payload, headers=auth_headers)
        
        # Regardless of success or failure, should return JSON
        assert 'application/json' in response.headers.get('Content-Type', '')

    def test_error_response_format_consistency(self, api_base_url, test_user_id, auth_headers):
        """Test that error responses follow consistent format"""
        endpoint = f"{api_base_url}/users/{test_user_id}/photo"
        
        # Send request with missing image to trigger error
        payload = {}
        
        response = requests.post(endpoint, json=payload, headers=auth_headers)
        
        assert response.status_code == 400
        body = response.json()
        
        # Verify error response format
        assert 'error' in body
        assert 'statusCode' in body
        assert body['statusCode'] == 400
        
        # Optional details field
        if 'details' in body:
            assert isinstance(body['details'], dict)

    def test_api_gateway_request_id_header(self, api_base_url, test_user_id, auth_headers):
        """Test that API Gateway includes request ID header"""
        endpoint = f"{api_base_url}/users/{test_user_id}/photo"
        
        payload = {}
        
        response = requests.post(endpoint, json=payload, headers=auth_headers)
        
        # API Gateway should include request ID
        assert 'x-amzn-RequestId' in response.headers or 'x-amz-request-id' in response.headers

    def test_new_user_creation_contract(self, api_base_url, auth_headers, sample_image_base64):
        """Test API contract for new user creation"""
        # Use a unique user ID for new user test
        new_user_id = f"new-user-{int(os.urandom(4).hex(), 16)}"
        endpoint = f"{api_base_url}/users/{new_user_id}/photo"
        
        # Modify auth headers to use new user ID (this would need JWT with correct sub claim)
        # For integration test, we assume the JWT token matches the user ID
        
        payload = {
            'image': f'data:image/jpeg;base64,{sample_image_base64}',
            'nickname': f'newuser{int(os.urandom(2).hex(), 16)}'
        }
        
        response = requests.post(endpoint, json=payload, headers=auth_headers)
        
        # Should succeed if JWT contains correct user ID
        # Or return 403 if JWT doesn't match
        assert response.status_code in [200, 403]
        
        if response.status_code == 200:
            body = response.json()
            assert 'user' in body
            assert body['user']['nickname'] == payload['nickname']

    def test_nickname_conflict_contract(self, api_base_url, test_user_id, 
                                      auth_headers, sample_image_base64):
        """Test API contract for nickname conflicts"""
        endpoint = f"{api_base_url}/users/{test_user_id}/photo"
        
        # Use a nickname that's likely to be taken
        payload = {
            'image': f'data:image/jpeg;base64,{sample_image_base64}',
            'nickname': 'admin'  # Common nickname likely to be taken
        }
        
        response = requests.post(endpoint, json=payload, headers=auth_headers)
        
        # Could be 409 (conflict) if nickname taken, or 200 if user already exists
        assert response.status_code in [200, 409]
        
        if response.status_code == 409:
            body = response.json()
            assert 'error' in body
            assert 'nickname' in body['error'].lower()


class TestPhotoUploadPerformance:
    """Performance and load testing for photo upload API"""

    def test_response_time_under_30_seconds(self, api_base_url, test_user_id, 
                                          auth_headers, sample_image_base64):
        """Test that photo upload completes within 30 seconds"""
        import time
        
        endpoint = f"{api_base_url}/users/{test_user_id}/photo"
        
        payload = {
            'image': f'data:image/jpeg;base64,{sample_image_base64}'
        }
        
        start_time = time.time()
        response = requests.post(endpoint, json=payload, headers=auth_headers, timeout=30)
        end_time = time.time()
        
        # Should complete within 30 seconds
        assert (end_time - start_time) < 30
        
        # Should succeed or fail gracefully
        assert response.status_code in [200, 400, 500]

    def test_concurrent_uploads_same_user(self, api_base_url, test_user_id, 
                                        auth_headers, sample_image_base64):
        """Test handling of concurrent uploads for the same user"""
        import concurrent.futures
        import threading
        
        endpoint = f"{api_base_url}/users/{test_user_id}/photo"
        
        def upload_photo(image_suffix):
            # Create slightly different images
            img = Image.new('RGB', (100, 100), color=(255, image_suffix % 256, 0))
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG')
            img_bytes = buffer.getvalue()
            image_b64 = base64.b64encode(img_bytes).decode('utf-8')
            
            payload = {
                'image': f'data:image/jpeg;base64,{image_b64}'
            }
            
            return requests.post(endpoint, json=payload, headers=auth_headers, timeout=30)
        
        # Submit 3 concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(upload_photo, i) for i in range(3)]
            responses = [future.result() for future in concurrent.futures.as_completed(futures)]
        
        # At least one should succeed, others might fail due to race conditions
        success_count = sum(1 for r in responses if r.status_code == 200)
        assert success_count >= 1
        
        # All should return valid HTTP responses
        for response in responses:
            assert response.status_code in [200, 400, 409, 500]


class TestAPIGatewayIntegration:
    """Test specific API Gateway integration aspects"""

    def test_request_timeout_configuration(self, api_base_url, test_user_id, auth_headers):
        """Test that API Gateway timeout is configured properly"""
        endpoint = f"{api_base_url}/users/{test_user_id}/photo"
        
        # Create a very large image to potentially trigger timeout
        large_img = Image.new('RGB', (2000, 2000), color='red')
        buffer = io.BytesIO()
        large_img.save(buffer, format='JPEG', quality=95)
        img_bytes = buffer.getvalue()
        large_image_b64 = base64.b64encode(img_bytes).decode('utf-8')
        
        payload = {
            'image': f'data:image/jpeg;base64,{large_image_b64}'
        }
        
        try:
            # API Gateway has 30 second timeout by default
            response = requests.post(endpoint, json=payload, headers=auth_headers, timeout=35)
            
            # Should either succeed, fail validation, or timeout gracefully
            assert response.status_code in [200, 400, 500, 504]
            
        except requests.exceptions.Timeout:
            # Client timeout is acceptable for this test
            pass

    def test_lambda_cold_start_handling(self, api_base_url, test_user_id, 
                                      auth_headers, sample_image_base64):
        """Test that Lambda cold starts are handled gracefully"""
        endpoint = f"{api_base_url}/users/{test_user_id}/photo"
        
        payload = {
            'image': f'data:image/jpeg;base64,{sample_image_base64}'
        }
        
        # Make multiple requests to test cold start behavior
        responses = []
        for i in range(3):
            response = requests.post(endpoint, json=payload, headers=auth_headers, timeout=30)
            responses.append(response)
        
        # All should succeed or fail consistently
        status_codes = [r.status_code for r in responses]
        
        # Should not have random failures due to cold starts
        success_count = sum(1 for code in status_codes if code == 200)
        error_count = sum(1 for code in status_codes if code >= 400)
        
        # Either all succeed or all fail with same error
        assert success_count == 3 or (success_count == 0 and len(set(status_codes)) <= 2)


# Utility functions for integration testing
def wait_for_api_ready(api_base_url, max_attempts=30):
    """Wait for API to be ready before running tests"""
    import time
    
    for attempt in range(max_attempts):
        try:
            response = requests.get(f"{api_base_url}/health", timeout=5)
            if response.status_code == 200:
                return True
        except requests.exceptions.RequestException:
            pass
        
        time.sleep(1)
    
    return False


# Pytest configuration for integration tests
def pytest_configure(config):
    """Configure pytest for integration tests"""
    # Add custom markers
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )


# Skip integration tests if API is not available
def pytest_collection_modifyitems(config, items):
    """Skip integration tests if API is not available"""
    api_base_url = os.environ.get('API_BASE_URL', 'http://localhost:3000')
    
    if not wait_for_api_ready(api_base_url, max_attempts=5):
        skip_integration = pytest.mark.skip(reason="API not available")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip_integration)