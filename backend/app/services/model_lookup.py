from __future__ import annotations

from sqlalchemy.orm import Session

from app.data_loader import get_model, load_models
from app.db import repository as repo
from app.schemas.model import ModelProfile


def resolve_model(db: Session, model_id: str) -> ModelProfile:
    custom = repo.get_custom_model(db, model_id)
    if custom is not None:
        return custom
    if model_id in load_models():
        return get_model(model_id)
    raise KeyError(f"unknown model '{model_id}'")
