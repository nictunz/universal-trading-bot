from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
import gzip
import zipfile

import pandas as pd

from universal_bot.archive_historical import OfficialArchiveHistoricalDataManager
from universal_bot.historical import DataRequest
from universal_bot.providers.official_archives import OfficialArchiveMarketData


def test_binance_zip_parser():
    csv = (
        "1722470400000,3000,3010,2990,3005,12.5,1722470699999,0,0,0,0,0\n"
        "1722470700000,3005,3020,3000,3015,10.0,1722470999999,0,0,0,0,0\n"
    )
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("ETHUSDT-5m-2024-08.csv", csv)
    df = OfficialArchiveMarketData._binance_zip(buf.getvalue())
    assert len(df) == 2
    assert float(df.iloc[-1].close) == 3015.0
    assert float(df.iloc[0].volume) == 12.5


def test_bybit_trade_chunk_aggregates_to_5m():
    raw = pd.DataFrame(
        {
            "timestamp": [1722470400.0, 1722470410.0, 1722470710.0],
            "symbol": ["ETHUSDT"] * 3,
            "side": ["Buy", "Sell", "Buy"],
            "size": [1.0, 2.0, 3.0],
            "price": [3000.0, 3010.0, 3020.0],
        }
    )
    df = OfficialArchiveMarketData._bybit_trade_chunk(raw, "5m")
    assert len(df) == 2
    assert float(df.iloc[0].open) == 3000.0
    assert float(df.iloc[0].close) == 3010.0
    assert float(df.iloc[0].volume) == 3.0


def test_archive_manager_uses_archive_after_direct_failure(tmp_path, monkeypatch):
    manager = OfficialArchiveHistoricalDataManager(f"sqlite:///{tmp_path/'x.db'}")
    monkeypatch.setattr(manager, "_fetch_crypto_direct", lambda request: (_ for _ in ()).throw(RuntimeError("blocked")))
    idx = pd.date_range("2026-08-01", periods=2, freq="5min", tz="UTC")
    frame = pd.DataFrame({"open":[1,2],"high":[2,3],"low":[.5,1.5],"close":[1.5,2.5],"volume":[10,20]}, index=idx)
    monkeypatch.setattr(manager._official_archive, "fetch_history", lambda *args, **kwargs: frame)
    request = DataRequest(
        symbol="ETH/USDT:USDT",
        timeframe="5m",
        start=datetime(2026,8,1,tzinfo=timezone.utc),
        end=datetime(2026,8,1,0,5,tzinfo=timezone.utc),
        asset_class="crypto",
        exchange="binance",
    )
    out = manager._fetch_crypto(request)
    assert len(out) == 2
    assert manager.last_fetch_status["binance"] == {"mode":"OFFICIAL_ARCHIVE","status":"OK"}
