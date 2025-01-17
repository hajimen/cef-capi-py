Minimum setup for Linux.

```bash
docker-compose build  # only after editing docker files
docker-compose up -d
docker-compose exec test-service bash
docker-compose down
```

`/mnt` is repo root.

Run like `xvfb-run python -m cef_capi.smoke_test`.
