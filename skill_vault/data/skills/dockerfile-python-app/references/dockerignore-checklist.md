# .dockerignore Checklist & Layer Caching

## Essential .dockerignore entries

```
# Version control
.git
.gitignore
.gitattributes

# Python artifacts
__pycache__
*.pyc
*.pyo
*.egg-info
.eggs
dist/
build/

# Virtual environments
.venv
venv
env/

# IDE / editor
.vscode
.idea
*.swp
*.swo

# Environment / secrets
.env
.env.*
*.key
*.pem

# Tests & docs (usually not needed in image)
tests/
docs/
*.md
README*

# OS junk
.DS_Store
Thumbs.db
```

## Layer caching strategy

The key principle: place **least-frequently-changing layers first**.

```
1. Base image (FROM)          ← rarely changes
2. System packages (apt)      ← occasionally changes
3. Python dependencies (pip)  ← changes when requirements change
4. Application code (COPY .)  ← changes every build
```

If you `COPY . .` before `pip install`, a single code change invalidates the pip cache — re-downloading all packages on every build.

## Image size checklist

- [ ] Multi-stage build: builder → slim runtime
- [ ] `--no-cache-dir` on pip installs
- [ ] Clean apt caches in same RUN: `apt-get update && apt-get install -y ... && rm -rf /var/lib/apt/lists/*`
- [ ] Use `-slim` or `-alpine` base images
- [ ] `.dockerignore` excludes everything not needed at runtime
- [ ] Non-root USER for the runtime stage