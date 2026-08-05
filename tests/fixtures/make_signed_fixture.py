"""Generate a genuinely-signed curated skill fixture for tests/fixtures/signed/.

Predictable keys are supplied via env (CURATOR_PRIV/CURATOR_PUB base64 strings) so the
result is deterministic across runs; a throwaway keypair is used when unset. Writes:
  public_key.hex       - hex of the raw 32-byte public key (stored in repo)
  fixture.json         - {payload_b64, signature_b64, public_key_b64, name, ...}
Run from the repo root after installing the package.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

from skill_vault.trust import canonical_payload, generate_curator_keypair, sign

HERE = Path(__file__).parent / "signed"

NAME = "curated-system-dump"
DESCRIPTION = "Curated reference for capturing and inspecting system inventory on Ubuntu."
TAGS = ["sysadmin", "ubuntu", "diagnostics"]
TRIGGERS = ["system summary", "hardware", "dump", "inventory"]
META = {"author": "curator", "source": "fixtures", "license": "MIT"}
BODY = (
    "# System inventory\n\n"
    "Use to capture a compact, repeatable system inventory on Ubuntu.\n\n"
    "```bash\n"
    "uname -a\n"
    "lscpu | head -20      # CPU/arch\n"
    "free -h               # memory\n"
    "df -h /               # root disk\n"
    "ip -brief addr        # interfaces\n"
    "```\n"
)


def main() -> None:
    priv_b64 = os.environ.get("CURATOR_PRIV")
    pub_b64 = os.environ.get("CURATOR_PUB")
    if priv_b64 and pub_b64:
        priv, pub = priv_b64, pub_b64
    else:
        priv, pub = generate_curator_keypair()

    payload = canonical_payload(
        name=NAME,
        description=DESCRIPTION,
        tags=TAGS,
        triggers=TRIGGERS,
        meta_json=META,
        body=BODY,
    )
    signature_b64 = sign(payload, priv)
    pub_raw_hex = base64.b64decode(pub.encode("ascii")).hex()

    HERE.mkdir(parents=True, exist_ok=True)
    (HERE / "public_key.hex").write_text(pub_raw_hex)
    (HERE / "fixture.json").write_text(
        json.dumps(
            {
                "name": NAME,
                "description": DESCRIPTION,
                "tags": TAGS,
                "triggers": TRIGGERS,
                "meta": META,
                "body": BODY,
                "payload_b64": base64.b64encode(payload).decode(),
                "signature_b64": signature_b64,
                "public_key_b64": pub,
            },
            indent=2,
        )
    )
    print(f"wrote signed fixture to {HERE}")


if __name__ == "__main__":
    main()
