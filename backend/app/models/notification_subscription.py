"""Per-user delivery channels: Telegram chat IDs, email addresses, etc.

A user can have multiple subscriptions (e.g. patient + their NoK both linked
to Telegram). Each channel implementation knows how to dispatch a message
given the ``target`` string.
"""
import enum
from datetime import datetime

from sqlalchemy import (Boolean, Column, DateTime, ForeignKey, Integer, String,
                        Text)

from ..database import Base


class NotificationChannel(str, enum.Enum):
    TELEGRAM = "telegram"   # target = chat_id
    EMAIL = "email"         # target = email address
    SMS = "sms"             # target = E.164 phone (Twilio)
    WEB_PUSH = "web_push"   # target = JSON-encoded VAPID subscription


class NotificationSubscription(Base):
    __tablename__ = "notification_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    channel = Column(String(20), nullable=False, index=True)
    target = Column(Text, nullable=False)
    label = Column(String(80), nullable=True)
    is_active = Column(Boolean, default=True)
    last_used_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
