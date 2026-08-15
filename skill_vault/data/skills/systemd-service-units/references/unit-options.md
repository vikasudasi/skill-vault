## systemd Unit File Options Reference

### [Unit]
```
Description=    Human-readable name
After=          Start after these units (ordering dependency)
Requires=       Hard dependency -- fail if this unit isn't active
Wants=          Soft dependency -- start if available, don't fail
```

### [Service]
```
Type=simple     Foreground process (most common)
Type=notify     Process signals readiness via sd_notify()
Type=forking    Process forks and parent exits when ready
Type=oneshot    Process exits after one action (scripts)

User=/Group=    Run as unprivileged user (NEVER root)
ExecStart=      Command + args to start
ExecStop=       Command to stop (optional; SIGTERM by default)
Restart=        no | on-failure | always | on-abnormal
RestartSec=     Seconds to wait before restart

EnvironmentFile=  Path to key=value file (mode 0600)
WorkingDirectory= Working dir for ExecStart

LimitNOFILE=    Max open file descriptors
TimeoutStopSec= Max seconds to wait for stop before SIGKILL
```

### [Install]
```
WantedBy=multi-user.target    Start at boot (normal services)
WantedBy=timers.target        Timer-activated services only
```

### Common patterns

**Python web app:**
```ini
[Service]
Type=simple
User=webapp
WorkingDirectory=/opt/myapp
ExecStart=/opt/myapp/.venv/bin/gunicorn app:app -w 4 -b 127.0.0.1:8000
Restart=on-failure
RestartSec=5
EnvironmentFile=/etc/myapp/env
```

**Oneshot script (runs once, logs output):**
```ini
[Service]
Type=oneshot
User=root
ExecStart=/usr/local/bin/startup-script.sh
RemainAfterExit=yes
```

### Debugging
```bash
sudo systemctl status <name>           # Current state
sudo journalctl -u <name> -f           # Follow logs
sudo journalctl -u <name> --since "5 min ago"
sudo systemctl daemon-reload           # Reload after editing unit
sudo systemctl reset-failed <name>     # Clear failure state
```