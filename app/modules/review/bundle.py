import json
from app.modules.runs.service import get
from app.modules.correction.repository import list_for_run
from .decisions import timeline


def bundle(run_id):
    history = timeline(run_id)
    run = get(run_id)
    # The export carries source line evidence and the applicable decision version.
    # 晚到更正只追加引用，原批次结果与签核时间线保持不可变。
    return json.dumps({'manifest':run['manifest'],'counts':run['counts'],'results':run['accepted'],
                       'quarantine':run['quarantine'],'suppressed':run['suppressed'],
                       'reconciliation':run['book'],'review':history,
                       'corrections':list_for_run(run_id)},ensure_ascii=False,indent=2)
