# Provera Celery Workera na Serveru

## Arhitektura na serveru

Server: `nl1-ts105.a2hosting.com` (shared hosting, bez systemd)
User: `uplatnic`
Python: `3.9` (virtualenv: `/home/uplatnic/virtualenv/Uplatnice/test/3.9/`)

### Komponente

| Komponenta | Tehnologija | Konekcija |
|---|---|---|
| Broker | Redis 5.0.3 | Unix socket (TCP isključen) |
| Task queue | Celery | 1 worker (concurrency=2) + 1 beat |
| Watchdog | Bash + cron | Svakih 15 min + na reboot |

### Redis konfiguracija

- **Socket:** `/home/uplatnic/.redis/redis.sock`
- **Config:** `/home/uplatnic/.redis/redis.conf`
- **Log:** `/home/uplatnic/.redis/redis.log`
- **TCP port:** isključen (`port 0`)
- **Max memorija:** 64MB, `allkeys-lru` eviction

### Struktura fajlova na serveru

```
/home/uplatnic/
├── .redis/
│   ├── redis.conf          # Redis konfiguracija
│   ├── redis.sock           # Unix socket
│   ├── redis.log            # Redis log
│   └── redis.pid            # PID fajl
├── Aplikacije/
│   ├── celery_watchdog.sh   # Watchdog skripta (Redis + Worker + Beat)
│   ├── celery_app.py        # Test celery app
│   ├── deploy_all.sh        # Deploy skripta
│   ├── 0001/ - 0100/        # Instalirane aplikacije (svaka ima svoj .env)
│   └── 0061/OneTouch/       # Aplikacija iz koje se pokreće Celery worker
├── logs/
│   ├── celery.log           # Celery worker log
│   ├── celery-beat.log      # Celery beat log
│   └── watchdog.log         # Watchdog log
└── virtualenv/Uplatnice/test/3.9/
    └── bin/celery            # Celery binary
```

### Celery konfiguracija

- Broker URL se čita iz `.env` fajla svake aplikacije: `CELERY_BROKER_URL=redis+socket:///home/uplatnic/.redis/redis.sock`
- Default u kodu (`redis://localhost:6379/0`) se ne koristi jer je env varijabla uvek setovana
- Task routing: `emails` queue za email taskove, `qr_codes` queue za QR taskove
- Beat schedule: SMTP healthcheck svakih 5 min, retry failed emails svakih 6h

### Cron jobs

```
@reboot sleep 30 && /bin/bash /home/uplatnic/Aplikacije/celery_watchdog.sh
*/15 * * * * /bin/bash /home/uplatnic/Aplikacije/celery_watchdog.sh
```

Watchdog skripta proverava redom: Redis -> Celery Worker -> Celery Beat. Ako bilo koja komponenta ne radi, restartuje je.

---

## Komande za proveru

### Brza provera (sve u jednoj liniji)

```bash
redis-cli -s /home/uplatnic/.redis/redis.sock ping && cd ~/Aplikacije/0061/OneTouch && /home/uplatnic/virtualenv/Uplatnice/test/3.9/bin/celery -A onetouch.celery inspect ping
```

Očekivan output: `PONG` + `pong` = sve radi.

### Detaljne provere

```bash
# 1. Redis status
redis-cli -s /home/uplatnic/.redis/redis.sock ping
redis-cli -s /home/uplatnic/.redis/redis.sock info clients
redis-cli -s /home/uplatnic/.redis/redis.sock info memory

# 2. Celery procesi
ps aux | grep celery
pgrep -fl celery

# 3. Celery inspect (iz app direktorijuma)
cd ~/Aplikacije/0061/OneTouch
/home/uplatnic/virtualenv/Uplatnice/test/3.9/bin/celery -A onetouch.celery inspect ping
/home/uplatnic/virtualenv/Uplatnice/test/3.9/bin/celery -A onetouch.celery inspect active
/home/uplatnic/virtualenv/Uplatnice/test/3.9/bin/celery -A onetouch.celery inspect registered
/home/uplatnic/virtualenv/Uplatnice/test/3.9/bin/celery -A onetouch.celery inspect stats

# 4. Redis queue-ovi (koliko taskova čeka)
redis-cli -s /home/uplatnic/.redis/redis.sock LLEN celery
redis-cli -s /home/uplatnic/.redis/redis.sock LLEN emails
redis-cli -s /home/uplatnic/.redis/redis.sock LLEN qr_codes
```

### Logovi

```bash
# Poslednji taskovi
tail -30 ~/logs/celery.log

# Beat schedule
tail -20 ~/logs/celery-beat.log

# Da li je watchdog nešto restartovao
tail -20 ~/logs/watchdog.log

# Redis log (greške)
tail -20 ~/.redis/redis.log
```

### Ručni restart (ako nešto ne radi)

```bash
# Restart Redis
redis-cli -s /home/uplatnic/.redis/redis.sock shutdown 2>/dev/null
/usr/bin/redis-server /home/uplatnic/.redis/redis.conf
sleep 2
redis-cli -s /home/uplatnic/.redis/redis.sock ping

# Restart Celery Worker (prvo ubij stare)
pkill -f "onetouch.celery worker"
sleep 2
cd ~/Aplikacije/0061/OneTouch
/home/uplatnic/virtualenv/Uplatnice/test/3.9/bin/celery -A onetouch.celery worker --loglevel=info --concurrency=2 >> ~/logs/celery.log 2>&1 &

# Restart Celery Beat
pkill -f "onetouch.celery beat"
sleep 2
cd ~/Aplikacije/0061/OneTouch
/home/uplatnic/virtualenv/Uplatnice/test/3.9/bin/celery -A onetouch.celery beat --loglevel=info >> ~/logs/celery-beat.log 2>&1 &

# Ili jednostavno pokreni watchdog koji će sam restartovati šta treba
/bin/bash ~/Aplikacije/celery_watchdog.sh
```
