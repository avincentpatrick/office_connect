# Password blocklist (vendored)

NIST SP 800-63B-4 §3.1.1.2 requires that new/changed passwords be checked against
a list of commonly-used, expected, or compromised values. Office-Connect runs
**on-prem with no outbound internet**, so the list is **vendored** (committed,
gzipped) rather than fetched at runtime — `is_blocklisted()` makes no network call.

## Artifact

- `top-100000.txt.gz` — gzip of `Pwdb_top-100000.txt`, the 100,000 most common
  passwords (ranked) from **SecLists**.
- Loaded lazily by `__init__.py` into a normalized (`strip().casefold()`)
  `frozenset` on first use.

## Provenance & integrity

| Field | Value |
|---|---|
| Source repo | `danielmiessler/SecLists` |
| Path | `Passwords/Common-Credentials/Pwdb_top-100000.txt` |
| Pinned commit | `6f9b97bd803b82017240dd22877567629b05b905` |
| Lines (decompressed) | 100,000 |
| `top-100000.txt.gz` SHA-256 | `4a8e887d7c4e52b72ec6c6361de47ef674e48b987ff20a05416dc090b8418168` |

## Refreshing the list (dev workstation, has internet)

```sh
curl -sSL -o top-100000.txt \
  "https://raw.githubusercontent.com/danielmiessler/SecLists/master/Passwords/Common-Credentials/Pwdb_top-100000.txt"
gzip -9 -f top-100000.txt          # -> top-100000.txt.gz
sha256sum top-100000.txt.gz         # update the table above
```

Only the `.gz` is committed (see `.gitattributes`: marked binary + vendored). The
runtime never re-downloads it.
