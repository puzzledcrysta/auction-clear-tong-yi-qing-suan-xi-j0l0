import json
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from app.errors import DataError
from app.settings import RULE_VERSION
from app.pipeline import stages
from app.modules.reconcile.ledger import ledger
from app.modules.review.decisions import timeline
from app.modules.runs.repository import fetch
from . import repository
from .impact import (accepted_index, assert_same_scope, build_lines,
                     attach_book_checks, evaluate_publish_gate)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _book_maps(book_bytes):
    return {key: (str(value), line) for key, (value, line) in ledger(book_bytes).items()}


def _build_voucher(run_id, target, note, old, new, book_bytes):
    lines = build_lines(old, new)
    if not lines:
        raise DataError('CORRECTION_NOCHANGE', f'场次 {target} 更正后与原签核结果一致，无需冲销')
    registered_book = _book_maps(book_bytes)
    attach_book_checks(lines, registered_book)
    review_history = timeline(run_id)
    old_rows = accepted_index(old)
    total_reversal = sum((Decimal(line['reversal_amount']) for line in lines), Decimal(0))
    return {
        'correction_id': None,
        'run_id': run_id,
        'target': target,
        'reason': note,
        'rule_version': RULE_VERSION,
        'status': '待发布',
        'created': None,
        'published_at': None,
        'scope': {
            'target': target,
            'changed_sessions': [line['key'] for line in lines],
            'unchanged_sessions': [key for key in old_rows if key not in {line['key'] for line in lines}],
            'delimitation': '仅登记场次的更正参与冲销；同期别其他场次来源逐行一致，不计入本次冲销',
        },
        'lines': lines,
        'total_reversal': str(total_reversal),
        'reconciliation_passed': False,
        'original_review': review_history,
        'registered_book_sha256': sha256(book_bytes).hexdigest(),
        'book_sha256': sha256(book_bytes).hexdigest(),
    }


def register(run_id, target, note, source_bytes, book_bytes):
    note = note.strip()
    if not note:
        raise DataError('REVIEW_NOTE', '晚到更正须填写更正原因')
    stored = fetch(run_id)
    reviews = timeline(run_id)
    if not reviews or reviews[0]['decision'] != '确认':
        raise DataError('CORRECTION_REVIEW', '只有最新结论为“确认”的已签核批次才能登记更正')
    old = json.loads(stored['result'])
    if target not in accepted_index(old):
        raise DataError('CORRECTION_TARGET', f'批次 {run_id} 中没有可清算的场次 {target}')
    source_sha = sha256(source_bytes).hexdigest()
    book_sha = sha256(book_bytes).hexdigest()
    existing = repository.find_by_fingerprint(run_id, target, source_sha, book_sha)
    if existing is not None:
        # 同一更正重试：直接回送既有冲销单，绝不重复生成。
        return json.loads(existing['voucher']), False
    new = stages(source_bytes)
    assert_same_scope(old, new, target)
    voucher = _build_voucher(run_id, target, note, old, new, book_bytes)
    created = _now()
    correction_id = sha256(
        f'{RULE_VERSION}:correction:{run_id}:{target}:{source_sha}:{book_sha}'.encode()).hexdigest()
    voucher.update(correction_id=correction_id, created=created)
    record = {'id': correction_id, 'run_id': run_id, 'target': target, 'note': note,
              'source': source_bytes, 'book': book_bytes, 'source_sha256': source_sha,
              'book_sha256': book_sha, 'status': '待发布', 'voucher': voucher, 'created': created}
    saved = repository.save(record)
    return json.loads(saved['voucher']), True


def recheck_and_publish(correction_id, book_bytes=None):
    stored = repository.get(correction_id)
    voucher = json.loads(stored['voucher'])
    if stored['published'] is not None:
        return voucher, False
    book_bytes = stored['book'] if book_bytes is None else book_bytes
    book_sha = sha256(book_bytes).hexdigest()
    # 用最新外账按场次重核更正后金额；闸口不通过则保持待发布、不改动旧版签核。
    book_map = _book_maps(book_bytes)
    failures = evaluate_publish_gate(voucher['lines'], book_map)
    if failures:
        # 不通过时不落库：已登记证据保持原样，结算员补账后可重试同一冲销单。
        raise DataError('VOUCHER_BLOCKED',
                        f'外账核对未通过的场次：{json.dumps(failures, ensure_ascii=False)}')
    voucher['reconciliation_passed'] = True
    voucher['book_sha256'] = book_sha
    published_at = _now()
    voucher['status'] = '已发布'
    voucher['published_at'] = published_at
    updated = repository.mark_published(correction_id, published_at, voucher)
    return json.loads(updated['voucher']), True


def detail(correction_id):
    return json.loads(repository.get(correction_id)['voucher'])


def list_corrections(run_id):
    return repository.list_for_run(run_id)
