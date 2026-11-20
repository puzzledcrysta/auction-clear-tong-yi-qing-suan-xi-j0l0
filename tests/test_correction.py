import csv
from io import StringIO
import pytest
from app.modules.correction import repository
from app.modules.correction.service import register
from app.settings import KEY, UNIT

HEADER = ['竞价场次', '修订号', '提交时间', '可售数量', '底价元', '报价事件', '原始备注']
WHEN = '2026-11-18T09:30:00+08:00'


def csv_text(rows):
    out = StringIO(newline='')
    writer = csv.writer(out)
    writer.writerow(HEADER)
    for row in rows:
        writer.writerow([row.get(field, '') for field in HEADER])
    return out.getvalue()


def book_text(pairs):
    out = StringIO(newline='')
    writer = csv.writer(out)
    writer.writerow([KEY, f'外部记录值({UNIT})'])
    for key, value in pairs:
        writer.writerow([key, value])
    return out.getvalue()


def session(key, offered, reserve, events, revision=1, note=''):
    return {'竞价场次': key, '修订号': revision, '提交时间': WHEN, '可售数量': offered,
            '底价元': reserve, '报价事件': events, '原始备注': note}


OLD_A = session('A001', '10', '5', '甲:1:1:10:4;乙:1:2:8:6')
# 乙报价由 8 抬到 10：最低获配价（统一清算价）由 8 升到 10，甲4乙6 配给不变，总额由 80 变 100。
NEW_A = session('A001', '10', '5', '甲:1:1:10:4;乙:1:2:10:6')
B = session('B002', '5', '5', '甲:1:1:10:3;乙:1:2:8:4')
OLD_SOURCE = csv_text([OLD_A, B])
# B002：清算价 8、甲3乙2、总额 40，更正前后不变。
NEW_SOURCE = csv_text([NEW_A, B])
OLD_BOOK = book_text([('A001', '80'), ('B002', '40')])
NEW_BOOK = book_text([('A001', '100'), ('B002', '40')])


@pytest.fixture
def signed(client):
    run = client.post('/api/runs', json={'data': OLD_SOURCE, 'book': OLD_BOOK}).json()
    run_id = run['manifest']['run_id']
    review = client.post(f'/api/review/{run_id}',
                         json={'version': 0, 'decision': '确认', 'note': '外账逐场核对通过'})
    assert review.status_code == 200
    return run_id


def correction(client, run_id, source=NEW_SOURCE, book=OLD_BOOK, target='A001', note='买家甲报单数量误填'):
    return client.post(f'/api/corrections/{run_id}',
                       json={'target': target, 'note': note, 'data': source, 'book': book})


def test_register_builds_per_session_voucher(client, signed):
    response = correction(client, signed)
    assert response.status_code == 200
    body = response.json()
    assert body['created'] is True
    voucher = body['voucher']
    assert voucher['status'] == '待发布' and voucher['target'] == 'A001'
    line, = voucher['lines']
    assert (line['key'], line['old_amount'], line['new_amount'], line['reversal_amount']) == \
           ('A001', '80', '100', '20')
    assert (line['old_clearing']['value'], line['new_clearing']['value'], line['clearing_delta']) == \
           ('8', '10', '2')
    awards = {item['bidder']: item for item in line['award_changes']}
    # 配给数量未变，但统一清算价变化连带改变每个买家的应付金额。
    assert (awards['甲']['old_quantity'], awards['甲']['new_quantity'], awards['甲']['quantity_delta']) == \
           ('4', '4', '0')
    assert awards['乙']['quantity_delta'] == '0'
    assert voucher['total_reversal'] == '20'
    # 同场其他买家的获配与统一清算价变化逐场列出，同期别 B002 明确划在冲销之外。
    assert voucher['scope']['changed_sessions'] == ['A001']
    assert voucher['scope']['unchanged_sessions'] == ['B002']


