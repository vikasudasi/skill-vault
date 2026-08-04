from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field


@dataclass(slots=True)
class Agent:
    id: str
    name: str
    created_at: str
    updated_at: str


@dataclass(slots=True)
class ApiKey:
    id: str
    agent_id: str
    key_hash: str
    key_prefix: str
    created_at: str
    last_used_at: str | None
    revoked_at: str | None


@dataclass(slots=True)
class Skill:
    id: str
    name: str
    owner_agent_id: str | None
    visibility: str
    current_version_id: str | None
    created_at: str
    updated_at: str


@dataclass(slots=True)
class SkillVersion:
    id: str
    skill_id: str
    version: int
    content_hash: str
    name: str
    description: str
    tags: list[str]
    triggers: list[str]
    meta_json: dict[str, Any]
    body: str
    created_at: str


@dataclass(slots=True)
class TrustRecord:
    id: str
    skill_version_id: str
    tier: str
    signed_by: str | None
    signature: str | None
    public_key: str | None
    verified_at: str | None


class SkillInput(BaseModel):
    name: str
    description: str
    tags: list[str] = Field(default_factory=list)
    triggers: list[str] = Field(default_factory=list)
    body: str
    meta: dict[str, Any] = Field(default_factory=dict)


class SkillCard(BaseModel):
    id: str
    name: str
    description: str
    tags: list[str] = Field(default_factory=list)
    trust: str
    score: float
    version: int


class SkillDetail(BaseModel):
    id: str
    name: str
    description: str
    body: str
    version: int
    tags: list[str] = Field(default_factory=list)
    trust: str
    content_hash: str
    verified: bool
    owner: str | None


class PublishResult(BaseModel):
    ok: bool
    id: str
    version: int
    content_hash: str


class DeleteResult(BaseModel):
    ok: bool
    id: str
    deleted: bool


class VerifyResult(BaseModel):
    ok: bool
    trust: str
    verified: bool
    signed_by: str | None
    content_hash: str

