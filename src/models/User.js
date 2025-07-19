const dynamoose = require('dynamoose');

const UserSchema = new dynamoose.Schema({
  id: {
    type: String,
    hashKey: true,
    required: true
  },
  name: {
    type: String,
    required: true,
    index: true
  },
  email: {
    type: String,
    required: true,
    index: {
      name: 'email-index',
      global: true
    }
  },
  isCertified: {
    type: Boolean,
    default: false,
    index: {
      name: 'certified-index',
      global: true
    }
  },
  createdAt: {
    type: Date,
    default: Date.now,
    index: {
      name: 'created-at-index',
      global: true
    }
  },
  profileImage: {
    type: String,
    required: false
  }
}, {
  timestamps: true
});

module.exports = dynamoose.model('User', UserSchema);