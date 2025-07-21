"""Tests for security utilities."""

import pytest
from unittest.mock import patch, MagicMock
import os

from utils.security import (
    get_security_headers,
    validate_cors_origin,
    mask_sensitive_data,
    audit_log,
    SecureConfig,
)


class TestGetSecurityHeaders:
    """Test cases for security headers."""

    def test_security_headers_present(self):
        """Test that all required security headers are present."""
        headers = get_security_headers()
        
        expected_headers = [
            'X-Content-Type-Options',
            'X-Frame-Options', 
            'X-XSS-Protection',
            'Strict-Transport-Security',
            'Content-Security-Policy',
            'Referrer-Policy',
        ]
        
        for header in expected_headers:
            assert header in headers

    def test_security_header_values(self):
        """Test security header values."""
        headers = get_security_headers()
        
        assert headers['X-Content-Type-Options'] == 'nosniff'
        assert headers['X-Frame-Options'] == 'DENY'
        assert headers['X-XSS-Protection'] == '1; mode=block'
        assert 'max-age=31536000' in headers['Strict-Transport-Security']
        assert headers['Content-Security-Policy'] == "default-src 'self'"


class TestValidateCorsOrigin:
    """Test cases for CORS origin validation."""

    def test_validate_cors_origin_with_allowed_origins(self):
        """Test CORS validation with configured allowed origins."""
        with patch.dict(os.environ, {'ALLOWED_ORIGINS': 'https://example.com,https://app.example.com'}):
            assert validate_cors_origin('https://example.com') is True
            assert validate_cors_origin('https://app.example.com') is True
            assert validate_cors_origin('https://malicious.com') is False

    def test_validate_cors_origin_localhost_fallback(self):
        """Test CORS validation with localhost fallback."""
        with patch.dict(os.environ, {'ALLOWED_ORIGINS': ''}, clear=True):
            assert validate_cors_origin('http://localhost:3000') is True
            assert validate_cors_origin('http://127.0.0.1:8080') is True
            assert validate_cors_origin('https://malicious.com') is False

    def test_validate_cors_origin_none(self):
        """Test CORS validation with None origin."""
        assert validate_cors_origin(None) is False

    def test_validate_cors_origin_empty_string(self):
        """Test CORS validation with empty string origin."""
        assert validate_cors_origin('') is False


class TestMaskSensitiveData:
    """Test cases for sensitive data masking."""

    def test_mask_email(self):
        """Test email masking."""
        data = {'email': 'user@example.com'}
        masked = mask_sensitive_data(data)
        assert masked['email'] == 'us***om'

    def test_mask_phone(self):
        """Test phone masking."""
        data = {'phone': '+1234567890'}
        masked = mask_sensitive_data(data)
        assert masked['phone'] == '+1***90'

    def test_mask_short_sensitive_field(self):
        """Test masking of short sensitive fields."""
        data = {'password': 'abc'}
        masked = mask_sensitive_data(data)
        assert masked['password'] == '***'

    def test_mask_multiple_fields(self):
        """Test masking multiple sensitive fields."""
        data = {
            'name': 'John Doe',
            'email': 'john@example.com',
            'phone': '+1234567890',
            'id': '12345'
        }
        masked = mask_sensitive_data(data)
        
        assert masked['name'] == 'John Doe'  # Not sensitive
        assert masked['email'] == 'jo***om'
        assert masked['phone'] == '+1***90'
        assert masked['id'] == '12345'  # Not sensitive

    def test_mask_preserves_original_data(self):
        """Test that original data is not modified."""
        original_data = {'email': 'user@example.com'}
        masked = mask_sensitive_data(original_data)
        
        assert original_data['email'] == 'user@example.com'
        assert masked['email'] == 'us***om'


