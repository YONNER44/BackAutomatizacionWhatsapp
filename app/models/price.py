from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Date
from sqlalchemy.sql import func
from app.database.db import Base


class Price(Base):
    __tablename__ = "prices"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=False)
    provider_id = Column(Integer, ForeignKey("providers.id"), nullable=False)
    medication_name = Column(String(200), nullable=False, index=True)
    price = Column(Float, nullable=False)
    unit = Column(String(50), nullable=True)
    date_reported = Column(Date, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<Price(medication={self.medication_name}, price={self.price}, provider_id={self.provider_id})>"
