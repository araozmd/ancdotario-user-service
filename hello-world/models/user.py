from pynamodb.models import Model
from pynamodb.attributes import (
    UnicodeAttribute, BooleanAttribute, UTCDateTimeAttribute
)
from pynamodb.indexes import GlobalSecondaryIndex, AllProjection
from datetime import datetime
import os


class EmailIndex(GlobalSecondaryIndex):
    """Global secondary index for email lookups"""
    class Meta:
        index_name = 'email-index'
        projection = AllProjection()
        
    email = UnicodeAttribute(hash_key=True)


class CertifiedIndex(GlobalSecondaryIndex):
    """Global secondary index for certified user queries"""
    class Meta:
        index_name = 'certified-index'
        projection = AllProjection()
        
    is_certified = BooleanAttribute(hash_key=True)
    created_at = UTCDateTimeAttribute(range_key=True)


class CreatedAtIndex(GlobalSecondaryIndex):
    """Global secondary index for chronological user queries"""
    class Meta:
        index_name = 'created-at-index'
        projection = AllProjection()
        
    created_at = UTCDateTimeAttribute(hash_key=True)


class User(Model):
    """User model for Anecdotario platform"""
    
    class Meta:
        table_name = os.environ.get('USER_TABLE_NAME', 'Users-dev')
        region = os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')
        # Enable host override for local development
        host = os.environ.get('DYNAMODB_ENDPOINT')
        
    # Primary key
    id = UnicodeAttribute(hash_key=True)
    
    # Required attributes
    name = UnicodeAttribute()
    email = UnicodeAttribute()
    
    # Optional attributes
    is_certified = BooleanAttribute(default=False)
    profile_image = UnicodeAttribute(null=True)
    
    # Timestamps
    created_at = UTCDateTimeAttribute(default=datetime.utcnow)
    updated_at = UTCDateTimeAttribute(default=datetime.utcnow)
    
    # Global Secondary Indexes
    email_index = EmailIndex()
    certified_index = CertifiedIndex()
    created_at_index = CreatedAtIndex()
    
    def save(self, **kwargs):
        """Override save to update timestamp"""
        self.updated_at = datetime.utcnow()
        super().save(**kwargs)
    
    def to_dict(self):
        """Convert model to dictionary"""
        return {
            'id': self.id,
            'name': self.name,
            'email': self.email,
            'is_certified': self.is_certified,
            'profile_image': self.profile_image,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }