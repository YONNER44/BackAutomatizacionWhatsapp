from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from app.database.db import Base


class Provider(Base):
    __tablename__ = "providers"

    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(20), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<Provider(phone={self.phone_number}, name={self.name})>"
