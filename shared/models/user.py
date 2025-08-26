import os
from datetime import datetime
from pynamodb.models import Model
from pynamodb.attributes import UnicodeAttribute, UTCDateTimeAttribute
from pynamodb.indexes import GlobalSecondaryIndex, AllProjection


class NicknameIndex(GlobalSecondaryIndex):
    """
    Global secondary index for case-insensitive nickname lookups
    Uses normalized (lowercase) nickname for uniqueness checking
    """
    class Meta:
        index_name = 'nickname-index'
        projection = AllProjection()
        # No capacity units needed for on-demand billing mode
    
    nickname_normalized = UnicodeAttribute(hash_key=True)


class User(Model):
    """
    User model for storing minimal user data
    Primary data is in Cognito, this table stores searchable fields and image URLs
    """
    class Meta:
        table_name = os.environ.get('USER_TABLE_NAME', 'Users-dev')
        region = os.environ.get('AWS_REGION', 'us-east-1')
        billing_mode = 'PAY_PER_REQUEST'
    
    # Primary key - Cognito user ID (sub)
    cognito_id = UnicodeAttribute(hash_key=True)
    
    # Display nickname (original case preserved)
    nickname = UnicodeAttribute()
    
    # Normalized nickname for uniqueness checking (lowercase)
    nickname_normalized = UnicodeAttribute()
    
    # S3 URLs and keys for profile images (multiple versions)
    image_url = UnicodeAttribute(null=True)              # Legacy field for backward compatibility
    thumbnail_url = UnicodeAttribute(null=True)          # Small thumbnail (150x150) - public URL
    standard_s3_key = UnicodeAttribute(null=True)        # Standard size (320x320) - S3 key for presigned URL
    high_res_s3_key = UnicodeAttribute(null=True)        # High resolution (800x800) - S3 key for presigned URL
    
    # Timestamps
    created_at = UTCDateTimeAttribute(default=datetime.utcnow)
    updated_at = UTCDateTimeAttribute(default=datetime.utcnow)
    
    # Global secondary index
    nickname_index = NicknameIndex()
    
    def save(self, **kwargs):
        """Override save to update timestamp and normalize nickname"""
        self.updated_at = datetime.utcnow()
        # Ensure nickname is normalized for uniqueness checking
        if hasattr(self, 'nickname') and self.nickname:
            self.nickname_normalized = self.nickname.lower()
        super().save(**kwargs)
    
    @classmethod
    def get_by_nickname(cls, nickname):
        """Get user by nickname using GSI (case-insensitive)"""
        try:
            # Normalize the search nickname for case-insensitive matching
            normalized_nickname = nickname.lower()
            results = list(cls.nickname_index.query(normalized_nickname))
            return results[0] if results else None
        except Exception:
            return None
    
    def to_dict(self, include_presigned_urls=False, s3_client=None):
        """
        Convert model to dictionary for API responses
        
        Args:
            include_presigned_urls: If True, generate presigned URLs for protected images
            s3_client: boto3 S3 client instance (required if include_presigned_urls is True)
        """
        # Build images object with available versions
        images = {}
        if self.thumbnail_url:
            images['thumbnail'] = self.thumbnail_url
            
        # Generate presigned URLs for standard and high-res if requested
        if include_presigned_urls and s3_client:
            if self.standard_s3_key:
                try:
                    images['standard'] = s3_client.generate_presigned_url(
                        'get_object',
                        Params={
                            'Bucket': os.environ.get('PHOTO_BUCKET_NAME'),
                            'Key': self.standard_s3_key
                        },
                        ExpiresIn=604800  # 7 days
                    )
                except Exception:
                    pass  # Silently fail if can't generate URL
                    
            if self.high_res_s3_key:
                try:
                    images['high_res'] = s3_client.generate_presigned_url(
                        'get_object',
                        Params={
                            'Bucket': os.environ.get('PHOTO_BUCKET_NAME'),
                            'Key': self.high_res_s3_key
                        },
                        ExpiresIn=604800  # 7 days
                    )
                except Exception:
                    pass  # Silently fail if can't generate URL
        
        # Fallback to legacy image_url if no new versions exist
        if not images and self.image_url:
            images['standard'] = self.image_url
        
        return {
            'cognito_id': self.cognito_id,
            'nickname': self.nickname,
            'images': images if images else None,
            'image_url': self.image_url,  # Keep for backward compatibility
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }