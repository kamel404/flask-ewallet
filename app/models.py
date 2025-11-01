import uuid
from datetime import datetime, timezone
from sqlalchemy.dialects.postgresql import UUID
from werkzeug.security import generate_password_hash, check_password_hash
from . import db

def uuid4():
    return str(uuid.uuid4())

class User(db.Model):
    __tablename__ = "users"
    id = db.Column(UUID(as_uuid=False), primary_key=True, default=uuid4)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    first_name = db.Column(db.String(120))
    last_name = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    cards = db.relationship("Card", back_populates="user", cascade="all, delete-orphan")
    balances = db.relationship("CurrencyBalance", back_populates="user", cascade="all, delete-orphan")

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

class CurrencyBalance(db.Model):
    __tablename__ = "currency_balances"
    id = db.Column(UUID(as_uuid=False), primary_key=True, default=uuid4)
    user_id = db.Column(UUID(as_uuid=False), db.ForeignKey("users.id"), nullable=False)
    currency = db.Column(db.String(3), nullable=False)  # "USD" or "LBP"
    amount = db.Column(db.BigInteger, nullable=False, default=0)  # minor units
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = db.relationship("User", back_populates="balances")

    __table_args__ = (db.UniqueConstraint("user_id", "currency", name="uq_user_currency"),)

class Card(db.Model):
    __tablename__ = "cards"
    id = db.Column(UUID(as_uuid=False), primary_key=True, default=uuid4)
    user_id = db.Column(UUID(as_uuid=False), db.ForeignKey("users.id"), nullable=False)
    pan_masked = db.Column(db.String(32), nullable=False, index=True)  # masked PAN e.g. 545454******5454
    card_type = db.Column(db.String(20), nullable=False)  # physical | virtual
    status = db.Column(db.String(20), nullable=False, default="active")  # active | frozen | canceled
    expiry = db.Column(db.String(6), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship("User", back_populates="cards")

class Transaction(db.Model):
    __tablename__ = "transactions"
    id = db.Column(UUID(as_uuid=False), primary_key=True, default=uuid4)
    from_user_id = db.Column(UUID(as_uuid=False), nullable=True)  # null for topup
    to_user_id = db.Column(UUID(as_uuid=False), nullable=True)    # null for card payments to external
    currency = db.Column(db.String(3), nullable=False)
    amount = db.Column(db.BigInteger, nullable=False)  # minor units
    type = db.Column(db.String(32), nullable=False)  # topup | p2p | card_payment
    status = db.Column(db.String(20), nullable=False, default="pending")  # pending|completed|failed
    details = db.Column(db.JSON, default={})
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

class CardAuthRequest(db.Model):
    __tablename__ = "card_auth_requests"
    id = db.Column(UUID(as_uuid=False), primary_key=True, default=uuid4)
    idempotency_key = db.Column(db.String(36), unique=True, nullable=False)
    request_payload = db.Column(db.JSON, nullable=False)
    response_payload = db.Column(db.JSON, nullable=False)
    processed_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
