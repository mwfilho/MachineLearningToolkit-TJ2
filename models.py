import uuid
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from database import db
import secrets
import datetime
from sqlalchemy.dialects.postgresql import UUID

class User(UserMixin, db.Model):
    __tablename__ = 'user'
    # Alterado para UUID
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    is_admin = db.Column(db.Boolean, default=False)
    can_create_api_keys = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime,
                           default=datetime.datetime.utcnow,
                           onupdate=datetime.datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def generate_api_key(self, description=None):
        """Gera uma nova API key para o usuário"""
        new_key = ApiKey()
        new_key.user_id = self.id  # agora UUID
        new_key.key = secrets.token_hex(32)
        new_key.description = description
        db.session.add(new_key)
        db.session.commit()
        return new_key

    def get_api_keys(self):
        """Retorna todas as API keys ativas do usuário"""
        return ApiKey.query.filter_by(user_id=self.id, is_active=True).all()

    def __repr__(self):
        return f"<User {self.username}>"


class ApiKey(db.Model):
    __tablename__ = 'api_key'
    id = db.Column(db.Integer, primary_key=True)
    # Alterado para UUID, batendo com User.id
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('user.id'), nullable=False)
    key = db.Column(db.String(128), unique=True, nullable=False)
    description = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    last_used = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)

    user = db.relationship('User', backref=db.backref('api_keys', lazy=True))

    def use(self):
        """Atualiza a data de último uso"""
        self.last_used = datetime.datetime.utcnow()
        db.session.commit()

    def __repr__(self):
        return f"<ApiKey {self.key} owned_by={self.user_id}>"
