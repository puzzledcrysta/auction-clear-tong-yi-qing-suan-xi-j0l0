import json
from app.errors import DataError
from app.store import connection
from app.modules.runs.repository import lookup


def get_db(db, correction_id):
    row = db.execute('SELECT * FROM corrections WHERE id=?', (correction_id,)).fetchone()
    if row is None:
        raise DataError('VOUCHER_UNKNOWN', '没有此更正记录', 404)
    return row


def get(correction_id):
    with connection() as db:
        return get_db(db, correction_id)


def list_for_run(run_id):
    with connection() as db:
        lookup(db, run_id)
        rows = db.execute(
            'SELECT id,run_id,target,status,created,published FROM corrections '
            'WHERE run_id=? ORDER BY created DESC,id DESC', (run_id,)).fetchall()
        return [dict(row) for row in rows]


def find_by_fingerprint(run_id, target, source_sha256, book_sha256):
    with connection() as db:
        row = db.execute(
            'SELECT * FROM corrections WHERE run_id=? AND target=? '
            'AND source_sha256=? AND book_sha256=?',
            (run_id, target, source_sha256, book_sha256)).fetchone()
        return dict(row) if row is not None else None


def save(record):
    """整笔事务写入；任何异常都会回滚，runs/reviews 旧版签核保持原样。"""
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute(
            'INSERT OR IGNORE INTO corrections '
            '(id,run_id,target,note,source,book,source_sha256,book_sha256,status,voucher,created,published) '
            'VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
            (record['id'], record['run_id'], record['target'], record['note'],
             record['source'], record['book'], record['source_sha256'], record['book_sha256'],
             record['status'], json.dumps(record['voucher'], ensure_ascii=False),
             record['created'], record.get('published')))
        return get_db(db, record['id'])


def mark_published(correction_id, published_at, voucher):
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row = get_db(db, correction_id)
        if row['published'] is not None:
            return row
        db.execute('UPDATE corrections SET status=?, published=?, voucher=? WHERE id=?',
                   ('已发布', published_at, json.dumps(voucher, ensure_ascii=False), correction_id))
        return get_db(db, correction_id)