def test_scope_rejects_changes_outside_target_session(client, signed):
    moved_b = dict(B, 报价事件='甲:1:1:10:5;乙:1:2:8:4')
    response = correction(client, signed, source=csv_text([NEW_A, moved_b]))
    assert (response.status_code, response.json()['code']) == (422, 'CORRECTION_SCOPE')


def test_scope_rejects_changed_quarantine_rows(client, signed):
    # 同期别隔离行的任何变化都不属于这次更正。
    bad = session('A999', '5', '10', '甲:1:2:20')
    moved = dict(bad, 报价事件='甲:1:2:20:3')
    source_with_bad = csv_text([OLD_A, B, bad])
    client.post('/api/runs', json={'data': source_with_bad, 'book': OLD_BOOK})
    run_id = client.get('/api/runs').json()[0]['id']
    client.post(f'/api/review/{run_id}', json={'version': 0, 'decision': '确认', 'note': '已知隔离'})
    response = correction(client, run_id, source=csv_text([NEW_A, B, moved]))
    assert (response.status_code, response.json()['code']) == (422, 'CORRECTION_SCOPE')


def test_no_change_correction_rejected(client, signed):
    response = correction(client, signed, source=OLD_SOURCE)
    assert (response.status_code, response.json()['code']) == (422, 'CORRECTION_NOCHANGE')


def test_target_must_belong_to_run(client, signed):
    response = correction(client, signed, target='NOPE')
    assert (response.status_code, response.json()['code']) == (422, 'CORRECTION_TARGET')


def test_unsigned_run_cannot_correct(client):
    run_id = client.post('/api/runs', json={'data': OLD_SOURCE, 'book': OLD_BOOK}).json()['manifest']['run_id']
    response = correction(client, run_id)
    assert (response.status_code, response.json()['code']) == (422, 'CORRECTION_REVIEW')


def test_retry_same_correction_never_duplicates(client, signed):
    first = correction(client, signed).json()['voucher']
    second = correction(client, signed, note='买家甲报单数量误填').json()
    assert second['created'] is False and second['voucher']['correction_id'] == first['correction_id']
    assert len(client.get(f'/api/corrections/{signed}').json()['corrections']) == 1


def test_different_book_opens_new_correction(client, signed):
    first = correction(client, signed).json()['voucher']
    second = correction(client, signed, book=NEW_BOOK).json()['voucher']
    assert second['correction_id'] != first['correction_id']
    assert len(client.get(f'/api/corrections/{signed}').json()['corrections']) == 2


def test_target_is_part_of_idempotency_key(client, signed):
    # 只改 B002 的来源，登记目标为 B002；与 A001 更正互不影响，各自独立编号。
    moved_b = dict(B, 报价事件='甲:1:1:10:5;乙:1:2:8:4')
    only_b = csv_text([OLD_A, moved_b])
    a_voucher = correction(client, signed).json()['voucher']
    response = correction(client, signed, target='B002', source=only_b)
    assert response.status_code == 200 and response.json()['created'] is True
    b_voucher = response.json()['voucher']
    assert b_voucher['correction_id'] != a_voucher['correction_id']
    assert [line['key'] for line in b_voucher['lines']] == ['B002']
    assert len(client.get(f'/api/corrections/{signed}').json()['corrections']) == 2


def test_publish_blocked_until_book_reconciles_per_session(client, signed):
    voucher = correction(client, signed).json()['voucher']
    cid = voucher['correction_id']
    blocked = client.post(f'/api/correction/{cid}/publish', json={})
    assert (blocked.status_code, blocked.json()['code']) == (422, 'VOUCHER_BLOCKED')
    detail = client.get(f'/api/correction/{cid}').json()
    assert detail['status'] == '待发布'
    check = detail['lines'][0]['book_check']
    # 登记时外账仍是旧值：原签核金额匹配，更正后金额形成 AMOUNT_DELTA。
    assert check['registered_old']['code'] == 'MATCH'
    assert check['registered_new']['code'] == 'AMOUNT_DELTA'
    # 补登外账后按场次重核更正后金额，通过才允许发布。
    published = client.post(f'/api/correction/{cid}/publish', json={'book': NEW_BOOK})
    assert published.status_code == 200 and published.json()['published'] is True
    body = published.json()['voucher']
    assert body['status'] == '已发布'
    assert body['lines'][0]['book_check']['publish']['code'] == 'MATCH'
    again = client.post(f'/api/correction/{cid}/publish', json={'book': NEW_BOOK})
    assert again.status_code == 200 and again.json()['published'] is False


