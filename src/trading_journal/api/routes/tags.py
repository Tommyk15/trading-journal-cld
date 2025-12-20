"""API routes for tags management."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from trading_journal.core.database import get_db
from trading_journal.models.tag import Tag, trade_tags
from trading_journal.models.trade import Trade
from trading_journal.schemas.tag import (
    TagCreate,
    TagListResponse,
    TagResponse,
    TagUpdate,
    TradeTagsUpdate,
)

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("", response_model=TagListResponse)
async def list_tags(
    session: AsyncSession = Depends(get_db),
):
    """List all tags.

    Returns all available tags, sorted by name.

    Args:
        session: Database session

    Returns:
        List of all tags
    """
    query = select(Tag).order_by(Tag.name)
    result = await session.execute(query)
    tags = list(result.scalars().all())

    return TagListResponse(
        tags=[TagResponse.model_validate(tag) for tag in tags],
        total=len(tags),
    )


@router.post("", response_model=TagResponse, status_code=201)
async def create_tag(
    tag_data: TagCreate,
    session: AsyncSession = Depends(get_db),
):
    """Create a new tag.

    Args:
        tag_data: Tag creation data
        session: Database session

    Returns:
        Created tag

    Raises:
        HTTPException: If tag name already exists
    """
    # Check if tag name already exists
    existing = await session.execute(
        select(Tag).where(func.lower(Tag.name) == func.lower(tag_data.name))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail=f"Tag with name '{tag_data.name}' already exists"
        )

    tag = Tag(
        name=tag_data.name,
        color=tag_data.color,
    )
    session.add(tag)
    await session.commit()
    await session.refresh(tag)

    return TagResponse.model_validate(tag)


@router.get("/{tag_id}", response_model=TagResponse)
async def get_tag(
    tag_id: int,
    session: AsyncSession = Depends(get_db),
):
    """Get a tag by ID.

    Args:
        tag_id: Tag ID
        session: Database session

    Returns:
        Tag

    Raises:
        HTTPException: If tag not found
    """
    tag = await session.get(Tag, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail=f"Tag {tag_id} not found")

    return TagResponse.model_validate(tag)


@router.patch("/{tag_id}", response_model=TagResponse)
async def update_tag(
    tag_id: int,
    tag_data: TagUpdate,
    session: AsyncSession = Depends(get_db),
):
    """Update a tag.

    Args:
        tag_id: Tag ID
        tag_data: Update data
        session: Database session

    Returns:
        Updated tag

    Raises:
        HTTPException: If tag not found or name already exists
    """
    tag = await session.get(Tag, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail=f"Tag {tag_id} not found")

    # Check if new name conflicts with existing tag
    if tag_data.name and tag_data.name.lower() != tag.name.lower():
        existing = await session.execute(
            select(Tag).where(
                func.lower(Tag.name) == func.lower(tag_data.name),
                Tag.id != tag_id
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail=f"Tag with name '{tag_data.name}' already exists"
            )

    # Update fields
    if tag_data.name is not None:
        tag.name = tag_data.name
    if tag_data.color is not None:
        tag.color = tag_data.color

    await session.commit()
    await session.refresh(tag)

    return TagResponse.model_validate(tag)


@router.delete("/{tag_id}", status_code=204)
async def delete_tag(
    tag_id: int,
    session: AsyncSession = Depends(get_db),
):
    """Delete a tag.

    This will also remove the tag from all trades.

    Args:
        tag_id: Tag ID
        session: Database session

    Raises:
        HTTPException: If tag not found
    """
    tag = await session.get(Tag, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail=f"Tag {tag_id} not found")

    await session.delete(tag)
    await session.commit()


@router.get("/trade/{trade_id}", response_model=list[TagResponse])
async def get_trade_tags(
    trade_id: int,
    session: AsyncSession = Depends(get_db),
):
    """Get all tags for a trade.

    Args:
        trade_id: Trade ID
        session: Database session

    Returns:
        List of tags assigned to the trade

    Raises:
        HTTPException: If trade not found
    """
    trade = await session.get(Trade, trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")

    # Load tags for the trade
    query = (
        select(Tag)
        .join(trade_tags, Tag.id == trade_tags.c.tag_id)
        .where(trade_tags.c.trade_id == trade_id)
        .order_by(Tag.name)
    )
    result = await session.execute(query)
    tags = list(result.scalars().all())

    return [TagResponse.model_validate(tag) for tag in tags]


@router.put("/trade/{trade_id}", response_model=list[TagResponse])
async def update_trade_tags(
    trade_id: int,
    data: TradeTagsUpdate,
    session: AsyncSession = Depends(get_db),
):
    """Update tags for a trade.

    Replaces all existing tags with the provided list of tag IDs.

    Args:
        trade_id: Trade ID
        data: List of tag IDs to assign
        session: Database session

    Returns:
        Updated list of tags

    Raises:
        HTTPException: If trade not found or invalid tag IDs
    """
    trade = await session.get(Trade, trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")

    # Verify all tag IDs exist
    if data.tag_ids:
        existing_tags = await session.execute(
            select(Tag).where(Tag.id.in_(data.tag_ids))
        )
        found_tags = list(existing_tags.scalars().all())
        found_ids = {tag.id for tag in found_tags}
        missing_ids = set(data.tag_ids) - found_ids
        if missing_ids:
            raise HTTPException(
                status_code=400,
                detail=f"Tag IDs not found: {sorted(missing_ids)}"
            )
    else:
        found_tags = []

    # Delete existing trade-tag associations
    await session.execute(
        trade_tags.delete().where(trade_tags.c.trade_id == trade_id)
    )

    # Insert new associations
    for tag_id in data.tag_ids:
        await session.execute(
            trade_tags.insert().values(trade_id=trade_id, tag_id=tag_id)
        )

    await session.commit()

    # Return updated tags
    return [TagResponse.model_validate(tag) for tag in found_tags]


@router.post("/trade/{trade_id}/add/{tag_id}", response_model=list[TagResponse])
async def add_tag_to_trade(
    trade_id: int,
    tag_id: int,
    session: AsyncSession = Depends(get_db),
):
    """Add a tag to a trade.

    Args:
        trade_id: Trade ID
        tag_id: Tag ID to add
        session: Database session

    Returns:
        Updated list of tags

    Raises:
        HTTPException: If trade or tag not found
    """
    trade = await session.get(Trade, trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")

    tag = await session.get(Tag, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail=f"Tag {tag_id} not found")

    # Check if association already exists
    existing = await session.execute(
        select(trade_tags).where(
            trade_tags.c.trade_id == trade_id,
            trade_tags.c.tag_id == tag_id
        )
    )
    if not existing.first():
        # Insert new association
        await session.execute(
            trade_tags.insert().values(trade_id=trade_id, tag_id=tag_id)
        )
        await session.commit()

    # Return all tags for the trade
    return await get_trade_tags(trade_id, session)


@router.delete("/trade/{trade_id}/remove/{tag_id}", response_model=list[TagResponse])
async def remove_tag_from_trade(
    trade_id: int,
    tag_id: int,
    session: AsyncSession = Depends(get_db),
):
    """Remove a tag from a trade.

    Args:
        trade_id: Trade ID
        tag_id: Tag ID to remove
        session: Database session

    Returns:
        Updated list of tags

    Raises:
        HTTPException: If trade not found
    """
    trade = await session.get(Trade, trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")

    # Delete the association
    await session.execute(
        trade_tags.delete().where(
            trade_tags.c.trade_id == trade_id,
            trade_tags.c.tag_id == tag_id
        )
    )
    await session.commit()

    # Return remaining tags
    return await get_trade_tags(trade_id, session)
