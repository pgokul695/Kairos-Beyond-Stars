"""Review ORM model with vector embedding for semantic search."""

from sqlalchemy import Column, Integer, Text, ARRAY, TIMESTAMP, ForeignKey, Numeric, Date, String, func
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

from app.database import Base


class Review(Base):
    """
    A user review for a restaurant scraped from Zomato.
    Stores a 768-dimensional embedding for vector similarity search.
    The allergen_mentions field is populated during ingestion and is used
    to upgrade a restaurant's allergen_confidence to 'high'.
    """

    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, autoincrement=True)
    restaurant_id = Column(
        Integer,
        ForeignKey("restaurants.id", ondelete="CASCADE"),
        nullable=False,
    )

    review_text = Column(Text, nullable=False)
    embedding = Column(Vector(768), nullable=True)

    # Allergen keywords found in this review
    allergen_mentions = Column(ARRAY(Text), nullable=False, server_default="{}")

    source = Column(String(50), nullable=False, server_default="zomato")
    review_date = Column(Date, nullable=True)
    review_rating = Column(Numeric(3, 1), nullable=True)
    created_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    restaurant = relationship("Restaurant", back_populates="reviews")
