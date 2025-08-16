# AWS SAM Pipeline Deployment - Complete Troubleshooting Guide

## Overview
This document captures the comprehensive troubleshooting process for resolving AWS SAM pipeline deployment issues in the anecdotario-user-service project. The issues were systematically identified and resolved through iterative permission fixes.

## Project Context
- **Service**: anecdotario-user-service (Python 3.12 serverless application)
- **Infrastructure**: AWS SAM with CodePipeline/CodeBuild CI/CD
- **Technology Stack**: Python Lambda functions, DynamoDB, S3, API Gateway with JWT auth
- **Deployment**: Multi-environment (dev/staging/prod) with AWS CloudFormation

## Root Cause Analysis
**Critical Issue**: During previous sessions, fixes were applied directly to deployed CloudFormation stacks but weren't reflected in the pipeline source files. When stacks were deleted and recreated, those fixes were lost, causing recurring deployment failures.

## Systematic Problem-Solving Approach

### 1. **SAM Managed Stack Creation Failures**
**Problem**: `aws-sam-cli-managed-default` stack creation failing with ROLLBACK_COMPLETE
**Root Cause**: Missing permissions for SAM CLI to create and manage S3 buckets

**Solutions Applied**:
```yaml
# Added to CodeBuildServiceRole in pipeline-template.yaml
- s3:CreateBucket
- s3:DeleteBucket
- s3:GetBucketLocation
- s3:PutBucketPolicy / DeleteBucketPolicy
- s3:PutBucketTagging / GetBucketTagging
- s3:PutBucketEncryption / GetBucketEncryption
- s3:PutBucketVersioning / GetBucketVersioning
- s3:PutBucketNotification / GetBucketNotification
- s3:PutBucketLifecycleConfiguration / GetBucketLifecycleConfiguration
- s3:PutBucketPublicAccessBlock / GetBucketPublicAccessBlock
- s3:PutBucketCors / GetBucketCors / DeleteBucketCors
- s3:PutBucketAcl / GetBucketAcl
- s3:ListAllMyBuckets / HeadBucket
```

### 2. **CloudFormation Permission Issues**
**Problem**: Stack operations failing due to insufficient CloudFormation permissions
**Solutions Added**:
```yaml
- cloudformation:ListStacks
- cloudformation:TagResource / UntagResource
- cloudformation:ListTagsForResource
- cloudformation:GetStackPolicy / SetStackPolicy
```

### 3. **CloudWatch Logs Permission Issues**
**Problem**: SAM managed resources requiring CloudWatch Logs operations
**Solutions Added**:
```yaml
- logs:CreateLogGroup / CreateLogStream / PutLogEvents
- logs:DescribeLogGroups / DescribeLogStreams
- logs:DeleteLogGroup / PutRetentionPolicy
```

### 4. **SAM Configuration Conflicts**
**Problem**: `Cannot use both --resolve-s3 and --s3-bucket parameters`
**Solution**: 
- Removed `resolve_s3 = true` from samconfig files
- Used explicit `s3_bucket` parameters instead
- Created predefined S3 buckets in build process

### 5. **Application S3 Bucket Permission Issues**
**Critical Discovery**: Multiple missing permissions for application-specific S3 buckets

**Missing Permissions Found Iteratively**:
1. **s3:PutBucketTagging** - For bucket tagging during creation
2. **s3:PutEncryptionConfiguration** - For bucket encryption setup  
3. **s3:PutLifecycleConfiguration** - For bucket lifecycle rules

## Complete Permission Set (Final Solution)

