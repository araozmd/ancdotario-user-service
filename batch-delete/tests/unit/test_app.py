import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from moto import mock_s3
import boto3
import sys
import os

# Add the app directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# Import the app module
import app

class TestBatchDelete:
    """Test cases for batch delete functionality"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.mock_context = Mock()
        self.mock_context.get_remaining_time_in_millis.return_value = 30000  # 30 seconds
        
        self.valid_event = {
            'requestContext': {
                'authorizer': {
                    'claims': {
                        'sub': 'test-user-123',
                        'email': 'test@example.com'
                    }
                },
                'requestTime': '2023-12-01T10:00:00Z'
            },
            'body': json.dumps({
                'user_ids': ['test-user-123', 'test-user-456'],
                'confirm': True,
                'reason': 'Test cleanup'
            })
        }
        
        self.test_mode_event = {
            'requestContext': {
                'authorizer': {
                    'claims': {
                        'sub': 'admin-user',
                        'email': 'admin@example.com'
                    }
                },
                'requestTime': '2023-12-01T10:00:00Z'
            },
            'body': json.dumps({
                'user_ids': ['test-user-123', 'test-user-456'],
                'confirm': True,
                'test_mode': True,
                'reason': 'Automated test cleanup'
            })
        }

    def test_lambda_handler_success(self):
        """Test successful batch deletion"""
        with patch('app.handle_batch_deletion') as mock_handler:
            mock_handler.return_value = {'statusCode': 200, 'body': '{"message": "success"}'}
            
            result = app.lambda_handler(self.valid_event, self.mock_context)
            
            assert result['statusCode'] == 200
            mock_handler.assert_called_once_with(self.valid_event, self.mock_context)

    def test_missing_request_body(self):
        """Test error handling for missing request body"""
        event_without_body = {
            'requestContext': {
                'authorizer': {
                    'claims': {
                        'sub': 'test-user-123'
                    }
                }
            }
        }
        
        result = app.handle_batch_deletion(event_without_body, self.mock_context)
        
        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert 'Request body is required' in body['error']

    def test_invalid_json_body(self):
        """Test error handling for invalid JSON in request body"""
        invalid_json_event = {
            'requestContext': {
                'authorizer': {
                    'claims': {
                        'sub': 'test-user-123'
                    }
                }
            },
            'body': 'invalid json {'
        }
        
        result = app.handle_batch_deletion(invalid_json_event, self.mock_context)
        
        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert 'Invalid JSON' in body['error']

    def test_empty_user_ids(self):
        """Test error handling for empty user_ids array"""
        empty_ids_event = {
            'requestContext': {
                'authorizer': {
                    'claims': {
                        'sub': 'test-user-123'
                    }
                }
            },
            'body': json.dumps({'user_ids': []})
        }
        
        result = app.handle_batch_deletion(empty_ids_event, self.mock_context)
        
        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert 'cannot be empty' in body['error']

    def test_batch_size_limit(self):
        """Test batch size limit enforcement"""
        large_batch_event = {
            'requestContext': {
                'authorizer': {
                    'claims': {
                        'sub': 'test-user-123'
                    }
                }
            },
            'body': json.dumps({
                'user_ids': [f'user-{i}' for i in range(51)]  # Exceeds MAX_BATCH_SIZE
            })
        }
        
        result = app.handle_batch_deletion(large_batch_event, self.mock_context)
        
        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert 'exceeds maximum limit' in body['error']

    def test_confirmation_required(self):
        """Test that confirmation is required for batch deletion"""
        no_confirm_event = {
            'requestContext': {
                'authorizer': {
                    'claims': {
                        'sub': 'test-user-123'
                    }
                }
            },
            'body': json.dumps({
                'user_ids': ['test-user-123']
            })
        }
        
        result = app.handle_batch_deletion(no_confirm_event, self.mock_context)
        
        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert 'requires confirmation' in body['error']

    @patch('app.User')
    def test_validate_batch_users_success(self, mock_user_class):
        """Test successful user validation"""
        # Mock user exists
        mock_user = Mock()
        mock_user.to_dict.return_value = {'cognito_id': 'test-user-123', 'nickname': 'testuser'}
        mock_user.thumbnail_url = None
        mock_user.standard_s3_key = None
        mock_user.high_res_s3_key = None
        mock_user.image_url = None
        mock_user_class.get.return_value = mock_user
        
        result = app.validate_batch_users(['test-user-123'], 'test-user-123', False)
        
        assert len(result['valid_users']) == 1
        assert len(result['errors']) == 0
        assert result['valid_users'][0]['user_id'] == 'test-user-123'
        assert not result['valid_users'][0]['has_photos']

    @patch('app.User')
    def test_validate_batch_users_not_found(self, mock_user_class):
        """Test validation with non-existent user"""
        from app import User
        mock_user_class.DoesNotExist = User.DoesNotExist
        mock_user_class.get.side_effect = User.DoesNotExist()
        
        result = app.validate_batch_users(['nonexistent-user'], 'test-user-123', False)
        
        assert len(result['valid_users']) == 0
        assert len(result['errors']) == 1
        assert result['errors'][0]['error_code'] == 'USER_NOT_FOUND'

    @patch('app.User')
    def test_validate_batch_users_unauthorized(self, mock_user_class):
        """Test validation with unauthorized user deletion"""
        mock_user = Mock()
        mock_user.to_dict.return_value = {'cognito_id': 'other-user-456'}
        mock_user_class.get.return_value = mock_user
        
        result = app.validate_batch_users(['other-user-456'], 'test-user-123', False)
        
        assert len(result['valid_users']) == 0
        assert len(result['errors']) == 1
        assert result['errors'][0]['error_code'] == 'UNAUTHORIZED_DELETION'

    @patch('app.User')
    def test_validate_batch_users_test_mode_bypasses_auth(self, mock_user_class):
        """Test that test mode bypasses authorization checks"""
        mock_user = Mock()
        mock_user.to_dict.return_value = {'cognito_id': 'other-user-456'}
        mock_user.thumbnail_url = None
        mock_user.standard_s3_key = None
        mock_user.high_res_s3_key = None
        mock_user.image_url = None
        mock_user_class.get.return_value = mock_user
        
        result = app.validate_batch_users(['other-user-456'], 'test-user-123', True)
        
        assert len(result['valid_users']) == 1
        assert len(result['errors']) == 0

    @patch('app.delete_single_user_with_timeout')
    def test_process_batch_deletions(self, mock_delete_single):
        """Test batch deletion processing"""
        valid_users = [
            {
                'user_id': 'user-1',
                'user_data': {'cognito_id': 'user-1'},
                'has_photos': False
            },
            {
                'user_id': 'user-2',
                'user_data': {'cognito_id': 'user-2'},
                'has_photos': True
            }
        ]
        
        # Mock successful deletion results
        mock_delete_single.side_effect = [
            {
                'success': True,
                'user_data': {'cognito_id': 'user-1'},
                'photos_deleted': 0,
                'cleanup_info': {}
            },
            {
                'success': True,
                'user_data': {'cognito_id': 'user-2'},
                'photos_deleted': 3,
                'cleanup_info': {'photos_deleted_count': 3}
            }
        ]
        
        result = app.process_batch_deletions(valid_users, 'Test reason', self.mock_context)
        
        assert result['successful_count'] == 2
        assert result['total_photos_deleted'] == 3
        assert len(result['errors']) == 0
        assert len(result['successful_deletions']) == 2

    @patch('app.User')
    def test_delete_single_user_success(self, mock_user_class):
        """Test successful single user deletion"""
        mock_user = Mock()
        mock_user.to_dict.return_value = {'cognito_id': 'test-user-123'}
        mock_user_class.get.return_value = mock_user
        
        user_data = {
            'user_id': 'test-user-123',
            'has_photos': False
        }
        
        with patch('app.BUCKET_NAME', None):  # No S3 bucket configured
            result = app.delete_single_user_with_timeout(user_data, 'Test', self.mock_context)
        
        assert result['success'] is True
        assert result['user_data']['cognito_id'] == 'test-user-123'
        assert result['photos_deleted'] == 0
        mock_user.delete.assert_called_once()

    @patch('app.User')
    def test_delete_single_user_not_found(self, mock_user_class):
        """Test single user deletion with non-existent user"""
        from app import User
        mock_user_class.DoesNotExist = User.DoesNotExist
        mock_user_class.get.side_effect = User.DoesNotExist()
        
        user_data = {
            'user_id': 'nonexistent-user',
            'has_photos': False
        }
        
        result = app.delete_single_user_with_timeout(user_data, 'Test', self.mock_context)
        
        assert result['success'] is False
        assert result['error_code'] == 'USER_NOT_FOUND'

    def test_delete_single_user_timeout_protection(self):
        """Test timeout protection in single user deletion"""
        self.mock_context.get_remaining_time_in_millis.return_value = 3000  # 3 seconds
        
        user_data = {
            'user_id': 'test-user-123',
            'has_photos': False
        }
        
        result = app.delete_single_user_with_timeout(user_data, 'Test', self.mock_context)
        
        assert result['success'] is False
        assert result['error_code'] == 'TIMEOUT_RISK'

    @mock_s3
    @patch('app.BUCKET_NAME', 'test-bucket')
    def test_delete_user_photos(self):
        """Test S3 photo deletion"""
        # Create mock S3 bucket and objects
        s3_client = boto3.client('s3', region_name='us-east-1')
        s3_client.create_bucket(Bucket='test-bucket')
        
        # Create test objects
        test_objects = [
            'users/test-user-123/thumbnail.jpg',
            'users/test-user-123/standard.jpg',
            'users/test-user-123/high_res.jpg'
        ]
        
        for obj_key in test_objects:
            s3_client.put_object(Bucket='test-bucket', Key=obj_key, Body=b'test content')
        
        # Test deletion
        with patch('app.s3_client', s3_client):
            deleted_files = app.delete_user_photos('test-user-123')
        
        assert len(deleted_files) == 3
        assert all(key in deleted_files for key in test_objects)

    @mock_s3  
    @patch('app.BUCKET_NAME', 'test-bucket')
    def test_delete_user_photos_no_objects(self):
        """Test S3 photo deletion when no photos exist"""
        # Create mock S3 bucket with no objects
        s3_client = boto3.client('s3', region_name='us-east-1')
        s3_client.create_bucket(Bucket='test-bucket')
        
        with patch('app.s3_client', s3_client):
            deleted_files = app.delete_user_photos('test-user-123')
        
        assert len(deleted_files) == 0

    def test_duplicate_user_ids_removed(self):
        """Test that duplicate user IDs are removed from request"""
        duplicate_event = {
            'requestContext': {
                'authorizer': {
                    'claims': {
                        'sub': 'test-user-123'
                    }
                }
            },
            'body': json.dumps({
                'user_ids': ['test-user-123', 'test-user-456', 'test-user-123'],  # Duplicate
                'confirm': True
            })
        }
        
        with patch('app.validate_batch_users') as mock_validate, \
             patch('app.process_batch_deletions') as mock_process:
            
            mock_validate.return_value = {'valid_users': [], 'errors': []}
            mock_process.return_value = {
                'successful_deletions': [],
                'errors': [],
                'successful_count': 0,
                'total_photos_deleted': 0,
                'processing_time': 0.1
            }
            
            app.handle_batch_deletion(duplicate_event, self.mock_context)
            
            # Should be called with deduplicated list
            mock_validate.assert_called_once()
            args = mock_validate.call_args[0]
            assert len(args[0]) == 2  # Only unique user IDs
            assert 'test-user-123' in args[0]
            assert 'test-user-456' in args[0]

    @patch('app.get_authenticated_user')
    def test_authentication_failure(self, mock_auth):
        """Test handling of authentication failure"""
        mock_auth.return_value = (None, {
            'statusCode': 401,
            'body': json.dumps({'error': 'Unauthorized'})
        })
        
        result = app.handle_batch_deletion(self.valid_event, self.mock_context)
        
        assert result['statusCode'] == 401

    def test_response_format_partial_success(self):
        """Test response format for partial success scenario"""
        with patch('app.get_authenticated_user') as mock_auth, \
             patch('app.validate_batch_users') as mock_validate, \
             patch('app.process_batch_deletions') as mock_process:
            
            mock_auth.return_value = ({'sub': 'test-user-123'}, None)
            mock_validate.return_value = {
                'valid_users': [{'user_id': 'test-user-123'}],
                'errors': [{'user_id': 'invalid-user', 'error': 'Not found'}]
            }
            mock_process.return_value = {
                'successful_deletions': [{'user_id': 'test-user-123'}],
                'errors': [],
                'successful_count': 1,
                'total_photos_deleted': 5,
                'processing_time': 1.5
            }
            
            result = app.handle_batch_deletion(self.valid_event, self.mock_context)
            
            assert result['statusCode'] == 207  # Multi-Status for partial success
            body = json.loads(result['body'])
            assert body['summary']['successful_count'] == 1
            assert body['summary']['failed_count'] == 1
            assert body['summary']['total_photos_deleted'] == 5

if __name__ == '__main__':
    pytest.main([__file__])