"""Interaction ORM model — audit trail of every chat turn."""

from sqlalchemy import (
    Column, BigInteger, Text, Boolean, Integer,
    ARRAY, TIMESTAMP, ForeignKey, func,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.database import Base


class Interaction(Base):
    """
    Records every chat turn; includes allergy audit fields so it is
    possible to audit what warnings were shown for any past response.
    """

    __tablename__ = "interactions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    uid = Column(
        UUID(as_uuid=True),
        ForeignKey("users.uid", ondelete="CASCADE"),
        nullable=False,
    )

    user_query = Column(Text, nullable=False)
    agent_response = Column(JSONB, nullable=False, server_default="{}")

    ui_type = Column(Text, nullable=True)
    restaurant_ids = Column(ARRAY(Integer), nullable=True)

    # Allergy audit trail
    allergy_warnings_shown = Column(Boolean, nullable=False, server_default="false")
    allergens_flagged = Column(ARRAY(Text), nullable=False, server_default="{}")

    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)

    created_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    user = relationship("User", back_populates="interactions")
