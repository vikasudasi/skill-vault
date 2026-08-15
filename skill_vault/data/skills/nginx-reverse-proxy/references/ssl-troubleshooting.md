## SSL/TLS Troubleshooting Reference

### Quick diagnostic commands

```bash
# Test config syntax
nginx -t

# Check which ports nginx is actually listening on
ss -tlnp | grep nginx

# Verify cert chain from outside
openssl s_client -connect yourdomain.com:443 -servername yourdomain.com </dev/null \
  | openssl x509 -noout -dates -subject -issuer

# Check cert expiration
echo | openssl s_client -connect yourdomain.com:443 -servername yourdomain.com 2>/dev/null \
  | openssl x509 -noout -enddate
```

### Common certbot issues

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `Connection refused` on :443 | nginx not listening on 443 | Check `listen 443 ssl;` in server block |
| `certbot` says "connection refused" | :80 not reachable | DNS not pointing to server, or firewall blocks :80 |
| Cert issued but browser shows warning | Old cert cached | `systemctl reload nginx`; check browser cache |
| Renewal fails silently | cron hook missing | `certbot renew --dry-run` to test |

### Headers you probably don't need
- `X-Real-IP` - only if the backend uses it for auth/logging
- `X-Forwarded-For` - only if the backend needs client IP chain
- `X-Forwarded-Proto` - only if the backend generates URLs and needs to know `https`

### Common header leaks
```nginx
# BAD: exposes backend internal IP to the internet
proxy_set_header Host $proxy_host;

# GOOD: preserves the external hostname
proxy_set_header Host $host;
```