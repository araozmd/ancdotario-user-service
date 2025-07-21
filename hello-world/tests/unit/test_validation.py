"""Tests for validation utilities."""

import pytest
from pydantic import ValidationError

from utils.validation import (
    CreateUserRequest,
    UpdateUserRequest,
    validate_user_id,
    sanitize_query_params,
    validate_request_size,
    validate_content_type,
)


class TestCreateUserRequest:
    """Test cases for CreateUserRequest validation."""

    def test_valid_create_user_request(self):
        """Test valid user creation request."""
        data = {
            "name": "John Doe",
            "email": "john@example.com",
            "profile_image": "https://example.com/profile.jpg"
        }
        request = CreateUserRequest(**data)
        assert request.name == "John Doe"
        assert request.email == "john@example.com"
        assert request.profile_image == "https://example.com/profile.jpg"

    def test_create_user_request_without_profile_image(self):
        """Test user creation without profile image."""
        data = {
            "name": "Jane Doe",
            "email": "jane@example.com"
        }
        request = CreateUserRequest(**data)
        assert request.name == "Jane Doe"
        assert request.email == "jane@example.com"
        assert request.profile_image is None

    def test_create_user_request_sanitizes_name(self):
        """Test that name is sanitized."""
        data = {
            "name": "John<script>alert('xss')</script>Doe",
            "email": "john@example.com"
        }
        request = CreateUserRequest(**data)
        assert request.name == "JohnDoe"  # XSS characters removed

    def test_create_user_request_invalid_email(self):
        """Test invalid email validation."""
        data = {
            "name": "John Doe",
            "email": "invalid-email"
        }
        with pytest.raises(ValidationError):
            CreateUserRequest(**data)

    def test_create_user_request_empty_name(self):
        """Test empty name validation."""
        data = {
            "name": "",
            "email": "john@example.com"
        }
        with pytest.raises(ValidationError):
            CreateUserRequest(**data)

    def test_create_user_request_invalid_url(self):
        """Test invalid profile image URL."""
        data = {
            "name": "John Doe",
            "email": "john@example.com",
            "profile_image": "not-a-url"
        }
        with pytest.raises(ValidationError):
            CreateUserRequest(**data)

    def test_create_user_request_name_too_long(self):
        """Test name that exceeds maximum length."""
        data = {
            "name": "a" * 101,  # Exceeds 100 character limit
            "email": "john@example.com"
        }
        with pytest.raises(ValidationError):
            CreateUserRequest(**data)


class TestUpdateUserRequest:
    """Test cases for UpdateUserRequest validation."""

    def test_valid_update_user_request(self):
        """Test valid user update request."""
        data = {
            "name": "Updated Name",
            "is_certified": True
        }
        request = UpdateUserRequest(**data)
        assert request.name == "Updated Name"
        assert request.is_certified is True
        assert request.profile_image is None

    def test_update_user_request_all_none(self):
        """Test update request with all None values."""
        request = UpdateUserRequest()
        assert request.name is None
        assert request.profile_image is None
        assert request.is_certified is None


class TestValidateUserId:
    """Test cases for user ID validation."""

    def test_valid_uuid(self):
        """Test valid UUID format."""
        valid_uuid = "550e8400-e29b-41d4-a716-446655440000"
        result = validate_user_id(valid_uuid)
        assert result == valid_uuid

    def test_invalid_uuid_format(self):
        """Test invalid UUID format."""
        with pytest.raises(ValueError, match="Invalid user ID format"):
            validate_user_id("not-a-uuid")

    def test_empty_user_id(self):
        """Test empty user ID."""
        with pytest.raises(ValueError, match="Invalid user ID format"):
            validate_user_id("")


class TestSanitizeQueryParams:
    """Test cases for query parameter sanitization."""

    def test_sanitize_valid_params(self):
        """Test sanitization of valid parameters."""
        params = {
            "limit": "10",
            "offset": "20",
            "certified": "true"
        }
        result = sanitize_query_params(params)
        assert result == {"limit": "10", "offset": "20", "certified": "true"}

    def test_sanitize_removes_unknown_params(self):
        """Test that unknown parameters are removed."""
        params = {
            "limit": "10",
            "unknown_param": "value",
            "malicious": "<script>alert('xss')</script>"
        }
        result = sanitize_query_params(params)
        assert result == {"limit": "10"}

    def test_sanitize_none_params(self):
        """Test sanitization with None input."""
        result = sanitize_query_params(None)
        assert result == {}

    def test_sanitize_empty_params(self):
        """Test sanitization with empty dict."""
        result = sanitize_query_params({})
        assert result == {}

    def test_sanitize_removes_xss_characters(self):
        """Test that XSS characters are removed."""
        params = {
            "filter": "name<script>alert('xss')</script>test"
        }
        result = sanitize_query_params(params)
        assert result == {"filter": "nametesttest"}


class TestValidateRequestSize:
    """Test cases for request size validation."""

    def test_valid_request_size(self):
        """Test request within size limit."""
        small_body = "small request"
        # Should not raise an exception
        validate_request_size(small_body)

    def test_request_too_large(self):
        """Test request exceeding size limit."""
        large_body = "x" * 20000  # Exceeds default 10KB limit
        with pytest.raises(ValueError, match="Request body too large"):
            validate_request_size(large_body)

    def test_custom_size_limit(self):
        """Test with custom size limit."""
        body = "x" * 100
        with pytest.raises(ValueError, match="Request body too large"):
            validate_request_size(body, max_size=50)


class TestValidateContentType:
    """Test cases for content type validation."""

    def test_valid_content_type(self):
        """Test valid content type."""
        headers = {"Content-Type": "application/json"}
        # Should not raise an exception
        validate_content_type(headers)

    def test_valid_content_type_with_charset(self):
        """Test valid content type with charset."""
        headers = {"Content-Type": "application/json; charset=utf-8"}
        # Should not raise an exception
        validate_content_type(headers)

    def test_invalid_content_type(self):
        """Test invalid content type."""
        headers = {"Content-Type": "text/plain"}
        with pytest.raises(ValueError, match="Invalid Content-Type"):
            validate_content_type(headers)

    def test_missing_content_type(self):
        """Test missing content type header."""
        headers = {}
        with pytest.raises(ValueError, match="Invalid Content-Type"):
            validate_content_type(headers)

    def test_case_insensitive_content_type(self):
        """Test case insensitive content type validation."""
        headers = {"Content-Type": "APPLICATION/JSON"}
        # Should not raise an exception
        validate_content_type(headers)