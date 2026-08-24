from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlencode

import requests

# When this file is executed directly (python scripts/...), Python puts the
# scripts directory on sys.path, not the repository root. Add the repo root so
# the local universal_bot package is always importable without installing it.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from universal_bot.adapters.bitget_elite import BitgetEliteAdapter
from universal_bot.config import Settings


def probe(adapter: BitgetEliteAdapter, path: str, params: dict[str, str] | None = None) -> None:
    clean = {k: v for k, v in (params or {}).items() if v is not None}
    query = urlencode(sorted((str(k), str(v)) for k, v in clean.items()))
    headers = adapter._signed_headers("GET", path, query, "")
    url = adapter.BASE_URL + path + (f"?{query}" if query else "")
    try:
        r = requests.get(url, headers=headers, timeout=adapter.timeout)
    except Exception as exc:
        print(json.dumps({"path": path, "transport_error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return

    try:
        payload = r.json()
    except Exception:
        payload = None

    out: dict[str, object] = {
        "path": path,
        "http": r.status_code,
    }
    if isinstance(payload, dict):
        out["code"] = payload.get("code")
        out["msg"] = payload.get("msg")
        data = payload.get("data")
        if path.endswith("/account/info") and isinstance(data, dict):
            out["permType"] = data.get("permType")
            out["permissions"] = data.get("permissions")
            out["ips_configured"] = bool(data.get("ips"))
        elif isinstance(data, list):
            out["data_items"] = len(data)
        elif isinstance(data, dict):
            out["data_keys"] = sorted(str(k) for k in data.keys())[:20]
    else:
        text = r.text.strip().replace("\n", " ")
        out["body_preview"] = text[:300]

    print(json.dumps(out, ensure_ascii=False))


def main() -> None:
    s = Settings()
    key, secret, passphrase = s.bitget_elite_credentials
    if not (key and secret and passphrase):
        raise SystemExit("Elite credentials are missing in .env")

    adapter = BitgetEliteAdapter(
        key,
        secret,
        passphrase,
        timeout=s.bitget_elite_request_timeout,
        fallback_exchanges=s.crypto_fallback_exchange_list,
        community_fallback=False,
    )

    print("BITGET_ELITE_AUTH_DIAGNOSTIC")
    print("Secrets are not printed. This script performs GET/read-only probes only.")
    probe(adapter, "/api/v3/account/info")
    probe(adapter, "/api/v3/copy/futures/trading-pairs")
    probe(adapter, "/api/v3/copy/futures/position-summary")
    # Compatibility probe matching the previously working Elite bot. Read-only only.
    probe(adapter, "/api/v2/mix/account/accounts", {"productType": "USDT-FUTURES"})


if __name__ == "__main__":
    main()
