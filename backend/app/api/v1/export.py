"""Report and recipe export, rendered from the stored analysis."""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.v1.routes import get_db
from app.data_loader import get_device
from app.db import repository as repo
from app.engine.recipe import build_recipe
from app.engine.report import build_report_md, md_to_html
from app.schemas.results import OptimisationResult
from app.services.model_lookup import resolve_model

router = APIRouter()


def _load(db: Session, project_id: int):
    p = repo.get_project(db, project_id)
    if p is None:
        raise HTTPException(404, "project not found")
    raw = repo.latest_run(db, project_id, "optimise")
    if raw is None:
        raise HTTPException(404, "Run the analysis first (Analyse), then export.")
    try:
        res = OptimisationResult.model_validate(raw)
    except ValidationError as e:
        raise HTTPException(409, "The stored analysis is from an older version; run it again.") from e
    return p.spec, resolve_model(db, p.spec.model_id), get_device(p.spec.device_id), res


@router.get("/projects/{project_id}/report")
def report(
    project_id: int,
    format: str = Query("md", pattern="^(md|html)$"),
    db: Session = Depends(get_db),
) -> Response:
    spec, model, hw, res = _load(db, project_id)
    md = build_report_md(spec, model, hw, res, datetime.now(UTC))
    if format == "html":
        return HTMLResponse(md_to_html(md, f"Report: {model.name} on {hw.name}"))
    return PlainTextResponse(md, media_type="text/markdown; charset=utf-8")


@router.get("/projects/{project_id}/recipe")
def recipe(project_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    spec, model, hw, res = _load(db, project_id)
    files, warnings = build_recipe(spec, model, hw, res)
    return {
        "files": {n: {"description": f.description, "content": f.content} for n, f in files.items()},
        "warnings": warnings,
    }


@router.get("/projects/{project_id}/recipe.zip")
def recipe_zip(project_id: int, db: Session = Depends(get_db)) -> Response:
    spec, model, hw, res = _load(db, project_id)
    files, _ = build_recipe(spec, model, hw, res)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, f in files.items():
            z.writestr(name, f.content)
    return Response(
        buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="green-computer-recipe-{project_id}.zip"'},
    )