def test_publish_requires_every_session_to_match(client, signed):
    cid = correction(client, signed).json()['voucher']['correction_id']
    # 外账缺目标场次：更正后金额无法逐场核对，发布闸口拒绝。
    missing = book_text([('B002', '40')])
    blocked = client.post(f'/api/correction/{cid}/publish', json={'book': missing})
    assert blocked.status_code == 422 and blocked.json()['code'] == 'VOUCHER_BLOCKED'
    detail = client.get(f'/api/correction/{cid}').json()
    # 被拒绝后不落库，登记证据仍保留原始外账核对结果。
    assert detail['lines'][0]['book_check']['publish'] is None
    # 金额不一致同样不放行。
    wrong = client.post(f'/api/correction/{cid}/publish', json={'book': book_text([('A001', '99')])})
    assert wrong.status_code == 422 and wrong.json()['code'] == 'VOUCHER_BLOCKED'


def test_save_failure_keeps_original_review_and_run(client, signed, monkeypatch):
    import sqlite3
    def boom(record):
        raise sqlite3.OperationalError('disk I/O error')
    monkeypatch.setattr(repository, 'save', boom)
    with pytest.raises(sqlite3.OperationalError):
        register(signed, 'A001', '晚到更正', NEW_SOURCE.encode(), OLD_BOOK.encode())
    assert client.get(f'/api/corrections/{signed}').json()['corrections'] == []
    reviews = client.get(f'/api/review/{signed}').json()
    assert [item['version'] for item in reviews] == [1] and reviews[0]['decision'] == '确认'
    run = client.get(f'/api/runs/{signed}').json()
    assert {row['key']: row['amount'] for row in run['accepted']} == {'A001': '80', 'B002': '40'}


def test_original_signed_amount_and_basis_remain_queryable(client, signed):
    voucher = correction(client, signed).json()['voucher']
    line = voucher['lines'][0]
    old_metrics = {item['metric']: item['value'] for item in line['old_proof']}
    assert old_metrics['统一清算价'] == '8' and old_metrics['成交总数'] == '10'
    assert voucher['original_review'][0]['decision'] == '确认'
    # 原批次结果未被改写。
    run = client.get(f'/api/runs/{signed}').json()
    original = next(row for row in run['accepted'] if row['key'] == 'A001')
    assert original['amount'] == '80'


def test_correction_invalid_when_target_no_longer_clears(client, signed):
    broken = dict(NEW_A, 报价事件='甲:1:2:20')
    response = correction(client, signed, source=csv_text([broken, B]))
    assert (response.status_code, response.json()['code']) == (422, 'CORRECTION_INVALID')


def test_correction_can_reallocate_other_bidders_in_same_session(client, signed):
    # 甲需求量由 4 增到 7：同场乙的获配被挤到 3，清算价不变，逐场列出每个买家的数量调整。
    moved_a = session('A001', '10', '5', '甲:1:1:10:7;乙:1:2:8:6')
    response = correction(client, signed, source=csv_text([moved_a, B]))
    assert response.status_code == 200
    line, = response.json()['voucher']['lines']
    awards = {item['bidder']: item for item in line['award_changes']}
    assert (awards['甲']['old_quantity'], awards['甲']['new_quantity'], awards['甲']['quantity_delta']) == \
           ('4', '7', '3')
    assert (awards['乙']['old_quantity'], awards['乙']['new_quantity'], awards['乙']['quantity_delta']) == \
           ('6', '3', '-3')
    assert (line['old_clearing']['value'], line['new_clearing']['value']) == ('8', '8')
    # 总额变化 = 清算价 8 × (总获配仍为 10)，此处保持 80；冲销金额为 0 但获配仍逐场留痕。
    assert line['reversal_amount'] == '0'


