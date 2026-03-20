from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum
from sqlalchemy.sql import func
from app.database.db import Base
import enum


class MessageType(str, enum.Enum):
    TEXT = "text"
    IMAGE = "image"


class MessageStatus(str, enum.Enum):
    RECEIVED = "received"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    whatsapp_message_id = Column(String(100), unique=True, index=True, nullable=False)
    provider_id = Column(Integer, ForeignKey("providers.id"), nullable=True)
    phone_number = Column(String(20), nullable=False)
    message_type = Column(Enum(MessageType), nullable=False)
    raw_text = Column(Text, nullable=True)
    image_url = Column(String(500), nullable=True)
    extracted_text = Column(Text, nullable=True)
    status = Column(Enum(MessageStatus), default=MessageStatus.RECEIVED)
    error_message = Column(Text, nullable=True)
    received_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<Message(id={self.id}, type={self.message_type}, status={self.status})>"
