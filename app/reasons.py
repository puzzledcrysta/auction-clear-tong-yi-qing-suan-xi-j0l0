REASONS = {
    'EMPTY': '文件无内容', 'BLANK_FILE': '文件只有空白', 'HEADER_ONLY': '文件只有表头',
    'ENCODING': '无法识别编码', 'CSV': '表格语法错误', 'HEADER': '表头无效',
    'WIDTH': '列数与表头不一致', 'CONTRACT': '列契约无法应用', 'REQUIRED': '主键或业务字段缺失',
    'TIMESTAMP': '时间需包含偏移量', 'NUMBER': '数字无法归一', 'RANGE': '数字越界',
    'EXACT_DUP': '同版本重复传输', 'SUPERSEDED': '已被更新版本代替',
    'REV_CONFLICT': '最高版本证据有冲突', 'BUSINESS': '业务规则无法判定',
    'MISSING_BOOK': '外部账缺少业务键', 'MISSING_RESULT': '复算结果缺少业务键',
    'AMOUNT_DELTA': '复算与外部账计量不同', 'BOOK_CONFLICT': '独立账含重复业务键',
    'RUN_UNKNOWN': '没有此批次', 'DEMO_UNKNOWN': '没有此样例', 'STALE': '复核版本已过期',
    'REVIEW_NOTE': '有差异时须填写复核意见', 'REVIEW_DECISION': '复核结论无效',
    'CORRECTION_REVIEW': '批次尚未签核确认，不能登记晚到更正',
    'CORRECTION_TARGET': '更正场次不在批次清算结果中',
    'CORRECTION_SCOPE': '更正只能改变指定场次，同期别其他来源不得变化',
    'CORRECTION_NOCHANGE': '更正后的指定场次与原签核结果一致',
    'CORRECTION_INVALID': '更正后的指定场次无法清算，先修正来源',
    'VOUCHER_UNKNOWN': '没有此更正记录',
    'VOUCHER_BLOCKED': '外账按场次核对未通过，冲销单不能发布',
    'VOUCHER_PUBLISHED': '冲销单已发布，不可重复发布',
}

REASONS.update({'AUCTION_FORMAT': '报价事件无效', 'AUCTION_CONFLICT': '同版报价冲突', 'DATE': '日期格式无效', 'REV_BLOCKED': '较新来源尚未采信'})