def test_concurrent_retries_create_one_voucher(client, signed):
    from concurrent.futures import ThreadPoolExecutor
    payload = {'target': 'A001', 'note': '买家甲报单数量误填', 'data': NEW_SOURCE, 'book': OLD_BOOK}
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(
            lambda _: client.post(f'/api/corrections/{signed}', json=payload), range(4)))
    assert all(item.status_code == 200 for item in responses)
    ids = {item.json()['voucher']['correction_id'] for item in responses}
    assert len(ids) == 1
    assert len(client.get(f'/api/corrections/{signed}').json()['corrections']) == 1


def test_note_is_required(client, signed):
    response = client.post(f'/api/corrections/{signed}',
                           json={'target': 'A001', 'note': '   ', 'data': NEW_SOURCE, 'book': OLD_BOOK})
    assert (response.status_code, response.json()['code']) == (422, 'REVIEW_NOTE')


def test_export_carries_correction_reference_without_mutating_history(client, signed):
    correction(client, signed)
    export = client.get(f'/api/export/{signed}').json()
    assert export['corrections'][0]['target'] == 'A001'
    assert export['review'][0]['version'] == 1
    assert export['results']  # 原结果仍在证据包内


def test_unknown_correction_is_404(client):
    response = client.get('/api/correction/deadbeef')
    assert (response.status_code, response.json()['code']) == (404, 'VOUCHER_UNKNOWN')


def test_routes_and_tab_registered(client):
    page = client.get('/').text
    assert '晚到更正' in page and 'correction' in page
    schema = client.get('/openapi.json').json()
    assert '/api/corrections/{run_id}' in schema['paths']
    assert '/api/correction/{correction_id}/publish' in schema['paths']


def test_book_defaults_to_run_ledger_when_omitted(client, signed):
    payload = {'target': 'A001', 'note': '乙报价晚到更正', 'data': NEW_SOURCE}
    response = client.post(f'/api/corrections/{signed}', json=payload)
    assert response.status_code == 200
    voucher = response.json()['voucher']
    import hashlib
    assert voucher['registered_book_sha256'] == hashlib.sha256(OLD_BOOK.encode()).hexdigest()
    # 缺省外账即旧账：原金额 MATCH、更正后金额 AMOUNT_DELTA。
    check = voucher['lines'][0]['book_check']
    assert check['registered_old']['code'] == 'MATCH'
    assert check['registered_new']['code'] == 'AMOUNT_DELTA'


def test_missing_source_is_clean_422(client, signed):
    response = client.post(f'/api/corrections/{signed}',
                           json={'target': 'A001', 'note': '乙报价晚到更正'})
    assert (response.status_code, response.json()['code']) == (422, 'REQUIRED')
    assert client.get(f'/api/corrections/{signed}').json()['corrections'] == []


def test_malformed_inputs_persist_nothing(client, signed):
    bad_csv = client.post(f'/api/corrections/{signed}',
                          json={'target': 'A001', 'note': 'x', 'data': '"unterminated'})
    assert (bad_csv.status_code, bad_csv.json()['code']) == (422, 'CSV')
    bad_book = client.post(f'/api/corrections/{signed}',
                           json={'target': 'A001', 'note': 'x', 'data': NEW_SOURCE,
                                 'book': 'a,b,c\n1,2,3'})
    assert (bad_book.status_code, bad_book.json()['code']) == (422, 'HEADER')
    assert client.get(f'/api/corrections/{signed}').json()['corrections'] == []
