"""Additive material groups, with a bounded union of separately owned retrievals."""
from itertools import zip_longest
from fastapi import HTTPException


def selected_ids(primary, ids):
    if len(ids) > 5 or len(set(ids)) != len(ids) or any(type(i) is not int or i <= 0 for i in ids):
        raise ValueError('Choose up to five distinct positive material IDs.')
    if ids and primary is not None and primary not in ids:
        raise ValueError('The primary material must be selected.')
    return ids or ([primary] if primary else [])


def require_materials(cursor, student, course, ids):
    for source in ids:
        cursor.execute('''SELECT s.status FROM sources s JOIN courses c ON c.course_id=s.course_id
            WHERE s.source_id=%s AND s.course_id=%s AND s.owner_student_id=%s AND c.owner_student_id=%s''',
            (source, course, student, student))
        row = cursor.fetchone()
        status = row.get('status') if isinstance(row, dict) else row[0] if row else None
        if row is None: raise HTTPException(404, 'Material not found.')
        if status not in ('success', 'partial', 'ready'): raise HTTPException(409, 'A selected material is not ready.')


def interleave(groups, limit):
    return [item for row in zip_longest(*groups) for item in row if item is not None][:limit]


class GroupRetriever:
    def __init__(self, retriever, owner, ids):
        self.base, self.owner, self.ids = retriever, owner, ids

    def _many(self, method, args, kwargs, default):
        limit = max(len(self.ids), min(96, kwargs.get('limit', kwargs.get('top_k', default))))
        options = {**kwargs, 'owner_student_id': self.owner}
        return interleave([getattr(self.base, method)(*args, **{**options, 'source_id': source}) for source in self.ids], limit)

    def search(self, query, **kwargs): return self._many('search', [query], kwargs, 10)
    def overview(self, **kwargs): return self._many('overview', [], kwargs, 12)
    def concept_context(self, query, **kwargs): return self._many('concept_context', [query], kwargs, 6)
    def document_context(self, **kwargs):
        limit = min(96, kwargs.get('limit', 96))
        parts = [self.base.document_context(**{**kwargs, 'source_id': source, 'owner_student_id': self.owner}) for source in self.ids]
        rows, chars = [], 0
        for item in interleave([part['results'] for part in parts], limit):
            if chars + len(item.chunk.content) <= 80000:
                rows.append(item); chars += len(item.chunk.content)
        complete = all(part['all_chunks_included'] for part in parts) and len(rows) == sum(len(part['results']) for part in parts)
        return {'results': rows, 'locations_available': sum(p['locations_available'] for p in parts),
                'locations_selected': len(rows), 'all_chunks_included': complete,
                'scope': 'all_available_locations' if complete else 'sampled_locations'}
