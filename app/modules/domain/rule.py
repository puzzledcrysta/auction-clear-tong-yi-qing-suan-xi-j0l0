from collections import defaultdict
from decimal import Decimal as D
from app.errors import DataError
from .values import whole, number, parts


def evaluate(row):
    offered = whole(row['可售数量'], 1, 10**6)
    reserve = number(row['底价元'], 0, 10**6)
    events = defaultdict(dict)
    for raw in parts(row['报价事件']):
        fields = raw.split(':')
        if len(fields) != 5:
            raise DataError('AUCTION_FORMAT','报价事件须包含买家、序号、时点、价格、数量')
        bidder, order, tick, price, quantity = fields
        if not bidder:
            raise DataError('AUCTION_FORMAT','买家编号为空')
        revision = whole(order, 1, 10**9)
        demand = whole(quantity, 0, 10**6)
        event = (whole(tick, 0, 10**9), number(price, 0, 10**6), demand)
        if revision in events[bidder] and events[bidder][revision] != event:
            raise DataError('AUCTION_CONFLICT', f'{bidder} 的修订 {revision} 报单互相矛盾')
        events[bidder][revision] = event
    qualified, proof = [], []
    for bidder, revisions in sorted(events.items()):
        tick, price, demand = revisions[max(revisions)]
        if not demand or price < reserve:
            proof.append((bidder,'撤单' if not demand else '低于底价',''))
        else:
            qualified.append((-price,tick,bidder,demand))
    sold = 0
    clearing = reserve
    for negative_price, _, bidder, demand in sorted(qualified):
        award = min(offered-sold,demand)
        sold += award
        if award:
            clearing = -negative_price
        proof.append((f'{bidder} 获配',award,'件'))
    if sold < offered:
        clearing = reserve
    proof += [('统一清算价',clearing,'元'),('成交总数',sold,'件'),('余量',offered-sold,'件')]
    return clearing*sold, proof
