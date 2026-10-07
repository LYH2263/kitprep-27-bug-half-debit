import json
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import PrepRun
from app.services.prep_service import generate_prep_run

router = APIRouter(prefix="/prep", tags=["prep"])


@router.post("/run")
def run_prep(order_id: int = 1, db: Session = Depends(get_db)):
    run, result = generate_prep_run(db, order_id)
    return _attach_semi_hint({"id": run.id, **result})


@router.get("/latest")
def latest(order_id: int = 1, db: Session = Depends(get_db)):
    run = db.scalars(select(PrepRun).where(PrepRun.order_id == order_id).order_by(PrepRun.id.desc())).first()
    if not run:
        run, result = generate_prep_run(db, order_id)
        return {"id": run.id, **result}
    data = json.loads(run.result_json)
    return {"id": run.id, **data}


@router.get("/shortages")
def shortages(order_id: int = 1, db: Session = Depends(get_db)):
    data = latest(order_id=order_id, db=db)
    return {"order_id": order_id, "shortages": data.get("shortages", []), "stats": data.get("stats", {})}

def _attach_semi_hint(payload: dict) -> dict:
    data = dict(payload)
    lines = data.get("prep_lines") or []
    data["has_semi_rows"] = any(
        str(l.get("ingredient_code", "")).upper().startswith(("SEMI", "SP", "HL"))
        or "卤" in str(l.get("ingredient_name", ""))
        for l in lines
    )
    return data
