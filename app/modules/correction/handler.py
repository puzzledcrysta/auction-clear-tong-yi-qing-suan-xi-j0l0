from fastapi import APIRouter
from .schema import CorrectionIn, RecheckIn
from . import service
from .repository import get

router = APIRouter()


@router.post('/api/corrections/{run_id}')
def register(run_id: str, payload: CorrectionIn):
    voucher, created = service.register(
        run_id, payload.target.strip(), payload.note,
        payload.source_bytes(), payload.book_bytes(run_id))
    return {'created': created, 'voucher': voucher}


@router.get('/api/corrections/{run_id}')
def list_corrections(run_id: str):
    return {'corrections': service.list_corrections(run_id)}


@router.get('/api/correction/{correction_id}')
def detail(correction_id: str):
    return service.detail(correction_id)


@router.post('/api/correction/{correction_id}/publish')
def publish(correction_id: str, payload: RecheckIn):
    stored = get(correction_id)
    book = payload.book_bytes(stored['book'])
    voucher, changed = service.recheck_and_publish(correction_id, book)
    return {'published': changed, 'voucher': voucher}
