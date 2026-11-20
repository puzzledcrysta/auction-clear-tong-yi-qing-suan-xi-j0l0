import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_ROOT = ROOT / 'sample_data'
DB = Path(os.getenv('WORKBENCH_DB', str(ROOT/'state/ledger.sqlite3')))
TITLE = '统一清算席'
SLUG = 'auction-clear'
KEY = '竞价场次'
FIELDS = ('可售数量', '底价元', '报价事件')
ROLE = '再生资源交易市场结算员'
UNIT = '元'
RULE_VERSION = 'auction-clear-1.0'
SIGNATURE = '成交配给'
TABS = {'intake': '场次报单', 'contract': '报价字段', 'quality': '争议报单', 'domain': '竞价清算', 'reconcile': '结算清单', 'runs': '交易批次', 'review': '市场签核', 'correction': '晚到更正'}
