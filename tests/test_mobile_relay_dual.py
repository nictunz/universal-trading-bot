import json
import time
import pytest
from universal_bot.providers.mobile_relay import MobileRelayMarketData


def payload(tf, now, volume):
    delta = {'5m':300000,'15m':900000}[tf]
    boundary = now // delta * delta
    return {'schema_version':1, 'generated_at_ms':now,
        'timeframe':tf, 'markets':{'BTC/USDT:USDT':{
            ex:[[boundary-delta,volume],[boundary,9999]] for ex in ('binance','bybit')}}}


def files(tmp_path):
    now=int(time.time()*1000)
    main=tmp_path/'mobile-market-relay.json'
    sidecar=tmp_path/'mobile-market-relay-5m.json'
    main.write_text(json.dumps(payload('15m',now,150)))
    sidecar.write_text(json.dumps(payload('5m',now,50)))
    return MobileRelayMarketData(main),main,sidecar,now


def test_dual_native_volume_keeps_legacy_and_filters_open_bar(tmp_path):
    relay,main,sidecar,now=files(tmp_path)
    for ex in ('binance','bybit'):
        assert relay.fetch_volume(ex,'BTCUSDT','15m').tolist()==[150]
        assert relay.fetch_volume(ex,'BTCUSDT','5m').tolist()==[50]
    assert relay.latest_common_timestamp('BTCUSDT','5m') == relay.fetch_volume('binance','BTCUSDT','5m').index[-1]


def test_missing_five_does_not_break_fifteen(tmp_path):
    relay,main,sidecar,now=files(tmp_path)
    sidecar.unlink()
    with pytest.raises(RuntimeError,match='Android dual-timeframe update required'):
        relay.fetch_volume('binance','BTCUSDT','5m')
    assert relay.fetch_volume('binance','BTCUSDT','15m').tolist()==[150]


@pytest.mark.parametrize('fault',['stale','wrong_timeframe','bad_json'])
def test_bad_sidecar_cannot_masquerade_as_fresh_five(tmp_path,fault):
    relay,main,sidecar,now=files(tmp_path)
    if fault=='stale':sidecar.write_text(json.dumps(payload('5m',now-180000,50)))
    elif fault=='wrong_timeframe':sidecar.write_text(json.dumps(payload('15m',now,150)))
    else:sidecar.write_text('{invalid')
    with pytest.raises(RuntimeError): relay.fetch_volume('binance','BTCUSDT','5m')
    assert relay.fetch_volume('binance','BTCUSDT','15m').tolist()==[150]


def test_five_uses_own_source_observation(tmp_path):
    relay,main,sidecar,now=files(tmp_path)
    data=payload('5m',now,50)
    boundary=now//300000*300000
    data['source_observed_at_ms']={'BTC/USDT:USDT':{'binance':boundary-1}}
    sidecar.write_text(json.dumps(data))
    with pytest.raises(RuntimeError): relay.fetch_volume('binance','BTCUSDT','5m')
