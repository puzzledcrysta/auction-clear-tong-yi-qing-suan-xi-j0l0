from decimal import Decimal
from app.errors import DataError


def proof_index(accepted_row):
    """把清算依据列表归并为 {指标: (值, 单位)}，便于逐项比对。"""
    return {item['metric']: (item['value'], item['unit']) for item in accepted_row['proof']}


def awards(accepted_row):
    """提取每个买家的获配数量，保留价时顺序（与 proof 中的顺序一致）。"""
    result = []
    for item in accepted_row['proof']:
        metric = item['metric']
        if metric.endswith(' 获配'):
            result.append({'bidder': metric[:-len(' 获配')],
                           'quantity': item['value'], 'unit': item['unit']})
    return result


def metric(accepted_row, label):
    value, unit = proof_index(accepted_row)[label]
    return {'value': value, 'unit': unit}


def accepted_index(result):
    return {row['key']: row for row in result['accepted']}


def finding_signature(row):
    """隔离/抑制记录的语义指纹：不含时间戳，只看来源行判定。"""
    return (row['line'], row['key'], row['code'], row['detail'], tuple(row['raw']))


def finding_buckets(result):
    # stages() 用 rejected/quality.suppressed，持久化批次用 quarantine/suppressed。
    quarantined = result.get('quarantine', result.get('rejected', []))
    suppressed = result.get('suppressed', result.get('quality', {}).get('suppressed', []))
    return (sorted(map(finding_signature, quarantined)),
            sorted(map(finding_signature, suppressed)))


def assert_same_scope(old, new, target):
    """划清更正影响：只允许指定场次变化，同期别其他来源必须逐行一致。"""
    old_rows, new_rows = accepted_index(old), accepted_index(new)
    # 目标场次更正后无法清算属于更正内容无效，优先于场次集合等越界判定。
    if target not in new_rows:
        raise DataError('CORRECTION_INVALID', f'更正后的场次 {target} 未能清算，请检查来源')
    if set(old_rows) != set(new_rows):
        raise DataError('CORRECTION_SCOPE',
                        f'场次集合变化：新增 {sorted(set(new_rows)-set(old_rows))}，'
                        f'缺失 {sorted(set(old_rows)-set(new_rows))}')
    changed = [key for key in old_rows if key != target and old_rows[key]['amount'] != new_rows[key]['amount']]
    if changed:
        raise DataError('CORRECTION_SCOPE', f'同期别非目标场次金额被改动：{changed}')
    for key in old_rows:
        if key == target:
            continue
        if proof_index(old_rows[key]) != proof_index(new_rows[key]):
            raise DataError('CORRECTION_SCOPE', f'同期别非目标场次 {key} 的配给依据被改动')
    old_findings, new_findings = finding_buckets(old), finding_buckets(new)
    if old_findings != new_findings:
        raise DataError('CORRECTION_SCOPE', '隔离或抑制的来源行发生变化，超出本次更正范围')


def delta(new_value, old_value):
    return str(Decimal(new_value) - Decimal(old_value))


def build_lines(old, new):
    """逐场构造冲销明细：目标场次一行，记录金额、获配与统一清算价的前后对照。"""
    old_rows, new_rows = accepted_index(old), accepted_index(new)
    target_changes = []
    for key in old_rows:
        before, after = old_rows[key], new_rows[key]
        if before['amount'] == after['amount'] and proof_index(before) == proof_index(after):
            continue
        old_awards = {item['bidder']: item for item in awards(before)}
        new_awards = {item['bidder']: item for item in awards(after)}
        bidders = sorted(set(old_awards) | set(new_awards))
        award_changes = []
        for bidder in bidders:
            old_qty = old_awards.get(bidder, {'quantity': '0', 'unit': '件'})
            new_qty = new_awards.get(bidder, {'quantity': '0', 'unit': '件'})
            award_changes.append({
                'bidder': bidder,
                'old_quantity': old_qty['quantity'],
                'new_quantity': new_qty['quantity'],
                'quantity_delta': delta(new_qty['quantity'], old_qty['quantity']),
                'unit': new_qty['unit'],
            })
        old_clearing, new_clearing = metric(before, '统一清算价'), metric(after, '统一清算价')
        target_changes.append({
            'key': key,
            'line': after['line'],
            'old_amount': before['amount'],
            'new_amount': after['amount'],
            'reversal_amount': delta(after['amount'], before['amount']),
            'old_clearing': old_clearing,
            'new_clearing': new_clearing,
            'clearing_delta': delta(new_clearing['value'], old_clearing['value']),
            'award_changes': award_changes,
            'old_proof': before['proof'],
            'new_proof': after['proof'],
            'book_check': None,
        })
    return target_changes


def _book_code(book, key, amount):
    reference = book.get(key)
    if reference is None:
        return None, None, 'MISSING_BOOK'
    value, line = reference
    code = 'MATCH' if Decimal(value) == Decimal(amount) else 'AMOUNT_DELTA'
    return str(value), line, code


def attach_book_checks(lines, registered_book):
    """登记时按当时外账同时核对原签核金额与更正后金额，留作发布前证据。"""
    for line in lines:
        old_value, old_line, old_code = _book_code(registered_book, line['key'], line['old_amount'])
        new_value, new_line, new_code = _book_code(registered_book, line['key'], line['new_amount'])
        line['book_check'] = {
            'registered_old': {'reference': old_value, 'book_line': old_line, 'code': old_code},
            'registered_new': {'reference': new_value, 'book_line': new_line, 'code': new_code},
            'publish': None,
            'passed': False,
        }


def evaluate_publish_gate(lines, current_book):
    """发布闸口：外账按场次核对的是更正后金额；原签核金额仅留痕，不参与放行。"""
    failures = []
    for line in lines:
        value, book_line, code = _book_code(current_book, line['key'], line['new_amount'])
        check = {'reference': value, 'book_line': book_line, 'code': code,
                 'expected_new_amount': line['new_amount']}
        line['book_check']['publish'] = check
        line['book_check']['passed'] = code == 'MATCH'
        if code != 'MATCH':
            failures.append({'key': line['key'], 'code': code})
    return failures
