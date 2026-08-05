FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SKILL_VAULT_DB_PATH=/data/skill_vault.db \
    SKILL_VAULT_MCP_HOST=0.0.0.0 \
    SKILL_VAULT_MCP_PORT=8000 \
    SKILL_VAULT_WEB_HOST=0.0.0.0 \
    SKILL_VAULT_WEB_PORT=8080 \
    SKILL_VAULT_SEED_DIR=/data/skills

WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends -y build-essential curl libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY README.md ./
COPY skill_vault ./skill_vault
COPY migrations ./migrations

RUN pip install .

EXPOSE 8000 8080

ENTRYPOINT ["skill-vault"]
CMD ["serve", "--transport", "streamable-http"]
