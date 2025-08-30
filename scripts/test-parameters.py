#!/usr/bin/env python3
"""
Script to test Parameter Store configuration for the user service
Usage: python test-parameters.py <environment> [aws-profile]
"""

import sys
import os
import boto3
from botocore.exceptions import ClientError

def test_parameters(environment='dev', aws_profile='default'):
    """Test that all required parameters are accessible"""
    
    # Set up AWS session with profile
    if aws_profile != 'default':
        session = boto3.Session(profile_name=aws_profile)
        ssm = session.client('ssm')
    else:
        ssm = boto3.client('ssm')
    
    prefix = f"/anecdotario/{environment}/user-service"
    cognito_prefix = f"/anecdotario/{environment}/cognito"
    
    # Required Cognito parameters (centralized)
    required_cognito_params = [
        'user-pool-id',
        'region'
    ]
    
    # Required SSM parameters (environment-specific/sensitive)
    required_ssm_params = []
    
    # Optional SSM parameters (can override local .env files)
    optional_ssm_params = [
        'photo-bucket-name',
        'user-table-name',
        'allowed-origins'
    ]
    
    # Local .env file parameters (static configuration)
    local_env_params = [
        'MAX_IMAGE_SIZE',
        'JWT_TOKEN_EXPIRY_TOLERANCE',
        'USER_NICKNAME_MIN_LENGTH',
        'USER_NICKNAME_MAX_LENGTH',
        'PHOTO_URL_EXPIRY_DAYS',
        'ENABLE_NICKNAME_VALIDATION',
        'USE_COMMONS_SERVICE',
        'ENVIRONMENT'
    ]
    
    print(f"🔍 Testing Parameter Store configuration for environment: {environment}")
    print(f"📍 Parameter prefix: {prefix}")
    print(f"🔐 AWS Profile: {aws_profile}")
    print("-" * 60)
    
    success_count = 0
    error_count = 0
    
    # Test required Cognito parameters
    print("✅ Required Cognito Parameters:")
    for param in required_cognito_params:
        try:
            response = ssm.get_parameter(Name=f"{cognito_prefix}/{param}")
            value = response['Parameter']['Value']
            print(f"  ✓ {param}: {value}")
            success_count += 1
        except ClientError as e:
            if e.response['Error']['Code'] == 'ParameterNotFound':
                print(f"  ❌ {param}: NOT FOUND at {cognito_prefix}/{param}")
                error_count += 1
            else:
                print(f"  ❌ {param}: ERROR - {e}")
                error_count += 1
    
    print()
    
    # Test user service SSM parameters (if any)
    if required_ssm_params:
        print("🔧 User Service Parameters:")
        for param in required_ssm_params:
            try:
                response = ssm.get_parameter(Name=f"{prefix}/{param}")
                value = response['Parameter']['Value']
                print(f"  ✓ {param}: {value}")
                success_count += 1
            except ClientError as e:
                if e.response['Error']['Code'] == 'ParameterNotFound':
                    print(f"  ❌ {param}: NOT FOUND")
                    error_count += 1
                else:
                    print(f"  ❌ {param}: ERROR - {e}")
                    error_count += 1
        print()
    else:
        print("🔧 User Service Parameters: None required (all optional)")
        print()
    
    # Test optional SSM parameters
    print("📋 Optional SSM Parameters:")
    for param in optional_ssm_params:
        try:
            response = ssm.get_parameter(Name=f"{prefix}/{param}")
            value = response['Parameter']['Value']
            print(f"  ✓ {param}: {value}")
            success_count += 1
        except ClientError as e:
            if e.response['Error']['Code'] == 'ParameterNotFound':
                print(f"  ⚠️  {param}: Not set (will use local .env or CloudFormation default)")
            else:
                print(f"  ❌ {param}: ERROR - {e}")
                error_count += 1
    
    print()
    
    # Test local .env files
    print("📄 Local Configuration Files:")
    import os
    from pathlib import Path
    
    # Check if .env files exist
    script_dir = Path(__file__).parent
    project_dir = script_dir.parent / 'photo-upload'
    
    defaults_file = project_dir / '.env.defaults'
    env_file = project_dir / f'.env.{environment}'
    
    if defaults_file.exists():
        print(f"  ✓ .env.defaults: Found")
        # Check some key parameters
        with open(defaults_file, 'r') as f:
            content = f.read()
            found_params = []
            for param in local_env_params[:5]:  # Check first 5
                if param in content:
                    found_params.append(param)
            print(f"    Contains: {', '.join(found_params)}")
        success_count += 1
    else:
        print(f"  ❌ .env.defaults: NOT FOUND")
        error_count += 1
    
    if env_file.exists():
        print(f"  ✓ .env.{environment}: Found")
        success_count += 1
    else:
        print(f"  ⚠️  .env.{environment}: Not found (will use defaults only)")
    
    print()
    
    # Test Parameter Store permissions
    print("🔒 Testing Parameter Store Access:")
    try:
        # Try to list parameters by path
        response = ssm.get_parameters_by_path(
            Path=prefix,
            Recursive=True,
            MaxResults=10
        )
        param_count = len(response['Parameters'])
        print(f"  ✓ Can access Parameter Store ({param_count} parameters found)")
        success_count += 1
    except ClientError as e:
        print(f"  ❌ Parameter Store access failed: {e}")
        error_count += 1
    
    print()
    print("-" * 60)
    
    if error_count == 0:
        print(f"🎉 All tests passed! ({success_count} successful)")
        print("✅ Your Parameter Store configuration is ready")
        return 0
    else:
        print(f"💥 {error_count} errors found, {success_count} successful")
        print("❌ Please fix the missing parameters before deploying")
        return 1

def show_parameter_structure():
    """Show the expected parameter structure"""
    print("""
📋 Configuration Structure:

🔐 AWS Parameter Store (Critical/Environment-specific):

Cognito Configuration (Centralized):
/anecdotario/{environment}/cognito/
├── user-pool-id                  (Required - Cognito User Pool ID)
└── region                        (Required - AWS region for Cognito)

User Service Configuration:
/anecdotario/{environment}/user-service/
├── photo-bucket-name             (Optional - Override S3 bucket name)
├── user-table-name               (Optional - Override DynamoDB table)
└── allowed-origins               (Optional - Override CORS origins)

📄 Local .env Files (Static Configuration):
photo-upload/
├── .env.defaults                 (Base configuration for all environments)
├── .env.dev                      (Development overrides)
├── .env.staging                  (Staging overrides)
└── .env.prod                     (Production overrides)

Local files contain:
- Image processing settings (MAX_IMAGE_SIZE - delegated to commons service)
- Security settings (JWT_TOKEN_EXPIRY_TOLERANCE)
- Application settings (USER_NICKNAME_*, PHOTO_URL_EXPIRY_DAYS)
- Feature flags (ENABLE_NICKNAME_VALIDATION, USE_COMMONS_SERVICE)
- Environment configuration (ENVIRONMENT)

🚀 Setup Commands:
   ./scripts/setup-parameters.sh {environment} [aws-profile]  # SSM only
   
   Local files are already created and committed to git.
   Edit them directly for configuration changes.
""")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test-parameters.py <environment> [aws-profile]")
        print("       python test-parameters.py --help")
        sys.exit(1)
    
    if sys.argv[1] in ['--help', '-h']:
        show_parameter_structure()
        sys.exit(0)
    
    environment = sys.argv[1]
    aws_profile = sys.argv[2] if len(sys.argv) > 2 else 'default'
    
    exit_code = test_parameters(environment, aws_profile)
    sys.exit(exit_code)