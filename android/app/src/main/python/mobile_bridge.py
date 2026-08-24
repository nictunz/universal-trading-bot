from __future__ import annotations

import json
from pathlib import Path

from universal_bot.local_cache_core import (
    DEFAULT_REMOTE_DIR,
    DEFAULT_SERVER,
    DEFAULT_USER,
    build_cache_and_backtest,
    test_ssh_connection,
    upload_to_server,
)


def defaults() -> str:
    return json.dumps(
        {
            "server": DEFAULT_SERVER,
            "user": DEFAULT_USER,
            "remote_dir": DEFAULT_REMOTE_DIR,
        },
        ensure_ascii=False,
    )


def run_backtest(symbol: str, timeframe: str, start_text: str, end_text: str, output_dir: str) -> str:
    logs: list[str] = []
    db, result, summary = build_cache_and_backtest(
        symbol.strip(),
        timeframe.strip(),
        start_text.strip(),
        end_text.strip(),
        Path(output_dir),
        logs.append,
    )
    return json.dumps(
        {
            "db": str(db),
            "result": str(result),
            "summary": summary,
            "logs": logs,
        },
        ensure_ascii=False,
    )


def ensure_ssh_key(app_files_dir: str) -> str:
    import paramiko

    root = Path(app_files_dir) / "ssh"
    root.mkdir(parents=True, exist_ok=True)
    private_path = root / "android_upload_rsa"
    if private_path.exists():
        key = paramiko.RSAKey.from_private_key_file(str(private_path))
    else:
        key = paramiko.RSAKey.generate(3072)
        key.write_private_key_file(str(private_path))
    public_key = f"{key.get_name()} {key.get_base64()} universal-backtester-android"
    return json.dumps(
        {"private_key": str(private_path), "public_key": public_key},
        ensure_ascii=False,
    )


def test_ssh(host: str, username: str, key_path: str) -> str:
    return test_ssh_connection(host.strip(), username.strip(), key_path=key_path.strip())


def upload_result(
    db_path: str,
    result_path: str,
    host: str,
    username: str,
    remote_dir: str,
    key_path: str,
) -> str:
    logs: list[str] = []
    upload_to_server(
        Path(db_path),
        Path(result_path),
        host.strip(),
        username.strip(),
        remote_dir.strip(),
        "",
        key_path.strip(),
        logs.append,
    )
    return json.dumps({"ok": True, "logs": logs}, ensure_ascii=False)
