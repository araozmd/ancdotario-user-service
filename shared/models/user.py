import os
from datetime import datetime
from pynamodb.models import Model
from pynamodb.attributes import UnicodeAttribute, UTCDateTimeAttribute
from pynamodb.indexes import GlobalSecondaryIndex, AllProjection


class NicknameIndex(GlobalSecondaryIndex):
    """
    Global secondary index for nickname lookups
    """
    class Meta:
        index_name = 'nickname-index'
        projection = AllProjection()
        # No capacity units needed for on-demand billing mode
    
    nickname = UnicodeAttribute(hash_key=True)


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
    
    # Searchable nickname (unique)
    nickname = UnicodeAttribute()
    
    # S3 URL for profile image
    image_url = UnicodeAttribute(null=True)
    
    # Timestamps
    created_at = UTCDateTimeAttribute(default=datetime.utcnow)
    updated_at = UTCDateTimeAttribute(default=datetime.utcnow)
    
    # Global secondary index
    nickname_index = NicknameIndex()
    
    def save(self, **kwargs):
        """Override save to update timestamp"""
        self.updated_at = datetime.utcnow()
        super().save(**kwargs)
    
    @classmethod
    def get_by_nickname(cls, nickname):
        """Get user by nickname using GSI"""
        try:
            results = list(cls.nickname_index.query(nickname))
            return results[0] if results else None
        except Exception:
            return None
    
    def to_dict(self):
        """Convert model to dictionary for API responses"""
        return {
            'cognito_id': self.cognito_id,
            'nickname': self.nickname,
            'image_url': self.image_url,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }