#!/usr/bin/env python3
"""
Local testing script for health-test-mode function
"""

import json
import os
import sys

# Add current directory and shared directory to Python path
sys.path.insert(0, '.')
sys.path.insert(0, os.path.join('..', 'shared'))

import app

def test_determine_test_mode():
    """Test the determine_test_mode function"""
    print("Testing determine_test_mode...")
    
    # Test dev environment
    os.environ['ENVIRONMENT'] = 'dev'
    result = app.determine_test_mode()
    assert result == True, f"Expected True for dev, got {result}"
    print("✓ dev environment correctly identified as test mode")
    
    # Test prod environment  
    os.environ['ENVIRONMENT'] = 'prod'
    result = app.determine_test_mode()
    assert result == False, f"Expected False for prod, got {result}"
    print("✓ prod environment correctly identified as non-test mode")
    
    print("✓ determine_test_mode tests passed\n")

def test_get_service_version():
    """Test the get_service_version function"""
    print("Testing get_service_version...")
    
    # Test with no build indicators
    for env_var in ['AWS_SAM_LOCAL', 'CODEBUILD_BUILD_ID', 'CODEBUILD_START_TIME', 'AWS_LAMBDA_FUNCTION_VERSION']:
        os.environ.pop(env_var, None)
    
    version = app.get_service_version()
    assert 'runtime=' in version, f"Expected runtime indicator, got {version}"
    print(f"✓ Default version: {version}")
    
    # Test with CodeBuild ID
    os.environ['CODEBUILD_BUILD_ID'] = 'test-build-123'
    version = app.get_service_version()
    assert version == 'CODEBUILD_BUILD_ID=test-build-123', f"Expected CodeBuild ID, got {version}"
    print(f"✓ CodeBuild version: {version}")
    
    # Clean up
    os.environ.pop('CODEBUILD_BUILD_ID', None)
    print("✓ get_service_version tests passed\n")

def test_health_handler():
    """Test the main lambda handler"""
    print("Testing lambda_handler...")
    
    # Set up test environment
    test_env = {
        'ENVIRONMENT': 'dev',
        'USER_TABLE_NAME': 'Users-dev', 
        'PHOTO_BUCKET_NAME': 'test-bucket-photos-dev',
        'AWS_EXECUTION_ENV': 'AWS_Lambda_python3.12'
    }
    
    for key, value in test_env.items():
        os.environ[key] = value
    
    # Create test event
    test_event = {
        'httpMethod': 'GET',
        'path': '/health/test-mode',
        'headers': {'Content-Type': 'application/json'}
    }
    
    # Call handler
    response = app.lambda_handler(test_event, None)
    
    # Verify response structure
    assert response['statusCode'] == 200, f"Expected 200, got {response['statusCode']}"
    assert response['headers']['Content-Type'] == 'application/json'
    
    # Parse response body
    body = json.loads(response['body'])
    
    # Verify required fields
    required_fields = ['service', 'environment', 'test_mode', 'health', 'timestamp', 'version', 'connectivity']
    for field in required_fields:
        assert field in body, f"Missing required field: {field}"
    
    # Verify values
    assert body['service'] == 'anecdotario-user-service'
    assert body['environment'] == 'dev'
    assert body['test_mode'] == True
    assert body['health'] in ['ok', 'degraded']  # Will be degraded without AWS access
    assert 'connectivity' in body
    assert 'dynamodb' in body['connectivity']
    assert 's3' in body['connectivity']
    
    print(f"✓ Response: {body['service']} | {body['environment']} | test_mode={body['test_mode']} | health={body['health']}")
    print("✓ lambda_handler tests passed\n")

def test_response_helpers():
    """Test response helper functions"""
    print("Testing response helpers...")
    
    # Test create_response
    response = app.create_response(200, '{"test": "data"}')
    assert response['statusCode'] == 200
    assert response['headers']['Content-Type'] == 'application/json'
    assert response['body'] == '{"test": "data"}'
    print("✓ create_response works correctly")
    
    # Test create_error_response
    error_response = app.create_error_response(400, 'Test error', {'detail': 'value'})
    assert error_response['statusCode'] == 400
    body = json.loads(error_response['body'])
    assert body['error'] == 'Test error'
    assert body['statusCode'] == 400
    assert body['details']['detail'] == 'value'
    print("✓ create_error_response works correctly")
    print("✓ Response helper tests passed\n")

def test_connectivity_checks():
    """Test connectivity checking functions (will fail without AWS access)"""
    print("Testing connectivity checks...")
    
    # These will fail without AWS credentials, but we can test the structure
    os.environ['USER_TABLE_NAME'] = 'test-table'
    dynamo_result = app.check_dynamodb_connectivity()
    assert 'status' in dynamo_result
    print(f"✓ DynamoDB check structure: {dynamo_result['status']}")
    
    os.environ['PHOTO_BUCKET_NAME'] = 'test-bucket'
    s3_result = app.check_s3_connectivity()
    assert 'status' in s3_result
    print(f"✓ S3 check structure: {s3_result['status']}")
    
    print("✓ Connectivity check tests passed\n")

if __name__ == '__main__':
    print("=== Health Test Mode Function - Local Tests ===\n")
    
    try:
        test_determine_test_mode()
        test_get_service_version() 
        test_response_helpers()
        test_connectivity_checks()
        test_health_handler()
        
        print("🎉 All tests passed! Health endpoint is ready for deployment.")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        sys.exit(1)