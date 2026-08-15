#!/usr/bin/env python3
"""Minimal FastAPI application with routing, validation, dependency injection, and tests.

Run:    uvicorn minimal_api:app --reload
Test:   pytest minimal_api.py -v
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

# ── App ─────────────────────────────────────────────────────────────────

app = FastAPI(title="Skills API", version="1.0.0")

# ── Schemas ─────────────────────────────────────────────────────────────


class SkillCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    description: str = Field(..., min_length=10)


class SkillResponse(BaseModel):
    id: str
    name: str
    description: str


# ── Dependencies ────────────────────────────────────────────────────────

# Simulated database; in production, use a real DB connection via Depends.
_db: dict[str, dict] = {}


def get_db() -> dict:
    return _db


# ── Router ──────────────────────────────────────────────────────────────

router = APIRouter(prefix="/skills", tags=["skills"])


@router.post("/", status_code=201, response_model=SkillResponse)
def create_skill(payload: SkillCreate, db: dict = Depends(get_db)) -> SkillResponse:
    sid = f"skill-{len(db) + 1}"
    db[sid] = {"id": sid, "name": payload.name, "description": payload.description}
    return SkillResponse(**db[sid])


@router.get("/{skill_id}", response_model=SkillResponse)
def get_skill(skill_id: str, db: dict = Depends(get_db)) -> SkillResponse:
    if skill_id not in db:
        raise HTTPException(status_code=404, detail="Skill not found")
    return SkillResponse(**db[skill_id])


app.include_router(router)

# ── Health check ────────────────────────────────────────────────────────


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# ── Tests ───────────────────────────────────────────────────────────────

client = TestClient(app)


def test_create_and_get():
    r = client.post("/skills/", json={"name": "pytest", "description": "Testing framework"})
    assert r.status_code == 201
    sid = r.json()["id"]

    r2 = client.get(f"/skills/{sid}")
    assert r2.status_code == 200
    assert r2.json()["name"] == "pytest"


def test_validation():
    r = client.post("/skills/", json={"name": "", "description": "short"})
    assert r.status_code == 422


def test_not_found():
    r = client.get("/skills/nonexistent")
    assert r.status_code == 404
