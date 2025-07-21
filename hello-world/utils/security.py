"""Security utilities for the user service."""

import os
import json
import boto3
from typing import Dict, Any, Optional
import logging
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class SecureConfig:
    """Secure configuration manager with encryption support."""
    
    def __init__(self):
        self.kms_client = boto3.client('kms')
        self.kms_key_id = os.environ.get('KMS_KEY_ID')
    
    def encrypt_sensitive_data(self, data: str) -> Optional[str]:
        """Encrypt sensitive data using KMS."""
        if not self.kms_key_id:
            logger.warning("KMS_KEY_ID not configured, skipping encryption")
            return data
        
        try:
            response = self.kms_client.encrypt(
                KeyId=self.kms_key_id,
                Plaintext=data.encode('utf-8')
            )
            return response['CiphertextBlob'].hex()
        except ClientError as e:
            logger.error(f"Failed to encrypt data: {e}")
            return None
    
    def decrypt_sensitive_data(self, encrypted_data: str) -> Optional[str]:
        """Decrypt sensitive data using KMS."""
        if not self.kms_key_id:
            logger.warning("KMS_KEY_ID not configured, returning data as-is")
            return encrypted_data
        
        try:
            ciphertext_blob = bytes.fromhex(encrypted_data)
            response = self.kms_client.decrypt(CiphertextBlob=ciphertext_blob)
            return response['Plaintext'].decode('utf-8')
        except (ClientError, ValueError) as e:
            logger.error(f"Failed to decrypt data: {e}")
            return None


def get_security_headers() -> Dict[str, str]:
    """Generate security headers for HTTP responses."""
    return {
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'DENY',
        'X-XSS-Protection': '1; mode=block',
        'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
        'Content-Security-Policy': "default-src 'self'",
        'Referrer-Policy': 'strict-origin-when-cross-origin',
    }


def validate_api_key(headers: Dict[str, str]) -> bool:
    """Validate API key from headers (placeholder for future implementation)."""
    api_key = headers.get('X-API-Key')
    if not api_key:
        return False
    
    # TODO: Implement actual API key validation
    # This could involve checking against DynamoDB, parameter store, etc.
    logger.info("API key validation not implemented yet")
    return True


def rate_limit_check(user_id: str, action: str) -> bool:
    """Check rate limits for user actions (placeholder for future implementation)."""
    # TODO: Implement rate limiting using DynamoDB or ElastiCache
    logger.info(f"Rate limit check for user {user_id}, action {action}")
    return True


def audit_log(user_id: str, action: str, resource: str, metadata: Optional[Dict[str, Any]] = None) -> None:
    """Log security-relevant events for auditing."""
    audit_entry = {
        'timestamp': str(int(os.times().user * 1000)),  # Current timestamp
        'user_id': user_id,
        'action': action,
        'resource': resource,
        'environment': os.environ.get('ENVIRONMENT', 'unknown'),
        'metadata': metadata or {}
    }
    
    # In production, this should go to CloudWatch Logs, CloudTrail, or security SIEM
    logger.info(f"AUDIT: {json.dumps(audit_entry)}")


def mask_sensitive_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Mask sensitive data in logs and responses."""
    sensitive_fields = {'email', 'phone', 'ssn', 'password', 'token'}
    masked_data = data.copy()
    
    for key, value in masked_data.items():
        if key.lower() in sensitive_fields:
            if isinstance(value, str) and len(value) > 4:
                masked_data[key] = f"{value[:2]}***{value[-2:]}"
            else:
                masked_data[key] = "***"
    
    return masked_data


def validate_cors_origin(origin: Optional[str]) -> bool:
    """Validate CORS origin against allowed domains."""
    if not origin:
        return False
    
    # Get allowed origins from environment
    allowed_origins = os.environ.get('ALLOWED_ORIGINS', '').split(',')
    allowed_origins = [origin.strip() for origin in allowed_origins if origin.strip()]
    
    if not allowed_origins:
        # If no origins configured, allow localhost for development
        return 'localhost' in origin or '127.0.0.1' in origin
    
    return origin in allowed_origins