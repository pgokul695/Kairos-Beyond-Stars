"""Restaurant ORM model with allergen metadata."""

from sqlalchemy import (
    Column, Integer, Text, String, Numeric, Boolean,
    ARRAY, TIMESTAMP, Double, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.database import Base


class Restaurant(Base):
    """
    Represents a restaurant ingested from the Zomato Bangalore dataset.
    Includes allergen metadata used by AllergyGuard at query time.
    """

    __tablename__ = "restaurants"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False)
    url = Column(Text, nullable=True)
    address = Column(Text, nullable=True)
    area = Column(Text, nullable=True)
    city = Column(Text, nullable=False, server_default="Bangalore")

    cuisine_types = Column(ARRAY(Text), nullable=False, server_default="{}")
    price_tier = Column(String(10), nullable=True)   # '$' | '$$' | '$$$' | '$$$$'
    cost_for_two = Column(Integer, nullable=True)

    rating = Column(Numeric(3, 1), nullable=True)
    votes = Column(Integer, nullable=False, server_default="0")

    lat = Column(Double, nullable=True)
    lng = Column(Double, nullable=True)

    # Allergen metadata
    known_allergens = Column(ARRAY(Text), nullable=False, server_default="{}")
    allergen_confidence = Column(
        String(10), nullable=False, server_default="low"
    )  # 'high' | 'medium' | 'low'

    meta = Column(JSONB, nullable=False, server_default="{}")

    is_active = Column(Boolean, nullable=False, server_default="true")
    created_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    reviews = relationship(
        "Review", back_populates="restaurant", cascade="all, delete-orphan"
    )
