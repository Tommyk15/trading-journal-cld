"""Pydantic schemas for Tag model."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TagBase(BaseModel):
    """Base tag schema."""

    name: str = Field(..., description="Tag name", max_length=50)
    color: str = Field(default="#6B7280", description="Hex color code", max_length=7)


class TagCreate(TagBase):
    """Schema for creating a tag."""

    pass


class TagUpdate(BaseModel):
    """Schema for updating a tag."""

    name: str | None = Field(None, max_length=50)
    color: str | None = Field(None, max_length=7)


class TagResponse(TagBase):
    """Schema for tag response."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Database ID")
    created_at: datetime = Field(..., description="Record creation timestamp")


class TagListResponse(BaseModel):
    """Schema for list of tags response."""

    tags: list[TagResponse]
    total: int


class TradeTagsUpdate(BaseModel):
    """Schema for updating tags on a trade."""

    tag_ids: list[int] = Field(..., description="List of tag IDs to assign to the trade")
