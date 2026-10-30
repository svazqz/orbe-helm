"""Agent-independent, append-only conversation events and explicit working checkpoints."""
import json
from pathlib import Path
import sys

from sqlalchemy import select, func, cast, String

from .core import OrbeHelmError, canonical
from .product.database import product_lock
from .product.models import Conversation, ConversationEvent, MemoryState, now, new_id
from .product.projects import get_project

MAX_EVENT = 2 * 1024 * 1024


def context_identity(store, project_id, profile, spec=None, unique_key=None, thread=None):
    from .product.projects import ensure_context
    return ensure_context(store, project_id, profile, spec, unique_key, thread)


def conversation(store, project_id, profile, spec=None, unique_key=None):
    selection = canonical({'profile': profile, 'spec': spec or None, 'unique_key': unique_key or None})
    with product_lock(store.root), store.write() as db:
        row = db.scalars(select(Conversation).where(Conversation.project_id == project_id,
                                                   Conversation.selection == selection)).first()
        if row is None:
            row = Conversation(id=new_id(), project_id=project_id, selection=selection)
            db.add(row)
            db.flush()
        result = row.id
    from .product.projects import ensure_context
    ensure_context(store, project_id, profile, spec, unique_key, result)
    return result


def append(store, thread, kind, agent, data, source_id=None):
    if len(canonical(data).encode()) > MAX_EVENT:
        raise OrbeHelmError('Conversation event exceeds 2 MiB; capture stopped instead of truncating history')
    with product_lock(store.root), store.write() as db:
        if db.get(Conversation, thread) is None:
            raise OrbeHelmError('Unknown conversation')
        if source_id:
            existing = db.scalar(select(ConversationEvent.sequence).where(
                ConversationEvent.conversation_id == thread, ConversationEvent.source_id == source_id))
            if existing is not None:
                return existing
        sequence = (db.scalar(select(func.max(ConversationEvent.sequence)).where(
            ConversationEvent.conversation_id == thread)) or 0) + 1
        db.add(ConversationEvent(conversation_id=thread, sequence=sequence,
                                 kind=kind, agent=agent, data=data, source_id=source_id))
        return sequence


def events(store, thread, query='', limit=50, after=None, kinds=None, memory_epoch=None, memory_visibility=None):
    if not 1 <= limit <= 200:
        raise OrbeHelmError('History limit must be between 1 and 200')
    statement = select(ConversationEvent).where(ConversationEvent.conversation_id == thread)
    if memory_epoch is not None:
        statement = statement.where(func.coalesce(func.json_extract(ConversationEvent.data, '$._memory_epoch'), 0) == memory_epoch)
    if memory_visibility in {'project', 'global'}:
        allowed = ['global'] if memory_visibility == 'global' else ['project', 'global']
        statement = statement.where(func.coalesce(func.json_extract(ConversationEvent.data, '$._memory_visibility'), 'private').in_(allowed))
    if kinds:
        statement = statement.where(ConversationEvent.kind.in_(kinds))
    if query:
        statement = statement.where(func.lower(cast(ConversationEvent.data, String)).contains(query.lower(), autoescape=True))
    if after is not None:
        statement = statement.where(ConversationEvent.sequence > after).order_by(ConversationEvent.sequence)
    else:
        statement = statement.order_by(ConversationEvent.sequence.desc())
    with store.read() as db:
        rows = db.scalars(statement.limit(limit)).all()
        if after is None:
            rows.reverse()
        return [{'sequence': row.sequence, 'kind': row.kind, 'agent': row.agent,
                 'data': row.data, 'created_at': row.created_at} for row in rows]


def bootstrap(store, thread, budget=24000, memory_epoch=None, memory_visibility=None):
    with store.read() as db:
        row = db.get(Conversation, thread)
        checkpoint = row.checkpoint
    recent = events(store, thread, limit=200, kinds=('user', 'assistant', 'native_message', 'checkpoint'), memory_epoch=memory_epoch, memory_visibility=memory_visibility)
    if (memory_epoch is not None and memory_epoch > 0) or memory_visibility in {'project', 'global'}:
        checkpoints = [item['data']['text'] for item in recent if item['kind'] == 'checkpoint']
        checkpoint = checkpoints[-1] if checkpoints else ''
    from .domain.conversations.context import history_context
    return history_context(thread, checkpoint, recent, budget)


def operation(store, action, project_path, thread=None, query='', limit=50, content_file=None, after=None, memory_epoch=None, memory_visibility=None):
    project = get_project(store, str(project_path))
    with store.read() as db:
        if action == 'list':
            return [{'id': row.id, 'selection': json.loads(row.selection), 'created_at': row.created_at}
                    for row in db.scalars(select(Conversation).where(Conversation.project_id == project.id))]
        row = db.get(Conversation, thread)
        if row is None or row.project_id != project.id:
            raise OrbeHelmError('Conversation is not in the selected project')
    if action in {'history', 'search', 'show'}:
        result = events(store, thread, query=query, limit=limit, after=after, memory_epoch=memory_epoch, memory_visibility=memory_visibility)
        return {'id': thread, 'checkpoint': row.checkpoint if memory_epoch in {None, 0} and memory_visibility != 'global' else '', 'events': result,
                'next_after': result[-1]['sequence'] if result else after}
    if action == 'checkpoint':
        if not content_file:
            raise OrbeHelmError('Supply --from-file=<checkpoint> or --from-file=-')
        if content_file == '-':
            text = sys.stdin.read(8193)
        else:
            with Path(content_file).open(encoding='utf-8') as handle:
                text = handle.read(8193)
        if len(text) > 8000:
            raise OrbeHelmError('Checkpoint exceeds 8000 characters')
        set_checkpoint(store, thread, text)
        return {'id': thread, 'checkpoint': text}
    raise OrbeHelmError('Use conversations list|show|history|search|checkpoint')


def set_checkpoint(store, thread, text):
    if len(text) > 8000:
        raise OrbeHelmError('Checkpoint exceeds 8000 characters')
    with product_lock(store.root), store.write() as db:
        row = db.get(Conversation, thread)
        if row is None:
            raise OrbeHelmError('Unknown conversation')
        sequence = (db.scalar(select(func.max(ConversationEvent.sequence)).where(
            ConversationEvent.conversation_id == thread)) or 0) + 1
        row.checkpoint = text
        state = db.get(MemoryState, 1)
        epoch = state.policy_epoch if state else 0
        db.add(ConversationEvent(conversation_id=thread, sequence=sequence, kind='checkpoint',
                                 agent='operator', data={'text': text, '_memory_epoch': epoch}))
