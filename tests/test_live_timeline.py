import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from universal_bot import live_timeline as live


class LiveTimelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = str(Path(self.tmp.name) / 'base.db')
        self.tail = str(Path(self.tmp.name) / 'tail.sqlite')
        with sqlite3.connect(self.base) as db:
            db.execute('CREATE TABLE ohlcv(asset_class,exchange,symbol,timeframe,timestamp,open,high,low,close,volume,PRIMARY KEY(asset_class,exchange,symbol,timeframe,timestamp))')
            db.executemany('INSERT INTO ohlcv VALUES(?,?,?,?,?,?,?,?,?,?)', [(*live.MARKET, i*live.STEP, 100,102,98,101,10) for i in range(40)])
        self.before = Path(self.base).read_bytes()

    def feed(self, indices, close=101, now=100*live.STEP):
        return live.ingest(self.tail, json.dumps([[i*live.STEP,100,102,98,close,10] for i in indices]), now)

    def test_merge_dedup_and_original_unchanged(self):
        self.feed(range(39,45),102)
        self.feed(range(39,45),102)
        page = json.loads(live.page(self.base,self.tail,0,100,True))
        self.assertEqual(page['total'],45)
        self.assertEqual(page['rows'][39][4],102)
        self.assertEqual(page['missing'],0)
        self.assertEqual(Path(self.base).read_bytes(),self.before)
        self.assertEqual(live.offset_for_timestamp(self.base,self.tail,44*live.STEP),44)

    def test_forming_update_and_confirmation(self):
        self.feed([40],100,40*live.STEP+1000)
        self.feed([40],102,41*live.STEP)
        self.feed([40],99,40*live.STEP+2000)
        with sqlite3.connect(self.tail) as db:
            self.assertEqual(db.execute('SELECT close,confirmed FROM candles').fetchone(),(102,1))

    def test_gap_backfill_and_historical_anchor(self):
        self.feed([40,44,45])
        self.assertEqual(live.gap_before(self.base,self.tail),44*live.STEP-1)
        self.assertEqual(json.loads(live.page(self.base,self.tail,0,100))['missing'],3)
        old = json.loads(live.page(self.base,self.tail,0,30))['rows']
        self.feed([41,42,43,46])
        self.assertEqual(live.gap_before(self.base,self.tail),0)
        self.assertEqual(json.loads(live.page(self.base,self.tail,0,30))['rows'],old)

    def test_invalid_batch_does_not_write(self):
        with self.assertRaises(ValueError):
            live.ingest(self.tail,json.dumps([[40*live.STEP,100,90,98,101,1]]),41*live.STEP)
        with sqlite3.connect(self.tail) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM candles').fetchone()[0],0)
