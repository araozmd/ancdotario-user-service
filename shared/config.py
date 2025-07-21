import os
import boto3
from typing import Dict, Any, Optional
import json
from botocore.exceptions import ClientError
from pathlib import Path


class ConfigManager:
    """
    Configuration manager that loads values from:
    1. Local .env files (for static config)
    2. AWS Parameter Store (for sensitive/environment-specific config)
    3. Environment variables (fallback)
    """
    
    def __init__(self):
        self.ssm_client = boto3.client('ssm')
        self.cache: Dict[str, Any] = {}
        self.parameter_prefix = os.environ.get('PARAMETER_STORE_PREFIX', '/anecdotario/dev/user-service')
        self.environment = os.environ.get('ENVIRONMENT', 'dev')
        
        # Load local environment configuration
        self._load_local_config()
    
    def _load_local_config(self):
        """Load configuration from local .env files"""
        current_dir = Path(__file__).parent
        
        # Load defaults first
        defaults_file = current_dir / '.env.defaults'
        if defaults_file.exists():
            self._load_env_file(defaults_file)
        
        # Load environment-specific overrides
        env_file = current_dir / f'.env.{self.environment}'
        if env_file.exists():
            self._load_env_file(env_file)
    
    def _load_env_file(self, file_path: Path):
        """Load key-value pairs from an .env file"""
        try:
            with open(file_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        # Store in cache with a special prefix to distinguish from SSM
                        cache_key = f"local:{key.strip()}"
                        self.cache[cache_key] = value.strip()
        except Exception as e:
            # Silently ignore file read errors
            pass
    
    def get_parameter(self, key: str, default: Optional[str] = None, decrypt: bool = False, use_ssm: bool = True) -> str:
        """
        Get a parameter value with priority:
        1. Local .env file (for static config)
        2. AWS Parameter Store (for sensitive/environment-specific config)
        3. Environment variables (fallback)
        
        Args:
            key: Parameter name (without prefix)
            default: Default value if parameter not found
            decrypt: Whether to decrypt SecureString parameters
            use_ssm: Whether to try Parameter Store (default True)
            
        Returns:
            Parameter value as string
        """
        # First check local cache (from .env files)
        local_cache_key = f"local:{key.upper().replace('-', '_')}"
        if local_cache_key in self.cache:
            return self.cache[local_cache_key]
        
        # Then check SSM cache
        ssm_cache_key = f"{self.parameter_prefix}/{key}"
        if ssm_cache_key in self.cache:
            return self.cache[ssm_cache_key]
        
        # Try Parameter Store for sensitive/environment-specific values
        if use_ssm:
            try:
                response = self.ssm_client.get_parameter(
                    Name=ssm_cache_key,
                    WithDecryption=decrypt
                )
                value = response['Parameter']['Value']
                
                # Cache the value
                self.cache[ssm_cache_key] = value
                return value
                
            except ClientError as e:
                error_code = e.response['Error']['Code']
                if error_code != 'ParameterNotFound':
                    # For other AWS errors, continue to fallbacks
                    pass
        
        # Fall back to environment variable
        env_key = key.upper().replace('-', '_')
        env_value = os.environ.get(env_key)
        if env_value is not None:
            # Cache the environment value
            self.cache[ssm_cache_key] = env_value
            return env_value
        
        if default is not None:
            return default
            
        raise ValueError(f"Parameter {key} not found in local config, Parameter Store, or environment variables")
    
    def get_json_parameter(self, key: str, default: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Get a JSON parameter from Parameter Store
        
        Args:
            key: Parameter name (without prefix)
            default: Default dictionary if parameter not found
            
        Returns:
            Parsed JSON as dictionary
        """
        try:
            value = self.get_parameter(key)
            return json.loads(value)
        except (json.JSONDecodeError, ValueError) as e:
            if default is not None:
                return default
            raise e
    
    def get_int_parameter(self, key: str, default: Optional[int] = None) -> int:
        """
        Get an integer parameter from Parameter Store
        
        Args:
            key: Parameter name (without prefix)
            default: Default integer if parameter not found
            
        Returns:
            Parameter value as integer
        """
        try:
            value = self.get_parameter(key)
            return int(value)
        except (ValueError, TypeError) as e:
            if default is not None:
                return default
            raise e
    
    def get_bool_parameter(self, key: str, default: Optional[bool] = None) -> bool:
        """
        Get a boolean parameter from Parameter Store
        
        Args:
            key: Parameter name (without prefix)  
            default: Default boolean if parameter not found
            
        Returns:
            Parameter value as boolean
        """
        try:
            value = self.get_parameter(key).lower()
            return value in ('true', '1', 'yes', 'on')
        except (ValueError, AttributeError) as e:
            if default is not None:
                return default
            raise e
    
    def get_list_parameter(self, key: str, separator: str = ',', default: Optional[list] = None) -> list:
        """
        Get a list parameter from Parameter Store (comma-separated by default)
        
        Args:
            key: Parameter name (without prefix)
            separator: Character to split the value on
            default: Default list if parameter not found
            
        Returns:
            Parameter value as list
        """
        try:
            value = self.get_parameter(key)
            return [item.strip() for item in value.split(separator) if item.strip()]
        except ValueError as e:
            if default is not None:
                return default
            raise e
    
    def get_local_parameter(self, key: str, default: Optional[str] = None) -> str:
        """
        Get a parameter from local .env files only (no SSM lookup)
        
        Args:
            key: Parameter name
            default: Default value if parameter not found
            
        Returns:
            Parameter value as string
        """
        return self.get_parameter(key, default, use_ssm=False)
    
    def get_cognito_parameter(self, key: str, default: Optional[str] = None) -> str:
        """
        Get a Cognito parameter from the centralized path
        /anecdotario/{environment}/cognito/{key}
        
        Args:
            key: Parameter name (e.g., 'user-pool-id', 'region')
            default: Default value if parameter not found
            
        Returns:
            Parameter value as string
        """
        cognito_path = f"/anecdotario/{self.environment}/cognito/{key}"
        
        # Check cache first
        if cognito_path in self.cache:
            return self.cache[cognito_path]
        
        try:
            response = self.ssm_client.get_parameter(
                Name=cognito_path,
                WithDecryption=False
            )
            value = response['Parameter']['Value']
            
            # Cache the value
            self.cache[cognito_path] = value
            return value
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ParameterNotFound':
                if default is not None:
                    return default
                raise ValueError(f"Cognito parameter {cognito_path} not found in Parameter Store")
            else:
                raise e
    
    def get_ssm_parameter(self, key: str, default: Optional[str] = None, decrypt: bool = False) -> str:
        """
        Get a parameter from Parameter Store only (no local file lookup)
        
        Args:
            key: Parameter name (without prefix)
            default: Default value if parameter not found
            decrypt: Whether to decrypt SecureString parameters
            
        Returns:
            Parameter value as string
        """
        # Check SSM cache first
        ssm_cache_key = f"{self.parameter_prefix}/{key}"
        if ssm_cache_key in self.cache:
            return self.cache[ssm_cache_key]
        
        try:
            response = self.ssm_client.get_parameter(
                Name=ssm_cache_key,
                WithDecryption=decrypt
            )
            value = response['Parameter']['Value']
            
            # Cache the value
            self.cache[ssm_cache_key] = value
            return value
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ParameterNotFound':
                if default is not None:
                    return default
                raise ValueError(f"Parameter {ssm_cache_key} not found in Parameter Store")
            else:
                raise e
    
    def refresh_cache(self):
        """Clear the parameter cache to force fresh retrieval"""
        self.cache.clear()
        # Reload local config
        self._load_local_config()
    
    def get_all_parameters(self) -> Dict[str, str]:
        """
        Get all parameters under the prefix path
        
        Returns:
            Dictionary of parameter names (without prefix) to values
        """
        try:
            paginator = self.ssm_client.get_paginator('get_parameters_by_path')
            parameters = {}
            
            for page in paginator.paginate(
                Path=self.parameter_prefix,
                Recursive=True,
                WithDecryption=True
            ):
                for param in page['Parameters']:
                    # Remove prefix from parameter name
                    key = param['Name'][len(self.parameter_prefix):].lstrip('/')
                    parameters[key] = param['Value']
                    
                    # Also cache the parameter
                    self.cache[param['Name']] = param['Value']
            
            return parameters
        except ClientError as e:
            # Fall back to environment variables
            return {}


# Global configuration manager instance
config = ConfigManager()