## Service Hardening Cheatsheet

### TLS / HTTPS
```nginx
server {
    listen 443 ssl;
    ssl_certificate     /etc/letsencrypt/live/example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/example.com/privkey.pem;
    add_header Strict-Transport-Security "max-age=63072000" always;
}
server {
    listen 80;
    return 301 https://$host$request_uri;
}
```

### Password hashing (Python)
```python
import hashlib, hmac, secrets


def hash_password(pw: str) -> tuple[bytes, bytes]:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 600_000)
    return salt, digest


def verify_password(pw: str, salt: bytes, expected: bytes) -> bool:
    digest = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 600_000)
    return hmac.compare_digest(digest, expected)  # timing-safe
```

### Secure cookies
```
Set-Cookie: session=...; HttpOnly; Secure; SameSite=Lax; Path=/
```

### API key principles
- Scope: read-only, one resource, one API
- Name: descriptive for audit (`svc-email-read`, not `key1`)
- Expiry: 30-90 days; rotate on schedule
- Revocation: test your revoke path (it usually doesn't work the first time)

### Git hygiene
```bash
# Pre-commit hook
gitleaks protect --staged --verbose

# Scan full history (CI)
gitleaks detect --source . --log-opts="--all" --verbose

# Remove a file from history (after rotating the secret!)
git filter-branch --force --index-filter \
  "git rm --cached --ignore-unmatch .env" \
  --prune-empty --tag-name-filter cat -- --all
```

### SSH hardening
```bash
# In ~/.ssh/authorized_keys, restrict a key:
command="/usr/local/bin/my-tool",no-port-forwarding,no-agent-forwarding ssh-ed25519 AAA...
```