### CodeBuild Service Role Permissions
```yaml
# S3 permissions for SAM managed buckets
- Effect: Allow
  Action:
    - s3:CreateBucket / DeleteBucket / GetBucketLocation
    - s3:GetBucketPolicy / PutBucketPolicy / DeleteBucketPolicy
    - s3:PutBucketTagging / GetBucketTagging
    - s3:PutBucketEncryption / GetBucketEncryption
    - s3:PutBucketVersioning / GetBucketVersioning
    - s3:PutBucketNotification / GetBucketNotification
    - s3:PutBucketLifecycleConfiguration / GetBucketLifecycleConfiguration
    - s3:PutBucketPublicAccessBlock / GetBucketPublicAccessBlock
    - s3:PutBucketCors / GetBucketCors / DeleteBucketCors
    - s3:PutBucketAcl / GetBucketAcl
    - s3:GetObject / PutObject / DeleteObject / ListBucket
    - s3:GetObjectVersion / DeleteObjectVersion
    - s3:GetObjectAcl / PutObjectAcl
  Resource: 
    - "arn:aws:s3:::aws-sam-cli-managed-default*"
    - "arn:aws:s3:::aws-sam-cli-managed-default*/*"
    - "arn:aws:s3:::aws-sam-cli-sourcebucket-*"
    - "arn:aws:s3:::aws-sam-cli-sourcebucket-*/*"
    - "arn:aws:s3:::anecdotario-sam-artifacts-*"
    - "arn:aws:s3:::anecdotario-sam-artifacts-*/*"

# S3 permissions for application buckets (CRITICAL!)
- Effect: Allow
  Action:
    - s3:CreateBucket / DeleteBucket / GetBucketLocation
    - s3:PutBucketTagging / GetBucketTagging
    - s3:PutBucketEncryption / GetBucketEncryption
    - s3:PutEncryptionConfiguration / GetEncryptionConfiguration  # CRITICAL
    - s3:PutBucketLifecycleConfiguration / GetBucketLifecycleConfiguration
    - s3:PutLifecycleConfiguration / GetLifecycleConfiguration    # CRITICAL
    - [... all other bucket operations]
  Resource: 
    - "arn:aws:s3:::user-service-*"
    - "arn:aws:s3:::user-service-*/*"

# Broad S3 permissions
- Effect: Allow
  Action:
    - s3:ListAllMyBuckets / HeadBucket
  Resource: "*"

# CloudFormation permissions
- Effect: Allow
  Action:
    - cloudformation:CreateStack / UpdateStack / DeleteStack
    - cloudformation:DescribeStacks / DescribeStackEvents / DescribeStackResources
    - cloudformation:GetTemplate / GetTemplateSummary
    - cloudformation:CreateChangeSet / DescribeChangeSet / ExecuteChangeSet / DeleteChangeSet
    - cloudformation:ListStackResources / ValidateTemplate
    - cloudformation:ListStacks / TagResource / UntagResource
    - cloudformation:ListTagsForResource / GetStackPolicy / SetStackPolicy
  Resource: 
    - "arn:aws:cloudformation:${AWS::Region}:${AWS::AccountId}:stack/user-service-*/*"
    - "arn:aws:cloudformation:${AWS::Region}:${AWS::AccountId}:stack/aws-sam-cli-managed-*/*"

# CloudWatch Logs permissions
- Effect: Allow
  Action:
    - logs:CreateLogGroup / CreateLogStream / PutLogEvents
    - logs:DescribeLogGroups / DescribeLogStreams
    - logs:DeleteLogGroup / PutRetentionPolicy
  Resource: "*"

# Cognito permissions (for JWT authorizers)
- Effect: Allow
  Action:
    - cognito-idp:DescribeUserPool / GetUserPool / ListUserPools
  Resource: "*"
```

## SAM Configuration Best Practices

### Environment-Specific S3 Buckets
```toml
# samconfig-dev.toml
[default.deploy.parameters]
capabilities = "CAPABILITY_IAM"
confirm_changeset = false
fail_on_empty_changeset = false
region = "us-east-1"
s3_bucket = "anecdotario-sam-artifacts-us-east-1"  # Predefined bucket
# NOTE: Do NOT use resolve_s3 = true with explicit s3_bucket
```

### Build Process S3 Bucket Creation
```yaml
# buildspec.yml - Pre-build phase
- |
  # Create SAM artifact buckets for each environment if they don't exist
  BUCKETS=(
    "anecdotario-sam-artifacts-us-east-1"
    "anecdotario-sam-artifacts-staging-us-east-1"
    "anecdotario-sam-artifacts-prod-us-east-1"
  )
  
  for bucket in "${BUCKETS[@]}"; do
    if aws s3 ls "s3://$bucket" 2>&1 | grep -q 'NoSuchBucket\|does not exist'; then
      aws s3 mb "s3://$bucket" --region us-east-1
      aws s3api put-bucket-encryption --bucket "$bucket" [...]
      aws s3api put-bucket-versioning --bucket "$bucket" [...]
    fi
  done
```

## Troubleshooting Methodology

### 1. **Systematic Permission Discovery**
When deployment fails:
1. Check CloudFormation events: `aws cloudformation describe-stack-events --stack-name <stack>`
2. Look for `CREATE_FAILED` resources with permission errors
3. Add missing permissions to pipeline template
4. Commit, push, and recreate pipeline stack

### 2. **Stack Management Process**
```bash
# 1. Stop current pipeline execution
aws codepipeline stop-pipeline-execution --pipeline-name <name> --pipeline-execution-id <id> --abandon

# 2. Delete failed application stacks
aws cloudformation delete-stack --stack-name user-service-dev

# 3. Delete pipeline stack (cleans S3 artifacts bucket first)
aws s3 rb s3://<artifacts-bucket> --force
aws cloudformation delete-stack --stack-name <pipeline-stack>

# 4. Recreate with updated permissions
./deploy-pipeline.sh <github-token>
```

