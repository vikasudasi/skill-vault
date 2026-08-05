from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from cryptography.hazmat.primitives.asymmetric import ed25519

from skill_vault.models import SkillInput
from skill_vault.service import _build_payload
from skill_vault.trust import sign


@dataclass(slots=True)
class SeedSkill:
    skill: SkillInput
    verify: bool
    source: str
    path: Path


def discover_seed_dir(base: str | Path) -> Path:
    base_path = Path(base).expanduser()
    if base_path.is_absolute():
        resolved = base_path.resolve()
        if not resolved.is_dir():
            raise FileNotFoundError(f"seed directory does not exist: {resolved}")
        return resolved

    candidates: list[Path] = [(Path.cwd() / base_path).resolve()]
    first_component = _first_component(base_path)
    if first_component == "skill_vault":
        candidates.append((Path(__file__).resolve().parent / "data" / "skills").resolve())

    for candidate in candidates:
        if candidate.is_dir():
            return candidate

    candidate_text = ", ".join(str(candidate) for candidate in candidates)
    raise FileNotFoundError(f"seed directory does not exist (checked: {candidate_text})")


def parse_skill_file(path: Path) -> SeedSkill:
    text = path.read_text(encoding="utf-8")
    frontmatter, body = _split_frontmatter(text, path)
    metadata = _parse_frontmatter(frontmatter, path)

    name = _require_non_empty_str(metadata, "name", path)
    description = _require_non_empty_str(metadata, "description", path)
    source = _require_non_empty_str(metadata, "source", path)
    body_text = body.strip()
    if not body_text:
        raise ValueError(f"{path}: skill body is required")

    skill = SkillInput(
        name=name,
        description=description,
        tags=_optional_list_of_str(metadata, "tags"),
        triggers=_optional_list_of_str(metadata, "triggers"),
        body=body_text,
        meta={
            "complexity": _optional_str(metadata, "complexity"),
            "time_estimate": _optional_str(metadata, "time_estimate"),
            "prerequisites": _optional_list_of_str(metadata, "prerequisites"),
            "source": source,
        },
    )
    verify = _optional_bool(metadata, "verify", default=False, path=path)
    return SeedSkill(skill=skill, verify=verify, source=source, path=path)


def seed_skills(services: Any, seed_dir: str | Path, curator_key: str | None) -> int:
    resolved_seed_dir = discover_seed_dir(seed_dir)
    published = 0

    for file_path in _seed_files(resolved_seed_dir):
        seed_skill = parse_skill_file(file_path)
        existing = services.db.execute(
            "SELECT id FROM skills WHERE name = ? AND visibility = 'global' LIMIT 1",
            (seed_skill.skill.name.strip(),),
        ).fetchone()
        if existing is not None:
            continue

        signature: str | None = None
        public_key: str | None = None
        signed_by: str | None = None
        if seed_skill.verify and curator_key:
            payload = _build_payload(seed_skill.skill)
            signature = sign(payload, curator_key)
            public_key = _public_key_from_private_key(curator_key)
            signed_by = seed_skill.source

        services.registry.admin_publish_seed(
            seed_skill.skill,
            signature=signature,
            public_key=public_key,
            signed_by=signed_by,
        )
        published += 1

    return published


def _first_component(path: Path) -> str | None:
    meaningful = [part for part in path.parts if part not in ("", ".")]
    return meaningful[0] if meaningful else None


def _seed_files(seed_dir: Path) -> list[Path]:
    files: list[Path] = []
    for entry in sorted(seed_dir.iterdir()):
        if entry.is_file() and entry.suffix.lower() == ".md":
            files.append(entry)
            continue
        if entry.is_dir():
            skill_file = entry / "SKILL.md"
            if skill_file.is_file():
                files.append(skill_file)
    return files


def _split_frontmatter(text: str, path: Path) -> tuple[str, str]:
    if not text.startswith("---\n"):
        raise ValueError(f"{path}: missing YAML frontmatter")
    marker = "\n---\n"
    end_index = text.find(marker, 4)
    if end_index < 0:
        raise ValueError(f"{path}: malformed YAML frontmatter")
    frontmatter = text[4:end_index]
    body = text[end_index + len(marker) :]
    return frontmatter, body


def _parse_frontmatter(frontmatter: str, path: Path) -> dict[str, object]:
    loaded = yaml.safe_load(frontmatter)
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise TypeError(f"{path}: frontmatter must be a YAML mapping")
    metadata: dict[str, object] = loaded
    return metadata


def _require_non_empty_str(metadata: dict[str, object], key: str, path: Path) -> str:
    value = metadata.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path}: frontmatter field '{key}' is required")
    return value.strip()


def _optional_str(metadata: dict[str, object], key: str) -> str | None:
    value = metadata.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"frontmatter field '{key}' must be a string")
    stripped = value.strip()
    return stripped if stripped else None


def _optional_list_of_str(metadata: dict[str, object], key: str) -> list[str]:
    value = metadata.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise TypeError(f"frontmatter field '{key}' must be a list of strings")
    values: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise TypeError(f"frontmatter field '{key}' must be a list of strings")
        values.append(item.strip())
    return [item for item in values if item]


def _optional_bool(metadata: dict[str, object], key: str, *, default: bool, path: Path) -> bool:
    value = metadata.get(key)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raise ValueError(f"{path}: frontmatter field '{key}' must be a boolean")


def _public_key_from_private_key(private_key_b64: str) -> str:
    private_key_bytes = base64.b64decode(private_key_b64.encode("ascii"))
    private_key = ed25519.Ed25519PrivateKey.from_private_bytes(private_key_bytes)
    return base64.b64encode(private_key.public_key().public_bytes_raw()).decode("ascii")
