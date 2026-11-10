from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.auth.deps import AuthContext, passive_auth, require_permission
from app.auth.permissions import Permission
from app.auth.ratelimit import check_limiter
from app.core.config import settings
from app.core.errors import InvalidInput
from app.db import get_db
from app.models import ChatMessage, ChatReceipt, User, utcnow
from app.services.chat import PRESENCE, parse_image

router = APIRouter(prefix="/api/chat", tags=["chat"])

user_perm = require_permission(Permission.CUSTOMER_CHECK)


class SendBody(BaseModel):
    text: str = Field(default="", max_length=4000)
    image: str | None = Field(default=None, max_length=4_000_000)
    reply_to: int | None = None


class ReadBody(BaseModel):
    ids: list[int] = Field(max_length=200)


def _names(db: Session, ids) -> dict:
    if not ids:
        return {}
    return {u.id: u.username for u in db.scalars(select(User).where(User.id.in_(list(ids))))}


def _item(message: ChatMessage, names: dict, **extra) -> dict:
    return {
        "id": message.id,
        "sender": names.get(message.sender_id, "?"),
        "text": message.text,
        "has_image": message.image is not None,
        "reply_to": message.reply_to_id,
        "created_at": message.created_at.isoformat() + "Z",
        **extra,
    }


@router.get("/poll")
def poll(after: int | None = Query(default=None), auth: AuthContext = Depends(passive_auth), db: Session = Depends(get_db)):
    """Called every few seconds by every open panel: counts as "online" and returns new messages."""
    me = auth.user.id
    PRESENCE.touch(me)

    latest = db.scalar(
        select(func.max(ChatReceipt.message_id)).where(ChatReceipt.user_id == me)
    ) or 0
    unread = db.scalar(
        select(func.count()).select_from(ChatReceipt).where(ChatReceipt.user_id == me, ChatReceipt.read_at.is_(None))
    ) or 0

    messages = []
    if after is not None:
        rows = db.execute(
            select(ChatMessage, ChatReceipt)
            .join(ChatReceipt, ChatReceipt.message_id == ChatMessage.id)
            .where(ChatReceipt.user_id == me, ChatMessage.id > after)
            .order_by(ChatMessage.id)
            .limit(50)
        ).all()
        names = _names(db, {m.sender_id for m, _ in rows})
        messages = [_item(m, names, read=r.read_at is not None) for m, r in rows]

    online_ids = PRESENCE.online_ids() - {me}
    online = sorted(_names(db, online_ids).values(), key=str.lower)
    return {"latest_id": latest, "unread": unread, "messages": messages, "online": online}


@router.get("/thread")
def thread(limit: int = Query(default=60, ge=1, le=200), auth: AuthContext = Depends(passive_auth), db: Session = Depends(get_db)):
    """The recent messages this user sent or received, oldest first."""
    me = auth.user.id
    PRESENCE.touch(me)
    received_ids = select(ChatReceipt.message_id).where(ChatReceipt.user_id == me)
    messages = list(
        reversed(
            db.scalars(
                select(ChatMessage)
                .where(or_(ChatMessage.sender_id == me, ChatMessage.id.in_(received_ids)))
                .order_by(ChatMessage.id.desc())
                .limit(limit)
            ).all()
        )
    )
    ids = [m.id for m in messages]
    names = _names(db, {m.sender_id for m in messages})
    mine_receipts = {
        r.message_id: r
        for r in db.scalars(select(ChatReceipt).where(ChatReceipt.user_id == me, ChatReceipt.message_id.in_(ids)))
    } if ids else {}
    sent_stats: dict = {}
    if ids:
        for message_id, total, read in db.execute(
            select(
                ChatReceipt.message_id,
                func.count(),
                func.count(ChatReceipt.read_at),
            )
            .where(ChatReceipt.message_id.in_(ids))
            .group_by(ChatReceipt.message_id)
        ):
            sent_stats[message_id] = (total, read)

    items = []
    for message in messages:
        if message.sender_id == me:
            total, read = sent_stats.get(message.id, (0, 0))
            items.append(_item(message, names, mine=True, recipients=total, read_by=read))
        else:
            receipt = mine_receipts.get(message.id)
            items.append(_item(message, names, mine=False, read=receipt is not None and receipt.read_at is not None))
    return {"messages": items}


@router.get("/image/{message_id}")
def image(message_id: int, auth: AuthContext = Depends(passive_auth), db: Session = Depends(get_db)):
    message = db.get(ChatMessage, message_id)
    allowed = message is not None and message.image is not None and (
        message.sender_id == auth.user.id
        or db.scalar(
            select(ChatReceipt.id).where(ChatReceipt.message_id == message_id, ChatReceipt.user_id == auth.user.id)
        )
        is not None
    )
    if not allowed:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Picture not found"})
    return Response(
        content=message.image,
        media_type=message.image_mime or "application/octet-stream",
        headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"},
    )


@router.post("/send")
async def send(body: SendBody, auth: AuthContext = Depends(user_perm), db: Session = Depends(get_db)):
    key = f"chat:{auth.user.id}"
    if check_limiter.blocked(key, settings.chat_sends_per_minute, 60):
        raise HTTPException(status_code=429, detail={"code": "rate_limited", "message": "Too many messages. Wait a moment."})
    check_limiter.record(key)

    text = body.text.strip()
    if len(text) > settings.chat_max_text:
        raise InvalidInput(f"A message can have at most {settings.chat_max_text} characters")
    picture = None
    if body.image:
        picture = await run_in_threadpool(parse_image, body.image)
    if not text and picture is None:
        raise InvalidInput("Write a message or add a picture")

    me = auth.user.id
    if body.reply_to is not None:
        original = db.get(ChatMessage, body.reply_to)
        is_recipient = original is not None and db.scalar(
            select(ChatReceipt.id).where(ChatReceipt.message_id == original.id, ChatReceipt.user_id == me)
        ) is not None
        if not is_recipient:
            raise InvalidInput("That message cannot be replied to")
        recipients = {original.sender_id} - {me}
    else:
        recipients = PRESENCE.online_ids() - {me}

    if not recipients:
        return {"delivered": 0, "id": None}

    message = ChatMessage(
        sender_id=me,
        text=text,
        image=picture[0] if picture else None,
        image_mime=picture[1] if picture else None,
        reply_to_id=body.reply_to,
    )
    db.add(message)
    db.flush()
    db.add_all([ChatReceipt(message_id=message.id, user_id=uid) for uid in recipients])

    cutoff = utcnow() - timedelta(days=settings.chat_keep_days)
    old = select(ChatMessage.id).where(ChatMessage.created_at < cutoff)
    db.execute(delete(ChatReceipt).where(ChatReceipt.message_id.in_(old)))
    db.execute(delete(ChatMessage).where(ChatMessage.created_at < cutoff))
    db.commit()
    return {"delivered": len(recipients), "id": message.id}


@router.post("/read")
def mark_read(body: ReadBody, auth: AuthContext = Depends(user_perm), db: Session = Depends(get_db)):
    now = utcnow()
    rows = db.scalars(
        select(ChatReceipt).where(
            ChatReceipt.user_id == auth.user.id,
            ChatReceipt.message_id.in_(body.ids),
            ChatReceipt.read_at.is_(None),
        )
    ).all()
    for row in rows:
        row.read_at = now
    db.commit()
    return {"marked": len(rows)}