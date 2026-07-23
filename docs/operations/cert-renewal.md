# Runbook — TLS Certificate Renewal

Production terminates TLS at the **reverse proxy** (Caddy/nginx) on 443 — the app
containers stay on the internal compose network and publish no host ports except
through the proxy (tech-stack §7). Dev (Windows/Laragon) is plain HTTP on 8001 and
needs no cert.

## Automated (recommended — Caddy)
Caddy obtains and renews Let's Encrypt certs automatically. Verify:
```sh
docker compose logs --tail=50 caddy | grep -i "certificate"
curl -sSI https://<domain> | grep -i "HTTP/"
```
No action needed unless renewal fails (e.g. port 80/443 blocked, DNS changed).

## Manual (nginx + certbot, or on-prem CA)
1. **~30 days before expiry** (tracked as a compliance-style reminder), renew:
   ```sh
   certbot renew --deploy-hook "docker compose exec proxy nginx -s reload"
   ```
   Or for an internal PKI, reissue from the on-prem CA and install the new cert +
   chain into the proxy's cert path.
2. **Reload** the proxy (no full downtime): `nginx -s reload` / `caddy reload`.
3. **Verify**:
   ```sh
   echo | openssl s_client -connect <domain>:443 -servername <domain> 2>/dev/null \
     | openssl x509 -noout -dates
   ```
   Confirm `notAfter` is the new date and the chain is complete.

## Notes
- `BASE_URL` must match the public HTTPS origin so app-generated links are correct
  (the app runs with `--proxy-headers`).
- Keep the private key access-controlled; never commit certs/keys.
- If a cert lapses, users get browser warnings but data is unaffected — renew and
  reload; no DB action.