### 3. **Key Learning: Direct vs Source Fixes**
**CRITICAL**: Always apply fixes to source files, not directly to deployed stacks. Direct stack fixes are lost when stacks are recreated.

## Architecture Patterns

### Multi-Environment Setup
```
anecdotario-user-service/
├── pipeline/
│   ├── pipeline-template.yaml      # Complete permissions
│   ├── buildspec.yml              # S3 bucket creation
│   └── deploy-*-buildspec.yml     # Environment-specific deploys
├── samconfig-dev.toml             # Dev environment config
├── samconfig-staging.toml         # Staging environment config
├── samconfig-prod.toml            # Prod environment config
└── template.yaml                  # SAM application template
```

### Environment Parameter Mapping
```yaml
# Handle environment name differences
Conditions:
  IsDevEnvironment: !Equals [!Ref Environment, dev]
  IsProdEnvironment: !Equals [!Ref Environment, prod]

# Map dev -> development, prod -> production for SSM parameters
EnvironmentName: !If 
  - IsDevEnvironment
  - development
  - !If 
    - IsProdEnvironment
    - production
    - !Ref Environment
```

## Common Error Patterns & Solutions

| Error Pattern | Root Cause | Solution |
|---------------|------------|----------|
| `ROLLBACK_COMPLETE` in `aws-sam-cli-managed-default` | Missing SAM managed bucket permissions | Add comprehensive S3 permissions |
| `Cannot use both --resolve-s3 and --s3-bucket` | SAM config conflict | Remove `resolve_s3`, use explicit `s3_bucket` |
| `not authorized to perform: s3:PutBucketTagging` | Missing application bucket permissions | Add to user-service bucket permissions |
| `not authorized to perform: s3:PutEncryptionConfiguration` | Missing encryption permissions | Add encryption config permissions |
| `not authorized to perform: s3:PutLifecycleConfiguration` | Missing lifecycle permissions | Add lifecycle config permissions |

## Future Project Recommendations

### 1. **Start with Comprehensive Permissions**
Use the complete permission set from this guide as a starting template for new SAM projects.

### 2. **Use Predefined S3 Buckets**
Avoid SAM managed stack creation issues by using predefined, environment-specific S3 buckets.

### 3. **Implement Systematic Testing**
- Test pipeline deployment from scratch in clean environment
- Use the delete-all -> recreate approach to verify fixes

### 4. **Version Control All Fixes**
- Never apply fixes directly to deployed stacks
- Always commit infrastructure changes to source control
- Document permission additions with clear commit messages

### 5. **Monitor CloudFormation Events**
Set up monitoring for CloudFormation stack failures to catch permission issues early.

## Key Learnings

1. **Permission Accumulation**: Each deployment failure revealed additional required permissions that weren't obvious from documentation
2. **Iteration Pattern**: The most effective approach was: stop pipeline → delete stacks → add permissions → commit → recreate pipeline
3. **Documentation Value**: Capturing these fixes prevents future teams from repeating the same discovery process
4. **Comprehensive Testing**: Full end-to-end pipeline tests reveal permission gaps that local testing misses

### OpenAPI Integration Lessons (Final Resolution)

5. **SAM Template vs OpenAPI File Compatibility**:
   - AWS SAM's `DefinitionUri` approach for external OpenAPI files has significant limitations
   - **CORS**: Compatible with both SAM template (`Cors:` property) and OpenAPI file (`x-amazon-apigateway-cors`)
   - **Authentication**: **ONLY works reliably with SAM template inline definition** (`Auth:` property)
   - Critical Error: `"Auth works only with inline Swagger specified in 'DefinitionBody' property"`

6. **API Documentation Strategy - Final Approach**:
   - Created comprehensive OpenAPI 3.0.1 specification (`openapi.yaml`) for complete API documentation
   - **Reverted to SAM template Auth/CORS configuration** for functional deployment reliability
   - OpenAPI file maintained as standalone reference documentation (not used in deployment)
   - **Successful deployment achieved** with traditional SAM template approach

7. **Deployment vs Documentation Trade-offs**:
   - **Functional API deployment takes precedence** over auto-generated documentation integration
   - SAM template provides more reliable Auth + CORS configuration than DefinitionUri approach
   - **Alternative recommendation**: Host API documentation separately (S3 static site, documentation platforms)
   - **Final pipeline deployment: SUCCESSFUL** after reverting OpenAPI integration attempts

---

**Key Takeaway**: AWS SAM pipeline deployments require extensive permissions across S3, CloudFormation, CloudWatch Logs, and service-specific resources. The most reliable approach is to start with comprehensive permissions and systematically test deployment from clean environments. For API documentation, maintain OpenAPI specifications as standalone files rather than attempting complex SAM integration when Auth/CORS reliability is critical.