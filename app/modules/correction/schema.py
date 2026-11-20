from typing import Annotated, Literal
from pydantic import BaseModel, Field
from app.errors import DataError
from app.inputs import CsvText, EncodedCsv, input_bytes
from app.modules.runs.repository import fetch

MAX_NOTE = 500


def _decode(data, encoded):
    if data is not None and encoded is not None:
        raise DataError('CONTRACT', '同一输入只能提交文本或原始文件')
    if data is None and encoded is None:
        raise DataError('REQUIRED', '更正来源 CSV 不能为空')
    return input_bytes(data, encoded, None)


class CorrectionIn(BaseModel):
    target: Annotated[str, Field(min_length=1, max_length=80)]
    note: Annotated[str, Field(min_length=1, max_length=MAX_NOTE)]
    data: CsvText | None = None
    data_base64: EncodedCsv | None = None
    book: CsvText | None = None
    book_base64: EncodedCsv | None = None

    def source_bytes(self):
        return _decode(self.data, self.data_base64)

    def book_bytes(self, run_id):
        # 外账缺省沿用原批次保存的独立账，保证同一次更正可在补账后重试。
        if self.book is None and self.book_base64 is None:
            return fetch(run_id)['book']
        return input_bytes(self.book, self.book_base64, None)


class RecheckIn(BaseModel):
    book: CsvText | None = None
    book_base64: EncodedCsv | None = None
    action: Literal['publish'] = 'publish'

    def book_bytes(self, fallback):
        if self.book is None and self.book_base64 is None:
            return fallback
        return input_bytes(self.book, self.book_base64, None)
