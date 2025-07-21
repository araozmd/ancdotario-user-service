"""Input validation and sanitization utilities."""

import re
from typing import Any, Dict, Optional
from pydantic import BaseModel, EmailStr, Field, validator
import logging

logger = logging.getLogger(__name__)


class CreateUserRequest(BaseModel):
    """Request model for creating a user."""
    
    name: str = Field(..., min_length=1, max_length=100, description="User's display name")
    email: EmailStr = Field(..., description="User's email address")
    profile_image: Optional[str] = Field(None, max_length=500, description="Profile image URL")
    
    @validator('name')
    def validate_name(cls, v: str) -> str:
        """Validate and sanitize name."""
        # Remove potential XSS characters
        sanitized = re.sub(r'[<>"\'\&]', '', v.strip())
        if not sanitized:
            raise ValueError("Name cannot be empty after sanitization")
        return sanitized
    
    @validator('profile_image')
    def validate_profile_image(cls, v: Optional[str]) -> Optional[str]:
        """Validate profile image URL."""
        if v is None:
            return v
        
        # Basic URL validation
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
            r'localhost|'  # localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        
        if not url_pattern.match(v):
            raise ValueError("Invalid URL format for profile image")
        
        return v


class UpdateUserRequest(BaseModel):
    """Request model for updating a user."""
    
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    profile_image: Optional[str] = Field(None, max_length=500)
    is_certified: Optional[bool] = Field(None)
    
    @validator('name')
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        """Validate and sanitize name."""
        if v is None:
            return v
        sanitized = re.sub(r'[<>"\'\&]', '', v.strip())
        if not sanitized:
            raise ValueError("Name cannot be empty after sanitization")
        return sanitized
    
    @validator('profile_image')
    def validate_profile_image(cls, v: Optional[str]) -> Optional[str]:
        """Validate profile image URL."""
        if v is None:
            return v
        
        url_pattern = re.compile(
            r'^https?://'
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'
            r'localhost|'
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
            r'(?::\d+)?'
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        
        if not url_pattern.match(v):
            raise ValueError("Invalid URL format for profile image")
        
        return v


def validate_user_id(user_id: str) -> str:
    """Validate user ID format."""
    # Basic UUID validation pattern
    uuid_pattern = re.compile(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
        re.IGNORECASE
    )
    
    if not uuid_pattern.match(user_id):
        raise ValueError("Invalid user ID format")
    
    return user_id


def sanitize_query_params(query_params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Sanitize query parameters."""
    if not query_params:
        return {}
    
    sanitized = {}
    allowed_params = {'limit', 'offset', 'sort', 'filter', 'certified'}
    
    for key, value in query_params.items():
        if key not in allowed_params:
            logger.warning(f"Ignoring unknown query parameter: {key}")
            continue
        
        # Sanitize string values
        if isinstance(value, str):
            sanitized_value = re.sub(r'[<>"\'\&]', '', value.strip())
            if sanitized_value:
                sanitized[key] = sanitized_value
        elif isinstance(value, (int, bool)):
            sanitized[key] = value
    
    return sanitized


def validate_request_size(body: str, max_size: int = 1024 * 10) -> None:
    """Validate request body size."""
    if len(body.encode('utf-8')) > max_size:
        raise ValueError(f"Request body too large. Maximum size: {max_size} bytes")


def validate_content_type(headers: Dict[str, str], expected: str = 'application/json') -> None:
    """Validate Content-Type header."""
    content_type = headers.get('Content-Type', '').lower()
    if expected.lower() not in content_type:
        raise ValueError(f"Invalid Content-Type. Expected: {expected}")