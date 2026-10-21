from sqlalchemy import select

from app.extensions import db
from app.models import Conversation, ConversationMemory, ConversationMessage
from app.schemas import MemoryInput, MessageInput
from app.services.errors import BusinessError


def owned_conversation(user_id: int, conversation_id: int, *, lock: bool = False) -> Conversation:
    query = select(Conversation).where(
        Conversation.id == conversation_id,
        Conversation.user_id == user_id,
    )
    if lock:
        query = query.with_for_update()
    conversation = db.session.scalar(query)
    if conversation is None:
        raise BusinessError("对话不存在。", 404)
    return conversation


def append_message(user_id: int, conversation_id: int, data: MessageInput) -> ConversationMessage:
    conversation = owned_conversation(user_id, conversation_id, lock=True)
    previous = db.session.scalar(
        select(ConversationMessage).where(
            ConversationMessage.conversation_id == conversation_id,
            ConversationMessage.request_key == str(data.request_key),
        )
    )
    if previous:
        if previous.content != data.content:
            raise BusinessError("重复请求内容不一致。", 409)
        return previous
    if conversation.status != "active":
        raise BusinessError("此对话已只读。", 409)
    message = ConversationMessage(
        conversation_id=conversation_id,
        role="user",
        content=data.content,
        request_key=str(data.request_key),
    )
    db.session.add(message)
    db.session.commit()
    return message


def save_memory(user_id: int, conversation_id: int, data: MemoryInput) -> None:
    conversation = owned_conversation(user_id, conversation_id, lock=True)
    if conversation.status != "active":
        raise BusinessError("此对话已只读。", 409)
    memory = db.session.scalar(
        select(ConversationMemory).where(
            ConversationMemory.conversation_id == conversation_id,
            ConversationMemory.key == data.key,
        )
    )
    if memory is None:
        memory = ConversationMemory(conversation_id=conversation_id, key=data.key)
        db.session.add(memory)
    memory.value = {"text": data.value}
    memory.provenance = "user_confirmed"
    db.session.commit()


def build_context(user_id: int, conversation_id: int, char_budget: int = 12000) -> dict:
    owned_conversation(user_id, conversation_id)
    memories = db.session.scalars(
        select(ConversationMemory)
        .where(
            ConversationMemory.conversation_id == conversation_id,
            ConversationMemory.provenance == "user_confirmed",
        )
        .order_by(ConversationMemory.id.desc())
        .limit(30)
    ).all()
    messages = db.session.scalars(
        select(ConversationMessage)
        .where(
            ConversationMessage.conversation_id == conversation_id,
        )
        .order_by(ConversationMessage.id.desc())
        .limit(40)
    ).all()
    remaining = max(0, min(char_budget, 24000))
    facts, history = [], []
    for memory in memories:
        item = {"key": memory.key, "value": memory.value, "source": memory.provenance}
        cost = len(str(item))
        if cost <= remaining:
            facts.append(item)
            remaining -= cost
    for message in messages:
        item = {"role": message.role, "content": message.content}
        cost = len(str(item))
        if cost > remaining:
            break
        history.append(item)
        remaining -= cost
    return {"untrusted_user_data": {"facts": facts, "messages": list(reversed(history))}}
