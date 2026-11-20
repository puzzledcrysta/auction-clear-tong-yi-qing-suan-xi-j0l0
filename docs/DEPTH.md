# 统一清算席业务与测试登记

- 规模：中型
- 使用者：再生资源交易市场结算员
- 核心规则：先采信每个买家的最终报单与撤单，按价时顺序配给，所有获配数量以同一清算价结算。

## 功能模块

| 模块 | 使用者动作 | 入口 | 核心文件 | 测试 |
|---|---|---|---|---|
| M1 场次报单 | 检查编码、字段宽度和来源行 | `POST /api/intake` | `app/modules/intake/service.py` | `tests/test_intake.py` |
| M2 报价字段 | 归一修订、业务键和偏移时间 | `POST /api/contract` | `app/modules/contract/service.py` | `tests/test_contract.py` |
| M3 争议报单 | 定位重复、被替代与矛盾来源 | `POST /api/quality` | `app/modules/quality/versions.py` | `tests/test_quality.py` |
| M4 竞价清算 | 按规则复算并追溯证据 | `POST /api/domain` | `app/modules/domain/rule.py` | `tests/test_domain.py` |
| M5 结算清单 | 核对独立清单和各类差异 | `POST /api/reconcile` | `app/modules/reconcile/service.py` | `tests/test_reconcile.py` |
| M6 交易批次 | 打开历史批次并对原文件复跑 | `POST /api/runs` | `app/modules/runs/service.py` | `tests/test_runs.py` |
| M7 市场签核 | 登记复核结论并下载证据 | `POST /api/review/{run_id}` | `app/modules/review/decisions.py` | `tests/test_review.py` |
| M8 晚到更正 | 登记晚到更正、按场生成冲销单并发布 | `POST /api/corrections/{run_id}` | `app/modules/correction/service.py` | `tests/test_correction.py` |

## 晚到更正与冲销单

- 历史签核不可改写：更正只新增 `corrections` 记录，`runs` 与 `reviews` 原样保留，原签核金额、依据与复核时间线可在冲销单和导出证据中追溯。
- 影响划界：对更正后来源重跑同一管线，只有登记的目标场次允许变化；同期别其他场次的金额、清算依据以及全部隔离/抑制来源行必须逐行一致，否则拒绝 `CORRECTION_SCOPE`。目标场次更正后无法清算判 `CORRECTION_INVALID`，无变化判 `CORRECTION_NOCHANGE`。
- 冲销单逐场列示原签核金额、更正后金额、冲销额（更正后减原签核）、统一清算价前后值，以及同场各买家获配数量调整；未改动场次列入 `unchanged_sessions` 明示不计入。
- 发布闸口：登记时按当时外账同时留痕原签核金额与更正后金额的核对结果；发布时用最新外账按场重核**更正后金额**，全部 `MATCH` 才置为已发布，未通过保持待发布并返回 `VOUCHER_BLOCKED`，可补账后重试同一冲销单。
- 保存失败整体回滚，旧版签核不受影响；更正编号由规则版本、批次与来源/外账字节摘要决定，配合同表唯一约束，同一更正重试只回送既有冲销单，并发登记也只落一条。

## 陷阱登记

| TRAP | 现象 | 样例 | 处理位置 | 测试 |
|---|---|---|---|---|
| TRAP-01 | GB18030 来源文件 | legacy.csv | `app/modules/intake/reader.py` | `tests/test_intake.py::test_gb18030` |
| TRAP-02 | BOM 前缀 | shift.csv | `app/modules/intake/reader.py` | `tests/test_intake.py::test_bom` |
| TRAP-03 | 备注含引号内换行 | shift.csv | `app/modules/intake/service.py` | `tests/test_intake.py::test_multiline` |
| TRAP-04 | 分段重复表头 | shift.csv | `app/modules/intake/service.py` | `tests/test_intake.py::test_repeated` |
| TRAP-05 | 列数不足 | shift.csv | `app/modules/intake/service.py` | `tests/test_intake.py::test_width` |
| TRAP-07 | 缺测哨兵 | shift.csv | `app/modules/contract/service.py` | `tests/test_contract.py::test_missing` |
| TRAP-08 | 前导零的单号 | shift.csv | `app/modules/contract/service.py` | `tests/test_contract.py::test_leading_zero` |
| TRAP-11 | 偏移时刻 UTC 归一 | shift.csv | `app/modules/domain/values.py` | `tests/test_contract.py::test_offsets` |
| TRAP-14 | 同版业务字段冲突 | shift.csv | `app/modules/quality/versions.py` | `tests/test_quality.py::test_conflicting` |
| TRAP-16 | 末行引号截断 | truncated.csv | `app/modules/intake/reader.py` | `tests/test_intake.py::test_truncated_rejected` |
| TRAP-17 | 旧版列名映射 | legacy.csv | `app/modules/contract/schema.py` | `tests/test_contract.py::test_legacy_aliased` |
| TRAP-18 | 空文件、空白文件与仅表头 | 测试构造 | `app/modules/intake/service.py` | `tests/test_intake.py::test_empty_states` |
| TRAP-26 | 陈旧复核版本拒绝 | 测试构造 | `app/modules/review/decisions.py` | `tests/test_review.py::test_stale` |
| TRAP-19 | time before identifier | cases.csv | `app/modules/domain/rule.py` | `tests/test_domain.py::test_time_before_identifier` |
| TRAP-27 | 更正越界改动同期别其他场次 | 测试构造 | `app/modules/correction/impact.py` | `tests/test_correction.py::test_scope_rejects_changes_outside_target_session` |
| TRAP-28 | 同一更正重试重复出冲销单 | 测试构造 | `app/modules/correction/repository.py` | `tests/test_correction.py::test_retry_same_correction_never_duplicates` |
| TRAP-29 | 外账未按场核对通过即发布 | 测试构造 | `app/modules/correction/service.py` | `tests/test_correction.py::test_publish_blocked_until_book_reconciles_per_session` |
| TRAP-30 | 保存失败污染历史签核 | 测试构造 | `app/modules/correction/repository.py` | `tests/test_correction.py::test_save_failure_keeps_original_review_and_run` |

## 对账

输入 = 计入 + 隔离 + 重传及版本替换 + 空白记录 + 重复表头。按业务键全外连接，缺失一侧与数值为零分别登记。逐笔差值与总差一致。
