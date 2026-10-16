"""Hardware import drafts: create from a datasheet, confirm (with corrections) or reject."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.client import LLM
from app.agent.datasheet import (
    DatasheetError,
    Extraction,
    build_profile,
    extract_hardware_spec,
    search_hits,
)
from app.data_loader import (
    clear_custom_devices,
    load_devices,
    register_device,
    unregister_device,
)
from app.db.models import HardwareDraftRow
from app.engine.hwbuild import CustomHardwareSpec, build_custom
from app.integrations.tavily import TavilyClient
from app.schemas.hardware import HardwareProfile


def _view(row: HardwareDraftRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "query": row.query,
        "status": row.status,
        "candidate": row.profile,
        "evidence": row.evidence,
        "missing": row.missing,
        "device_id": row.device_id,
        "needs_confirmation": row.status == "draft",
        "created_at": row.created_at.isoformat(),
    }


def create_draft(
    db: Session, name: str, tavily: TavilyClient, llm: LLM, model_id: str
) -> dict[str, Any]:
    hits = search_hits(tavily, name)
    ex = extract_hardware_spec(llm, model_id, name, hits)
    return store_draft(db, name, ex, [h.url for h in hits])


def store_draft(db: Session, query: str, ex: Extraction, urls: list[str]) -> dict[str, Any]:
    cand = dict(ex.candidate)
    cand.setdefault("name", query)
    row = HardwareDraftRow(
        query=query[:200],
        status="draft",
        profile=cand,
        evidence=[*ex.evidence, {"field": "_pages_read", "value": urls, "source_url": None}],
        missing=[m for m in ex.missing if m != "name"],
    )
    db.add(row)
    db.commit()
    out = _view(row)
    out["notes"] = ex.notes
    out["dropped_implausible"] = ex.dropped
    return out


def list_drafts(db: Session) -> list[dict[str, Any]]:
    return [_view(r) for r in db.scalars(select(HardwareDraftRow).order_by(HardwareDraftRow.id.desc()))]


def get_draft(db: Session, draft_id: int) -> dict[str, Any] | None:
    row = db.get(HardwareDraftRow, draft_id)
    return _view(row) if row else None


def _new_id(name: str) -> str:
    base = "custom-hw-" + (re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "device")
    taken = set(load_devices())
    cand, n = base, 2
    while cand in taken:
        cand, n = f"{base}-{n}", n + 1
    return cand


def confirm(db: Session, draft_id: int, overrides: dict[str, Any] | None) -> HardwareProfile:
    """The user has reviewed the extracted values (and corrected any); register the device."""
    row = db.get(HardwareDraftRow, draft_id)
    if row is None:
        raise DatasheetError("draft not found")
    if row.status != "draft":
        raise DatasheetError(f"this draft is already {row.status}")
    name = (overrides or {}).get("name") or row.profile.get("name") or row.query
    profile = build_profile(row.profile, overrides, _new_id(str(name)))
    row.status = "confirmed"
    row.device_id = profile.id
    row.profile = {**row.profile, **(overrides or {}), "_profile": profile.model_dump(mode="json")}
    db.commit()
    register_device(profile)
    return profile


def register_custom(db: Session, spec: CustomHardwareSpec) -> HardwareProfile:
    """A device the user described themselves (no extraction, so no confirmation gate)."""
    profile = build_custom(spec, _new_id(spec.name))
    row = HardwareDraftRow(
        query=spec.name[:200], status="confirmed", device_id=profile.id,
        profile={"name": spec.name, "_spec": spec.model_dump(mode="json"),
                 "_profile": profile.model_dump(mode="json")},
        evidence=[], missing=[],
    )  # fmt: skip
    db.add(row)
    db.commit()
    register_device(profile)
    return profile


def remove_custom(db: Session, device_id: str) -> bool:
    row = db.scalars(
        select(HardwareDraftRow).where(
            HardwareDraftRow.device_id == device_id, HardwareDraftRow.status == "confirmed"
        )
    ).first()
    if row is None:
        return False
    row.status = "rejected"
    db.commit()
    unregister_device(device_id)
    return True


def reject(db: Session, draft_id: int) -> dict[str, Any]:
    row = db.get(HardwareDraftRow, draft_id)
    if row is None:
        raise DatasheetError("draft not found")
    row.status = "rejected"
    db.commit()
    return _view(row)


def load_confirmed(db: Session) -> int:
    """Re-register confirmed devices at start-up (drops any left from another app instance)."""
    clear_custom_devices()
    n = 0
    for row in db.scalars(select(HardwareDraftRow).where(HardwareDraftRow.status == "confirmed")):
        raw = row.profile.get("_profile")
        if raw:
            register_device(HardwareProfile.model_validate(raw))
            n += 1
    return n