class TestAuditLog:
    """Test cases for audit logging."""

    @patch('utils.security.logger')
    def test_audit_log_basic(self, mock_logger):
        """Test basic audit logging."""
        audit_log('user123', 'login', 'auth', {'ip': '192.168.1.1'})
        
        mock_logger.info.assert_called_once()
        log_call = mock_logger.info.call_args[0][0]
        assert 'user123' in log_call
        assert 'login' in log_call
        assert 'auth' in log_call

    @patch('utils.security.logger')
    def test_audit_log_with_environment(self, mock_logger):
        """Test audit logging includes environment."""
        with patch.dict(os.environ, {'ENVIRONMENT': 'test'}):
            audit_log('user123', 'create', 'users')
            
            log_call = mock_logger.info.call_args[0][0]
            assert 'test' in log_call

    @patch('utils.security.logger')
    def test_audit_log_without_metadata(self, mock_logger):
        """Test audit logging without metadata."""
        audit_log('user123', 'delete', 'users')
        
        mock_logger.info.assert_called_once()
        log_call = mock_logger.info.call_args[0][0]
        assert 'user123' in log_call


class TestSecureConfig:
    """Test cases for SecureConfig class."""

    def test_secure_config_init_without_kms(self):
        """Test SecureConfig initialization without KMS key."""
        with patch.dict(os.environ, {}, clear=True):
            config = SecureConfig()
            assert config.kms_key_id is None

    def test_secure_config_init_with_kms(self):
        """Test SecureConfig initialization with KMS key."""
        with patch.dict(os.environ, {'KMS_KEY_ID': 'test-key-id'}):
            config = SecureConfig()
            assert config.kms_key_id == 'test-key-id'

    @patch('boto3.client')
    def test_encrypt_without_kms_key(self, mock_boto_client):
        """Test encryption without KMS key."""
        with patch.dict(os.environ, {}, clear=True):
            config = SecureConfig()
            result = config.encrypt_sensitive_data('test data')
            assert result == 'test data'

    @patch('boto3.client')
    def test_encrypt_with_kms_key(self, mock_boto_client):
        """Test encryption with KMS key."""
        mock_kms = MagicMock()
        mock_kms.encrypt.return_value = {'CiphertextBlob': b'encrypted_data'}
        mock_boto_client.return_value = mock_kms
        
        with patch.dict(os.environ, {'KMS_KEY_ID': 'test-key-id'}):
            config = SecureConfig()
            result = config.encrypt_sensitive_data('test data')
            
            assert result == 'encrypted_data'.encode().hex()
            mock_kms.encrypt.assert_called_once()

    @patch('boto3.client')
    def test_decrypt_without_kms_key(self, mock_boto_client):
        """Test decryption without KMS key."""
        with patch.dict(os.environ, {}, clear=True):
            config = SecureConfig()
            result = config.decrypt_sensitive_data('test data')
            assert result == 'test data'

    @patch('boto3.client')
    def test_decrypt_with_kms_key(self, mock_boto_client):
        """Test decryption with KMS key."""
        mock_kms = MagicMock()
        mock_kms.decrypt.return_value = {'Plaintext': b'decrypted_data'}
        mock_boto_client.return_value = mock_kms
        
        encrypted_hex = 'encrypted_data'.encode().hex()
        
        with patch.dict(os.environ, {'KMS_KEY_ID': 'test-key-id'}):
            config = SecureConfig()
            result = config.decrypt_sensitive_data(encrypted_hex)
            
            assert result == 'decrypted_data'
            mock_kms.decrypt.assert_called_once()

    @patch('boto3.client')
    def test_encrypt_kms_error(self, mock_boto_client):
        """Test encryption with KMS error."""
        mock_kms = MagicMock()
        mock_kms.encrypt.side_effect = Exception('KMS Error')
        mock_boto_client.return_value = mock_kms
        
        with patch.dict(os.environ, {'KMS_KEY_ID': 'test-key-id'}):
            config = SecureConfig()
            result = config.encrypt_sensitive_data('test data')
            
            assert result is None