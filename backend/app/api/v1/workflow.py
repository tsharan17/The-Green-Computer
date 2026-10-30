"""Workflow stages: verification report, pipeline status, structured recommendations from the
engine and the cooling sweep with its figures."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.v1.routes import project_for
from app.auth.deps import Ctx, get_db, require_ctx
from app.render import figures
from app.services import plan_service as plans
from app.services import workflow_service as wf

router = APIRouter(tags=["workflow"])
_SWEEP_CACHE: dict[tuple[int, int, str, str], bytes] = {}
_SWEEP_CACHE_MAX = 64


@router.get("/projects/{project_id}/verification")
def project_verification(project_id: int, db: Session = Depends(get_db), ctx: Ctx = Depends(require_ctx)) -> dict[str, Any]:
    """Verification and Requirements Manager report for the project's current inputs."""
    return wf.verification(db, project_for(db, ctx, project_id), ctx.workspace_id)


@router.get("/projects/{project_id}/pipeline")
def project_pipeline(project_id: int, db: Session = Depends(get_db), ctx: Ctx = Depends(require_ctx)) -> dict[str, Any]:
    """Each workflow stage with its stored record and whether it is done, ready, blocked or stale."""
    return wf.pipeline(db, project_for(db, ctx, project_id), ctx.workspace_id)


@router.get("/projects/{project_id}/recommendations")
def project_recommendations(project_id: int, db: Session = Depends(get_db), ctx: Ctx = Depends(require_ctx)) -> dict[str, Any]:
    """Software and hardware recommendations from the latest analysis, ranked by the project's
    requirements, with each one's validation state."""
    return wf.recommendations(db, project_for(db, ctx, project_id), ctx.workspace_id)


@router.get("/projects/{project_id}/cooling-sweep")
def project_cooling_sweep(project_id: int, db: Session = Depends(get_db), ctx: Ctx = Depends(require_ctx)) -> dict[str, Any]:
    """Temperature over ambient x input rate for every cooling option, and power mode x cooling."""
    try:
        return plans.cooling_sweep(db, project_for(db, ctx, project_id), ctx.workspace_id)
    except (KeyError, ValueError) as e:
        raise HTTPException(422, str(e).strip("'")) from e


@router.get("/projects/{project_id}/figures/{name}")
def project_figure(
    project_id: int, name: str, theme: Literal["light", "dark"] = "light", db: Session = Depends(get_db),
    ctx: Ctx = Depends(require_ctx),
) -> Response:  # fmt: skip
    """Seaborn/matplotlib cooling figures (PNG) drawn from the engine's cooling sweep."""
    p = project_for(db, ctx, project_id)
    if name not in figures.SWEEP_FIGURES:
        raise HTTPException(404, f"unknown figure; choose one of {', '.join(sorted(figures.SWEEP_FIGURES))}")
    key = (p.id, p.version, name, theme)
    png = _SWEEP_CACHE.get(key)
    if png is None:
        try:
            png = figures.render_sweep(name, plans.cooling_sweep(db, p, ctx.workspace_id), theme)
        except (figures.FigureError, KeyError, ValueError) as e:
            raise HTTPException(422, str(e).strip("'")) from e
        if len(_SWEEP_CACHE) >= _SWEEP_CACHE_MAX:
            _SWEEP_CACHE.pop(next(iter(_SWEEP_CACHE)))
        _SWEEP_CACHE[key] = png
    return Response(png, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})
