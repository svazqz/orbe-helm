"""Authoritative KUnits and an independently rebuildable SQLite search projection."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import hmac
import json
import math
from pathlib import Path
import secrets
import sqlite3
import struct
import time
import uuid

from ...domain.shared.errors import Conflict, Forbidden, OrbeHelmError
from ...domain.knowledge.retrieval import (ACTIVE_STATES, content_text, lexical_expression,
    may_read, reciprocal_rank_fusion, segments, visibility, outcome_metadata, instruction_like)


class SQLiteMemory:
    def __init__(self, database, index, embedder=None, clock=time.time, ids=lambda: uuid.uuid4().hex):
        self.database, self.index = Path(database), Path(index)
        self.embedder, self.clock, self.ids = embedder, clock, ids
        for path in (self.database, self.index):
            if any(part.is_symlink() for part in (path, *path.parents)):
                raise OrbeHelmError('Memory storage must not traverse symlinks')
        self.configuration = self.settings()

    @contextmanager
    def transaction(self, write=False):
        db = sqlite3.connect(self.database, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            yield db
            db.commit()
        except sqlite3.DatabaseError as error:
            db.rollback()
            raise OrbeHelmError('Canonical memory storage is unavailable or busy; retry or inspect its backup') from error
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @contextmanager
    def search_index(self):
        if self.index.is_symlink():
            raise OrbeHelmError('Memory index must not be a symlink')
        self.index.parent.mkdir(parents=True, exist_ok=True)
        # Create with restrictive permissions before SQLite opens the file.
        import os
        descriptor = os.open(self.index, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        os.close(descriptor)
        db = sqlite3.connect(self.index, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            db.executescript('''
                CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
                    unit_id UNINDEXED, revision UNINDEXED, ordinal UNINDEXED, content);
                CREATE TABLE IF NOT EXISTS vectors (
                    unit_id TEXT, revision INTEGER, ordinal INTEGER, model TEXT, vector BLOB,
                    PRIMARY KEY(unit_id, ordinal));
            ''')
            yield db
            db.commit()
        except sqlite3.DatabaseError as error:
            db.rollback()
            raise OrbeHelmError('Memory search index is unavailable; run oh memory reindex --rebuild-index') from error
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _timestamp(self):
        return datetime.fromtimestamp(self.clock(), timezone.utc).isoformat()

    def ensure_owner(self, owner, project_id, default_visibility=None):
        if default_visibility is not None:
            visibility(default_visibility)
        with self.transaction(True) as db:
            row = db.execute('SELECT * FROM memory_owners WHERE id=?', (owner,)).fetchone()
            if row and row['project_id'] != project_id:
                raise Forbidden('Access denied')
            if not row:
                db.execute('INSERT INTO memory_owners VALUES (?, ?, ?)', (owner, project_id, default_visibility or 'private'))
            elif default_visibility is not None:
                db.execute('UPDATE memory_owners SET visibility=? WHERE id=?', (default_visibility, owner))
            return default_visibility or (row['visibility'] if row else 'private')

    def issue_binding(self, owner, default_visibility, conversation_id=None):
        visibility(default_visibility)
        binding, token = self.ids(), secrets.token_urlsafe(32)
        with self.transaction(True) as db:
            if conversation_id:
                relation = db.execute('SELECT c.project_id=o.project_id FROM conversations c JOIN memory_owners o ON o.id=? WHERE c.id=?',
                                      (owner, conversation_id)).fetchone()
                if not relation or not relation[0]:
                    raise Forbidden('Access denied')
                previous = db.execute('SELECT owner_id FROM memory_threads WHERE conversation_id=?', (conversation_id,)).fetchone()
                if previous and previous['owner_id'] != owner:
                    raise Conflict('Conversation is already bound to another memory owner')
                db.execute('INSERT OR IGNORE INTO memory_threads VALUES (?, ?)', (conversation_id, owner))
            db.execute('INSERT INTO memory_bindings VALUES (?, ?, ?, ?, ?, 1, ?)',
                (binding, owner, hashlib.sha256(token.encode()).hexdigest(), default_visibility, int(self.clock()) + 43200, conversation_id))
        return {'binding': binding, 'token': token}

    def verify_binding(self, binding, token):
        if not isinstance(binding, str) or not isinstance(token, str):
            raise Forbidden('Access denied')
        with self.transaction() as db:
            row = db.execute('SELECT * FROM memory_bindings WHERE id=?', (binding,)).fetchone()
            if (not row or not row['active'] or row['expires_at'] <= self.clock()
                    or not hmac.compare_digest(row['token_hash'], hashlib.sha256(token.encode()).hexdigest())):
                raise Forbidden('Access denied')
            return dict(row)

    def revoke_binding(self, binding):
        with self.transaction(True) as db:
            db.execute('UPDATE memory_bindings SET active=0 WHERE id=?', (binding,))

    def inherit_reads(self, owner, binding, previous):
        """A resumed native session retains the provenance of its earlier context."""
        with self.transaction(True) as db:
            self._check_binding(db, owner, binding)
            parent = db.execute('SELECT owner_id FROM memory_bindings WHERE id=?', (previous,)).fetchone()
            if not parent or parent['owner_id'] != owner:
                raise Forbidden('Access denied')
            for read in db.execute('SELECT unit_id,revision FROM memory_reads WHERE binding_id=?', (previous,)).fetchall():
                row = self._readable(db, owner, read['unit_id'], binding)
                if row['revision'] != read['revision']:
                    raise Conflict('Native context contains changed knowledge; start a fresh session')
                self._record_read(db, binding, row)

    def binding_visibility(self, binding):
        with self.transaction() as db:
            row = db.execute('SELECT visibility FROM memory_bindings WHERE id=?', (binding,)).fetchone()
            private = db.execute("SELECT 1 FROM memory_reads r JOIN kunits k ON k.id=r.unit_id "
                                 "WHERE r.binding_id=? AND k.visibility='private' LIMIT 1", (binding,)).fetchone()
            project = db.execute("SELECT 1 FROM memory_reads r JOIN kunits k ON k.id=r.unit_id "
                                 "WHERE r.binding_id=? AND k.visibility='project' LIMIT 1", (binding,)).fetchone()
            return 'private' if private else 'project' if project and row['visibility'] == 'global' else row['visibility']

    def _check_binding(self, db, owner, binding):
        if binding is None:
            return
        row = db.execute('SELECT * FROM memory_bindings WHERE id=?', (binding,)).fetchone()
        if not row or row['owner_id'] != owner or not row['active'] or row['expires_at'] <= self.clock():
            raise Forbidden('Access denied')
        return row

    def _readable(self, db, owner, unit_id, binding=None):
        self._check_binding(db, owner, binding)
        row = db.execute('SELECT * FROM kunits WHERE id=?', (unit_id,)).fetchone()
        if not row or not self._eligible(db, owner, row, binding):
            raise Forbidden('Access denied')
        return row

    def _identity(self, db, owner, binding=None):
        bound = self._check_binding(db, owner, binding)
        owner_row = db.execute('SELECT project_id FROM memory_owners WHERE id=?', (owner,)).fetchone()
        selection = {}
        if bound and bound['conversation_id']:
            row = db.execute('SELECT selection FROM conversations WHERE id=?', (bound['conversation_id'],)).fetchone()
            try:
                selection = json.loads(row[0]) if row else {}
            except (ValueError, TypeError):
                selection = {}
        elif not binding:
            row = db.execute('SELECT selection FROM conversations WHERE id=?', (owner,)).fetchone()
            try:
                selection = json.loads(row[0]) if row else {}
            except (ValueError, TypeError):
                selection = {}
            if not selection:
                actor = db.execute('SELECT profile,specialization FROM logical_orbes WHERE id=?', (owner,)).fetchone()
                if actor:
                    selection = {'profile': actor['profile'], 'spec': actor['specialization']}
        if not isinstance(selection, dict):
            selection = {}
        return (owner_row['project_id'] if owner_row else None,
                selection.get('profile', ''), selection.get('spec') or '')

    def _eligible(self, db, owner, row, binding=None):
        if row['status'] == 'pending' and not binding and owner == row['owner_id']:
            return True
        if row['status'] not in ACTIVE_STATES:
            return False
        project, profile, spec = self._identity(db, owner, binding)
        source_owner = db.execute('SELECT project_id FROM memory_owners WHERE id=?', (row['owner_id'],)).fetchone()
        allowed = (owner == row['owner_id'] or row['visibility'] == 'global' or
                   (row['visibility'] == 'project' and source_owner and source_owner['project_id'] == project))
        if not allowed:
            return False
        metadata = db.execute('SELECT * FROM knowledge_metadata WHERE unit_id=?', (row['id'],)).fetchone()
        if binding:
            if not metadata:
                return False
            audience = json.loads(metadata['audience'])
            return '*' in audience or profile in audience or (bool(spec) and profile + ':' + spec in audience)
        return True

    @staticmethod
    def _dto(row):
        return {key: row[key] for key in ('id', 'owner_id', 'revision', 'content', 'visibility',
                                         'status', 'source_kind', 'created_at', 'updated_at')}

    def _details(self, db, row):
        result = self._dto(row)
        metadata = db.execute('SELECT * FROM knowledge_metadata WHERE unit_id=?', (row['id'],)).fetchone()
        if metadata:
            result.update(kind=metadata['kind'], evidence=json.loads(metadata['evidence']),
                          audience=json.loads(metadata['audience']), evidence_state=metadata['evidence_state'],
                          profile=metadata['profile'], specialization=metadata['specialization'])
        else:
            result['kind'] = 'unclassified'
        return result

    def _record_read(self, db, binding, row):
        if binding:
            if db.execute('SELECT count(*) FROM memory_reads WHERE binding_id=?', (binding,)).fetchone()[0] >= 1000:
                if not db.execute('SELECT 1 FROM memory_reads WHERE binding_id=? AND unit_id=?', (binding, row['id'])).fetchone():
                    raise OrbeHelmError('Memory provenance limit reached; start a fresh turn')
            db.execute('INSERT INTO memory_reads VALUES (?, ?, ?) ON CONFLICT(binding_id,unit_id) '
                       'DO UPDATE SET revision=excluded.revision', (binding, row['id'], row['revision']))

    def _revision(self, db, unit_id, reason):
        row = db.execute('SELECT * FROM kunits WHERE id=?', (unit_id,)).fetchone()
        db.execute('INSERT INTO kunit_revisions VALUES (?, ?, ?, ?, ?, ?, ?)',
            (unit_id, row['revision'], row['content'], row['visibility'], row['status'], reason, self._timestamp()))
        db.execute("INSERT INTO memory_index_jobs VALUES (?, ?, 'pending', NULL) ON CONFLICT(unit_id) "
                   "DO UPDATE SET revision=excluded.revision,status='pending',error=NULL", (unit_id, row['revision']))
        return self._details(db, row)

    def put(self, owner, content, source_id, default_visibility, binding_id=None, source_ids=(), source_kind='explicit', source_versions=None, metadata=None):
        content, default_visibility = content_text(content), visibility(default_visibility)
        metadata = outcome_metadata(**metadata) if metadata is not None else None
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        with self.transaction(True) as db:
            bound = self._check_binding(db, owner, binding_id)
            project, profile, spec = self._identity(db, owner, binding_id)
            if bound and metadata is None:
                raise OrbeHelmError('Agent writes require structured outcome metadata')
            if bound and metadata['evidence_state'] == 'verified' and profile not in {'reviewer', 'qa'}:
                raise Forbidden('Independent verification requires a reviewer or QA binding')
            if bound and bound['visibility'] != default_visibility:
                raise Forbidden('Launch binding fixes the visibility default')
            source = db.execute('SELECT * FROM memory_sources WHERE owner_id=? AND source_id=?', (owner, source_id)).fetchone()
            existing = db.execute('SELECT * FROM kunits WHERE id=?', (source['unit_id'],)).fetchone() if source else None
            if existing:
                if source['content_hash'] != content_hash or source['source_kind'] != source_kind:
                    raise Conflict('Memory source_id already identifies different content')
                recorded = db.execute('SELECT * FROM knowledge_metadata WHERE unit_id=?', (existing['id'],)).fetchone()
                recorded_metadata = ({'kind': recorded['kind'], 'evidence': json.loads(recorded['evidence']),
                    'audience': json.loads(recorded['audience']), 'evidence_state': recorded['evidence_state']} if recorded else None)
                if recorded_metadata != metadata:
                    raise Conflict('Memory source_id already identifies different outcome metadata')
                return self._details(db, existing)
            dependencies = dict.fromkeys(source_ids)
            dependencies.update(source_versions or {})
            if binding_id:
                for read in db.execute('SELECT * FROM memory_reads WHERE binding_id=?', (binding_id,)):
                    dependencies[read['unit_id']] = read['revision']
            parents = []
            for unit_id, recorded_revision in dependencies.items():
                row = self._readable(db, owner, unit_id, binding_id)
                if recorded_revision is not None and recorded_revision != row['revision']:
                    raise Conflict('Retrieved knowledge changed; refresh context before recording derived knowledge')
                parents.append(row)
            # Private inputs are never automatically released by a global launch default.
            effective_visibility = default_visibility
            if any(row['visibility'] == 'private' for row in parents):
                effective_visibility = 'private'
            elif any(row['visibility'] == 'project' for row in parents) and effective_visibility == 'global':
                effective_visibility = 'project'
            restricted_audience = False
            for parent in parents:
                parent_metadata = db.execute('SELECT audience FROM knowledge_metadata WHERE unit_id=?', (parent['id'],)).fetchone()
                if parent_metadata and '*' not in json.loads(parent_metadata['audience']):
                    # A role-restricted input cannot be laundered through a public summary.
                    restricted_audience = True
            target_status = 'reported' if source_kind in {'observation', 'legacy', 'agent', 'assessment'} else 'accepted'
            if metadata and instruction_like(content):
                target_status, effective_visibility = 'pending', 'private'
            elif restricted_audience:
                effective_visibility = 'private'
            duplicates = db.execute('SELECT * FROM kunits WHERE owner_id=? AND content=? AND visibility=? AND status=? ORDER BY created_at,id',
                                    (owner, content, effective_visibility, target_status)).fetchall()
            for duplicate in duplicates:
                duplicate_metadata = db.execute('SELECT * FROM knowledge_metadata WHERE unit_id=?', (duplicate['id'],)).fetchone()
                normalized = ({'kind': duplicate_metadata['kind'], 'evidence': json.loads(duplicate_metadata['evidence']),
                    'audience': json.loads(duplicate_metadata['audience']), 'evidence_state': duplicate_metadata['evidence_state']} if duplicate_metadata else None)
                if normalized != metadata:
                    continue
                recorded = {(edge['source_id'], edge['source_revision']) for edge in db.execute(
                    'SELECT source_id,source_revision FROM kunit_edges WHERE unit_id=?', (duplicate['id'],))}
                supplied = {(parent['id'], parent['revision']) for parent in parents if parent['id'] != duplicate['id']}
                if recorded == supplied:
                    db.execute('INSERT INTO memory_sources VALUES (?, ?, ?, ?, ?, ?)',
                        (owner, source_id, duplicate['id'], content_hash, source_kind, self._timestamp()))
                    return self._details(db, duplicate)
            unit_id, timestamp = self.ids(), self._timestamp()
            db.execute('INSERT INTO kunits VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?)',
                (unit_id, owner, content, effective_visibility,
                 target_status, source_id, source_kind, timestamp, timestamp))
            db.execute('INSERT INTO memory_sources VALUES (?, ?, ?, ?, ?, ?)',
                       (owner, source_id, unit_id, content_hash, source_kind, timestamp))
            if metadata:
                db.execute('INSERT INTO knowledge_metadata VALUES (?, ?, ?, ?, ?, ?, ?)',
                    (unit_id, metadata['kind'], json.dumps(metadata['audience']), json.dumps(metadata['evidence']),
                     metadata['evidence_state'], profile, spec))
            for parent in parents:
                db.execute('INSERT INTO kunit_edges VALUES (?, ?, ?)', (unit_id, parent['id'], parent['revision']))
            return self._revision(db, unit_id, 'created')

    def read_unit(self, owner, unit_id, binding_id=None):
        with self.transaction(True) as db:
            row = self._readable(db, owner, unit_id, binding_id)
            self._record_read(db, binding_id, row)
            result = self._details(db, row)
            if row['owner_id'] == owner:
                result['sources'] = [dict(source) for source in db.execute(
                    'SELECT source_id,source_kind,created_at FROM memory_sources WHERE unit_id=?', (unit_id,))]
                result['derived_from'] = [dict(edge) for edge in db.execute(
                    'SELECT source_id,source_revision FROM kunit_edges WHERE unit_id=?', (unit_id,))]
            return result

    def history(self, owner, unit_id):
        with self.transaction() as db:
            row = db.execute('SELECT owner_id FROM kunits WHERE id=?', (unit_id,)).fetchone()
            if not row or row['owner_id'] != owner:
                raise Forbidden('Access denied')
            return [dict(item) for item in db.execute('SELECT * FROM kunit_revisions WHERE unit_id=? ORDER BY revision', (unit_id,))]

    def _invalidate_descendants(self, db, unit_id):
        rows = db.execute('''WITH RECURSIVE descendants(id) AS (
            SELECT unit_id FROM kunit_edges WHERE source_id=?
            UNION SELECT e.unit_id FROM kunit_edges e JOIN descendants d ON e.source_id=d.id)
            SELECT DISTINCT id FROM descendants WHERE id!=?''', (unit_id, unit_id)).fetchall()
        for item in rows:
            row = db.execute('SELECT status FROM kunits WHERE id=?', (item['id'],)).fetchone()
            if row['status'] in ACTIVE_STATES:
                db.execute("UPDATE kunits SET status='invalidated',revision=revision+1,updated_at=? WHERE id=?",
                           (self._timestamp(), item['id']))
                self._revision(db, item['id'], 'source changed; regenerate from currently authorized inputs')

    def revise(self, owner, unit_id, expected, content=None, visibility=None, retract=False):
        with self.transaction(True) as db:
            row = db.execute('SELECT * FROM kunits WHERE id=?', (unit_id,)).fetchone()
            if not row or row['owner_id'] != owner:
                raise Forbidden('Access denied')
            if row['revision'] != expected:
                raise Conflict('Knowledge changed; read its current revision before updating')
            if row['status'] == 'invalidated' and content is not None:
                raise Conflict('Regenerate invalidated knowledge as a new unit from currently authorized sources')
            new_content = content if content is not None else row['content']
            new_visibility = visibility if visibility is not None else row['visibility']
            new_status = 'retracted' if retract else row['status']
            if content is not None and content != row['content']:
                db.execute("UPDATE knowledge_metadata SET evidence_state='proposed' WHERE unit_id=?", (unit_id,))
                if instruction_like(content):
                    new_status, new_visibility = 'pending', 'private'
                elif new_status == 'pending':
                    new_status = 'reported'
            if (new_content, new_visibility, new_status) == (row['content'], row['visibility'], row['status']):
                return self._details(db, row)
            # Publication of a derived unit requires release of its private sources first.
            if new_visibility in {'project', 'global'}:
                for edge in db.execute('SELECT source_id FROM kunit_edges WHERE unit_id=?', (unit_id,)):
                    parent = self._readable(db, owner, edge['source_id'])
                    if parent['visibility'] == 'private' or (new_visibility == 'global' and parent['visibility'] != 'global'):
                        raise Forbidden('Release private source units before publishing derived knowledge')
                    source_metadata = db.execute('SELECT audience FROM knowledge_metadata WHERE unit_id=?', (edge['source_id'],)).fetchone()
                    if source_metadata and '*' not in json.loads(source_metadata['audience']):
                        raise Forbidden('Role-restricted source knowledge cannot be published through a broader summary')
            db.execute('UPDATE kunits SET content=?,visibility=?,status=?,revision=revision+1,updated_at=? WHERE id=?',
                (new_content, new_visibility, new_status, self._timestamp(), unit_id))
            self._invalidate_descendants(db, unit_id)
            db.execute('UPDATE memory_state SET policy_epoch=policy_epoch+1 WHERE id=1')
            return self._revision(db, unit_id, 'retracted' if retract else 'content or visibility changed')

    def policy_epoch(self):
        with self.transaction() as db:
            return db.execute('SELECT policy_epoch FROM memory_state WHERE id=1').fetchone()[0]

    def settings(self):
        with self.transaction() as db:
            return json.loads(db.execute('SELECT settings FROM memory_state WHERE id=1').fetchone()[0])

    def configure(self, settings):
        with self.transaction(True) as db:
            db.execute('UPDATE memory_state SET settings=? WHERE id=1', (json.dumps(settings),))
            db.execute("UPDATE memory_index_jobs SET status='pending',error=NULL")
            db.execute('UPDATE memory_state SET policy_epoch=policy_epoch+1 WHERE id=1')
        self.configuration = dict(settings)
        if not settings:
            self.embedder = None

    @staticmethod
    def _vector(values):
        values = list(values)
        if not 1 <= len(values) <= 8192 or any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
            raise OrbeHelmError('Embedding provider returned an invalid vector')
        if not any(values):
            raise OrbeHelmError('Embedding provider returned a zero vector')
        return struct.pack('<' + 'f' * len(values), *values)

    @staticmethod
    def _distance_function(index):
        """Use the native extension where supported; otherwise exact local cosine."""
        if hasattr(index, 'enable_load_extension'):
            try:
                import sqlite_vec
                index.enable_load_extension(True)
                try:
                    sqlite_vec.load(index)
                finally:
                    index.enable_load_extension(False)
                return 'vec_distance_cosine', 'sqlite-vec'
            except (ImportError, AttributeError, sqlite3.DatabaseError):
                pass
        def cosine(left, right):
            a = struct.unpack('<' + 'f' * (len(left) // 4), left)
            b = struct.unpack('<' + 'f' * (len(right) // 4), right)
            return 1 - sum(x * y for x, y in zip(a, b)) / math.sqrt(sum(x*x for x in a) * sum(y*y for y in b))
        index.create_function('memory_cosine', 2, cosine, deterministic=True)
        return 'memory_cosine', 'python-exact'

    def _check_configuration(self, db):
        current = json.loads(db.execute('SELECT settings FROM memory_state WHERE id=1').fetchone()[0])
        if current != self.configuration:
            raise OrbeHelmError('Memory embedding configuration changed; restart this memory client')

    def sync_index(self, limit=1000):
        if self.configuration.get('provider') and self.embedder is None:
            raise OrbeHelmError('The configured local embedding model must be loaded before indexing')
        with self.transaction() as db:
            self._check_configuration(db)
            jobs = [dict(row) for row in db.execute("SELECT k.* FROM kunits k JOIN memory_index_jobs j ON j.unit_id=k.id "
                                                  "WHERE j.status IN ('pending','error') ORDER BY CASE j.status WHEN 'pending' THEN 0 ELSE 1 END LIMIT ?", (limit,))]
        for row in jobs:
            error, state = None, 'keyword'
            chunks = segments(row['content']) if row['status'] in ACTIVE_STATES else ()
            vectors = []
            if chunks and self.embedder:
                try:
                    with self.search_index() as index:
                        cached = {row['content']: row['vector'] for row in index.execute(
                            'SELECT f.content,v.vector FROM vectors v JOIN knowledge_fts f ON '
                            'f.unit_id=v.unit_id AND f.revision=v.revision AND f.ordinal=v.ordinal '
                            'WHERE v.unit_id=? AND v.model=?', (row['id'], self.embedder.model_id))}
                    missing = list(dict.fromkeys(chunk for chunk in chunks if chunk not in cached))
                    fresh = [self._vector(vector) for vector in self.embedder.documents(missing)] if missing else []
                    if len(fresh) != len(missing):
                        raise OrbeHelmError('Embedding provider returned an inconsistent vector count')
                    cached.update(zip(missing, fresh))
                    vectors = [cached[chunk] for chunk in chunks]
                    if len(vectors) != len(chunks) or len({len(vector) for vector in vectors}) != 1:
                        raise OrbeHelmError('Embedding provider returned inconsistent dimensions/count')
                    state = 'ready'
                except Exception:
                    error, vectors, state = 'Embedding failed; run memory reindex after checking the local model', [], 'error'
            with self.transaction(True) as db:
                self._check_configuration(db)
                current = db.execute('SELECT revision FROM kunits WHERE id=?', (row['id'],)).fetchone()
                if not current or current['revision'] != row['revision']:
                    continue
                try:
                    with self.search_index() as index:
                        index.execute('DELETE FROM knowledge_fts WHERE unit_id=?', (row['id'],))
                        index.execute('DELETE FROM vectors WHERE unit_id=?', (row['id'],))
                        for ordinal, chunk in enumerate(chunks):
                            index.execute('INSERT INTO knowledge_fts VALUES (?, ?, ?, ?)', (row['id'], row['revision'], ordinal, chunk))
                            if vectors:
                                index.execute('INSERT INTO vectors VALUES (?, ?, ?, ?, ?)',
                                    (row['id'], row['revision'], ordinal, self.embedder.model_id, vectors[ordinal]))
                except sqlite3.DatabaseError as failure:
                    raise OrbeHelmError('Memory search index is unavailable; run oh memory reindex --rebuild-index') from failure
                db.execute('UPDATE memory_index_jobs SET status=?,error=? WHERE unit_id=? AND revision=?',
                           (state, error, row['id'], row['revision']))
        return self.status()

    def rebuild(self):
        if self.index.exists():
            if self.index.is_symlink():
                raise OrbeHelmError('Memory index must not be a symlink')
            self.index.rename(self.index.with_name(self.index.name + '.backup-' + self.ids()))
        with self.transaction(True) as db:
            db.execute("UPDATE memory_index_jobs SET status='pending',error=NULL")
        return self.finish_index()

    def finish_index(self):
        previous = None
        while True:
            result = self.sync_index()
            pending = result['index_jobs'].get('pending', 0)
            if not pending or (previous is not None and pending >= previous):
                return result
            previous = pending

    def status(self):
        with self.transaction() as db:
            counts = {row[0]: row[1] for row in db.execute('SELECT status,count(*) FROM memory_index_jobs GROUP BY status')}
            captures = {row[0]: row[1] for row in db.execute('SELECT status,count(*) FROM memory_captures GROUP BY status')}
        return {'index_jobs': counts, 'embedding_model': self.embedder.model_id if self.embedder else self.configuration.get('name'),
                'retrieval': 'hybrid' if self.embedder else 'hybrid-configured' if self.configuration.get('provider') else 'keyword-only',
                'policy_epoch': self.policy_epoch(),
                'capture_jobs': captures}

    def search(self, owner, query, limit=10, binding_id=None):
        self.sync_index()
        query_blob = None
        if self.embedder and query.strip():
            try:
                query_blob = self._vector(self.embedder.query(query))
            except Exception as error:
                raise OrbeHelmError('Local query embedding failed; check memory status/configuration') from error
        with self.transaction(True) as db:
            self._check_configuration(db)
            self._check_binding(db, owner, binding_id)
            candidates = db.execute("SELECT * FROM kunits WHERE status IN ('reported','accepted') "
                                   "ORDER BY created_at DESC,id").fetchall()
            rows = [row for row in candidates if self._eligible(db, owner, row, binding_id)]
            eligible = {row['id']: row for row in rows}
            lexical, semantic, vector_backend, snippets = [], [], None, {}
            if eligible:
                with self.search_index() as index:
                    index.execute('CREATE TEMP TABLE eligible (id TEXT PRIMARY KEY,revision INTEGER)')
                    index.executemany('INSERT INTO eligible VALUES (?, ?)', ((row['id'], row['revision']) for row in rows))
                    expression = lexical_expression(query)
                    if expression:
                        matches = index.execute('SELECT knowledge_fts.unit_id,knowledge_fts.content FROM knowledge_fts '
                            'JOIN eligible e ON e.id=knowledge_fts.unit_id AND e.revision=knowledge_fts.revision '
                            'WHERE knowledge_fts MATCH ? ORDER BY bm25(knowledge_fts),knowledge_fts.unit_id,knowledge_fts.ordinal', (expression,)).fetchall()
                        lexical = [row[0] for row in matches]
                        for unit, text in matches:
                            snippets.setdefault(unit, text)
                    if query_blob:
                        distance, vector_backend = self._distance_function(index)
                        matches = index.execute('SELECT v.unit_id,f.content FROM vectors v JOIN eligible e '
                            'ON v.unit_id=e.id AND v.revision=e.revision JOIN knowledge_fts f ON '
                            'f.unit_id=v.unit_id AND f.revision=v.revision AND f.ordinal=v.ordinal '
                            'WHERE v.model=? AND length(v.vector)=? ORDER BY ' + distance + '(v.vector, ?),v.unit_id,v.ordinal',
                            (self.embedder.model_id, len(query_blob), query_blob)).fetchall()
                        semantic = [row[0] for row in matches]
                        for unit, text in matches:
                            snippets.setdefault(unit, text)
            ranking = reciprocal_rank_fusion(lexical, semantic) if query.strip() else tuple(eligible)
            selected = [eligible[unit_id] for unit_id in ranking[:limit]]
            for row in selected:
                self._record_read(db, binding_id, row)
            jobs = db.execute("SELECT unit_id,status FROM memory_index_jobs WHERE status!='ready'").fetchall()
            pending = sum(job['unit_id'] in eligible for job in jobs)
            pending_index = sum(job['unit_id'] in eligible and job['status'] == 'pending' for job in jobs)
            return {'units': [{**self._details(db, row), 'match': snippets.get(row['id'], row['content'][:1800])} for row in selected],
                    'mode': 'hybrid' if query_blob else 'keyword-only', 'pending_embeddings': pending,
                    'vector_backend': vector_backend,
                    'pending_index_units': pending_index,
                    'policy_epoch': db.execute('SELECT policy_epoch FROM memory_state WHERE id=1').fetchone()[0]}

    def enqueue_capture(self, owner, source_id, content, default_visibility, binding_id=None):
        with self.transaction(True) as db:
            self._check_binding(db, owner, binding_id)
            sources = {row['unit_id']: row['revision'] for row in db.execute(
                'SELECT unit_id,revision FROM memory_reads WHERE binding_id=?', (binding_id,))} if binding_id else {}
            if any(self._readable(db, owner, key, binding_id)['visibility'] == 'private' for key in sources):
                default_visibility = 'private'
            db.execute("INSERT OR IGNORE INTO memory_captures VALUES (?, ?, ?, ?, 'waiting', NULL, ?)",
                       (owner, source_id, content, default_visibility, json.dumps(sources)))

    def complete_captures(self, owner, binding_id, successful=True):
        with self.transaction(True) as db:
            db.execute('UPDATE memory_captures SET status=? WHERE owner_id=? AND source_id LIKE ? AND status=?',
                       ('pending' if successful else 'failed', owner, binding_id + ':%', 'waiting'))

    def drain_captures(self, owner, binding_id=None):
        errors = 0
        with self.transaction() as db:
            rows = db.execute("SELECT * FROM memory_captures WHERE owner_id=? AND status IN ('pending','error')", (owner,)).fetchall()
        for row in rows:
            try:
                for ordinal, chunk in enumerate(segments(row['content'])):
                    self.put(owner, chunk, 'capture:' + row['source_id'] + ':' + str(ordinal), row['visibility'],
                             source_kind='observation', source_versions=json.loads(row['sources']))
            except (OrbeHelmError, ValueError):
                with self.transaction(True) as db:
                    db.execute("UPDATE memory_captures SET status='error',error='Capture requires retry with authorized source context' "
                               'WHERE owner_id=? AND source_id=?', (owner, row['source_id']))
                errors += 1
                continue
            with self.transaction(True) as db:
                db.execute("UPDATE memory_captures SET status='done',error=NULL WHERE owner_id=? AND source_id=?", (owner, row['source_id']))
        return {'retried': len(rows), 'errors': errors}
