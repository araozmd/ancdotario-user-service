# CI/CD Setup Instructions

## Option 1: GitHub Actions (Recommended)

### Prerequisites
- GitHub repository
- AWS account with appropriate permissions
- AWS CLI configured

### Setup Steps

1. **Configure GitHub Secrets**
   ```bash
   # In your GitHub repo: Settings -> Secrets and Variables -> Actions
   # Add these repository secrets:
   ```
   - `AWS_ACCESS_KEY_ID`: Your AWS access key
   - `AWS_SECRET_ACCESS_KEY`: Your AWS secret key
   - `AWS_ACCESS_KEY_ID_PROD`: Production AWS access key (if different)
   - `AWS_SECRET_ACCESS_KEY_PROD`: Production AWS secret key (if different)

2. **Create GitHub Environments**
   ```bash
   # Go to Settings -> Environments
   # Create three environments:
   # - development (no protection rules)
   # - staging (no protection rules)  
   # - production (require reviewers, restrict to main branch)
   ```

3. **Deploy**
   The workflow will automatically trigger on:
   - Push to main branch (deploys to all environments)
   - Pull requests (runs tests only)

### Workflow Features
- ✅ Automated testing for all Lambda functions
- ✅ Multi-environment deployment (dev → staging → prod)
- ✅ Code coverage reporting
- ✅ Manual approval for production
- ✅ Rollback capabilities

## Option 2: AWS CodePipeline

### Setup Steps

1. **Create GitHub Personal Access Token**
   ```bash
   # Go to GitHub Settings -> Developer settings -> Personal access tokens
   # Create token with 'repo' and 'admin:repo_hook' permissions
   ```

2. **Deploy Pipeline Infrastructure**
   ```bash
   aws cloudformation create-stack \
     --stack-name user-service-pipeline \
     --template-body file://pipeline/pipeline-template.yaml \
     --parameters ParameterKey=GitHubToken,ParameterValue=YOUR_GITHUB_TOKEN \
     --capabilities CAPABILITY_IAM \
     --region us-east-1
   ```

3. **Monitor Deployment**
   ```bash
   aws cloudformation describe-stacks \
     --stack-name user-service-pipeline \
     --query 'Stacks[0].StackStatus'
   ```

### Pipeline Features
- ✅ Automated build and test
- ✅ Multi-stage deployment
- ✅ Manual approval for production
- ✅ Integration with AWS services
- ✅ S3 artifact storage with lifecycle

## Option 3: SAM Pipelines

### Quick Setup
```bash
# In your SAM project root
sam pipeline init --bootstrap

# Follow the prompts:
# 1. Choose "AWS Quick Start Pipeline Templates"
# 2. Select "GitHub Actions"
# 3. Configure your environments (dev, staging, prod)
# 4. Provide AWS account details for each environment
```

This will:
- Create `.github/workflows/pipeline.yaml`
- Bootstrap necessary IAM roles and S3 buckets
- Configure environment-specific settings

## Required AWS Permissions

### For GitHub Actions
Your AWS user/role needs:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "cloudformation:*",
        "lambda:*",
        "apigateway:*",
        "dynamodb:*",
        "s3:*",
        "ssm:*",
        "iam:*",
        "logs:*"
      ],
      "Resource": "*"
    }
  ]
}
```

### Environment-Specific Configuration

#### Development
```bash
# Automatic deployment on every commit to main
# No manual approval required
# Resource prefix: user-service-dev
```

#### Staging  
```bash
# Deploys after successful dev deployment
# Optional integration tests
# Resource prefix: user-service-staging
```

#### Production
```bash
# Requires manual approval
# Deploys after successful staging deployment
# Resource prefix: user-service-prod
```

## Monitoring and Troubleshooting

### GitHub Actions
```bash
# View workflow runs in GitHub
# https://github.com/YOUR_USERNAME/YOUR_REPO/actions

# Check SAM logs
sam logs -n PhotoUploadFunction --stack-name user-service-dev --tail
```

### AWS CodePipeline
```bash
# View pipeline in AWS Console
# https://console.aws.amazon.com/codesuite/codepipeline/

# Check CloudFormation stacks
aws cloudformation describe-stacks --stack-name user-service-dev
```

## Best Practices

1. **Environment Isolation**
   - Use separate AWS accounts for prod
   - Different parameter store paths per environment
   - Isolated S3 buckets and DynamoDB tables

2. **Security**
   - Use IAM roles instead of access keys when possible
   - Enable AWS CloudTrail for audit logging
   - Rotate access keys regularly

3. **Testing**
   - Run unit tests before deployment
   - Add integration tests for staging
   - Monitor deployment health with CloudWatch

4. **Rollback Strategy**
   - Keep previous Lambda versions
   - Use CloudFormation change sets for review
   - Monitor error rates after deployment