from decimal import Decimal
import pytest
from app.errors import DataError
from app.modules.domain.rule import evaluate


def test_partial_award(cases):
    actual, proof = evaluate(cases['partial_award'])
    assert actual == Decimal('120')
    assert Decimal(str(dict((label, value) for label, value, _ in proof)['乙 获配'])) == Decimal('3')


def test_time_before_identifier(cases):
    # TRAP-19
    actual, proof = evaluate(cases['time_before_identifier'])
    assert actual == Decimal('36')
    assert Decimal(str(dict((label, value) for label, value, _ in proof)['乙 获配'])) == Decimal('2')


def test_cancel_before_clear(cases):
    actual, proof = evaluate(cases['cancel_before_clear'])
    assert actual == Decimal('45')
    assert str(dict((label, value) for label, value, _ in proof)['甲']) == '撤单'


def test_unsold_at_reserve(cases):
    actual, proof = evaluate(cases['unsold_at_reserve'])
    assert actual == Decimal('12.5')
    assert Decimal(str(dict((label, value) for label, value, _ in proof)['余量'])) == Decimal('5')


def test_no_award(cases):
    actual, proof = evaluate(cases['no_award'])
    assert actual == Decimal('0')
    assert Decimal(str(dict((label, value) for label, value, _ in proof)['成交总数'])) == Decimal('0')


def test_revised_bid(cases):
    actual, proof = evaluate(cases['revised_bid'])
    assert actual == Decimal('40')
    assert Decimal(str(dict((label, value) for label, value, _ in proof)['统一清算价'])) == Decimal('10')


def test_same_rev_conflict(cases):
    # TRAP-14
    with pytest.raises(DataError) as error:
        evaluate(cases['same_rev_conflict'])
    assert error.value.code == 'AUCTION_CONFLICT'


def test_bad_record(cases):
    with pytest.raises(DataError) as error:
        evaluate(cases['bad_record'])
    assert error.value.code == 'AUCTION_FORMAT'


def test_negative_demand(cases):
    with pytest.raises(DataError) as error:
        evaluate(cases['negative_demand'])
    assert error.value.code == 'RANGE'
