package com.nictunz.universalbacktester;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;
import android.os.IBinder;
import android.os.PowerManager;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

public class MobileMarketRelayService extends Service {
    public static final String ACTION_START = "com.nictunz.universalbacktester.RELAY_START";
    public static final String ACTION_STOP = "com.nictunz.universalbacktester.RELAY_STOP";
    public static final String ACTION_ONCE = "com.nictunz.universalbacktester.RELAY_ONCE";

    private static final String CHANNEL_ID = "market_relay";
    private static final int NOTIFICATION_ID = 4401;
    private static final long NORMAL_INTERVAL_MILLIS = 30_000L;
    private static final long PRE_BOUNDARY_INTERVAL_MILLIS = 5_000L;
    private static final long POST_BOUNDARY_INTERVAL_MILLIS = 1_000L;
    private static final long BOUNDARY_WINDOW_MILLIS = 60_000L;
    // Boundary reads start at +1s so a just-closed exchange candle has time to roll over.
    private static final long RELAY_PHASE_MILLIS = 1_000L;
    private static final long TIMEFRAME_MILLIS = 15L * 60L * 1_000L;
    // First read at about +1s, then retry at about +2s and +4s if needed.
    private static final long[] ROLLOVER_RETRY_DELAYS_MS = {0L, 1_000L, 2_000L};
    private static final String RELAY_TIMEFRAME = "15m";
    private static final int CANDLE_LIMIT = 240;
    private static final int MAX_HISTORY_LINES = 300;

    private ScheduledExecutorService scheduler;
    private ExecutorService marketFetchPool;
    private SshBridge.RelayClient relayClient;
    private PowerManager.WakeLock wakeLock;
    private volatile boolean continuous = false;
    private volatile long confirmedBoundaryOpenMs = Long.MIN_VALUE;

    private interface VenueRequest {
        JSONArray fetch() throws Exception;
    }

    private static final class RelayFetch {
        final JSONArray rows;
        final long observedAtMs;

        RelayFetch(JSONArray rows, long observedAtMs) {
            this.rows = rows;
            this.observedAtMs = observedAtMs;
        }
    }

    @Override
    public void onCreate() {
        super.onCreate();
        createNotificationChannel();
        PowerManager pm = (PowerManager) getSystemService(POWER_SERVICE);
        wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "UniversalBacktester:MarketRelay");
        wakeLock.setReferenceCounted(false);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        String action = intent == null ? null : intent.getAction();
        SharedPreferences prefs = prefs();

        if (ACTION_STOP.equals(action)) {
            prefs.edit().putBoolean("relay_requested", false).apply();
            stopRelay();
            return START_NOT_STICKY;
        }

        boolean oneShot = ACTION_ONCE.equals(action);
        if (!oneShot && action == null && !prefs.getBoolean("relay_requested", false)) {
            stopSelf();
            return START_NOT_STICKY;
        }

        startForeground(NOTIFICATION_ID, notification("중계 준비 중..."));
        if (!wakeLock.isHeld()) wakeLock.acquire();

        if (oneShot) {
            runOneShot();
            return START_NOT_STICKY;
        }

        prefs.edit().putBoolean("relay_requested", true).putBoolean("relay_running", true).apply();
        startContinuous();
        return START_STICKY;
    }

    private synchronized void startContinuous() {
        if (scheduler != null && !scheduler.isShutdown()) return;
        continuous = true;
        ensureFetchPool();
        appendHistory("시작", "평상시 30초 · 경계 전 5초 · 경계 후 1초 중계를 시작했습니다.");
        scheduler = Executors.newSingleThreadScheduledExecutor();
        scheduleNextRelay(true);
    }

    private void runScheduledCycle() {
        try {
            relayCycle();
        } catch (Exception e) {
            recordFailure(e);
        } finally {
            scheduleNextRelay(false);
        }
    }

    private synchronized void scheduleNextRelay(boolean first) {
        if (!continuous || scheduler == null || scheduler.isShutdown()) return;
        long delay = millisUntilNextRelaySlot(
                System.currentTimeMillis(),
                confirmedBoundaryOpenMs
        );
        // A completed cycle landing exactly on a slot must not run twice.
        if (!first && delay < 50L) delay = 50L;
        try {
            scheduler.schedule(this::runScheduledCycle, delay, TimeUnit.MILLISECONDS);
        } catch (RejectedExecutionException ignored) {
            // Expected only when ACTION_STOP races with a completed cycle.
        }
    }

    static long millisUntilNextRelaySlot(long nowMs, long confirmedBoundaryOpenMs) {
        long currentBoundary = nowMs - Math.floorMod(nowMs, TIMEFRAME_MILLIS);
        long elapsed = nowMs - currentBoundary;
        boolean awaitingBoundary = elapsed < BOUNDARY_WINDOW_MILLIS
                && confirmedBoundaryOpenMs != currentBoundary;

        long interval;
        long phase;
        long regimeEnd;
        if (awaitingBoundary) {
            interval = POST_BOUNDARY_INTERVAL_MILLIS;
            phase = currentBoundary + RELAY_PHASE_MILLIS;
            regimeEnd = currentBoundary + BOUNDARY_WINDOW_MILLIS;
        } else {
            long nextBoundary = currentBoundary + TIMEFRAME_MILLIS;
            long preBoundaryStart = nextBoundary - BOUNDARY_WINDOW_MILLIS;
            if (nowMs >= preBoundaryStart) {
                interval = PRE_BOUNDARY_INTERVAL_MILLIS;
                phase = preBoundaryStart;
                regimeEnd = nextBoundary + RELAY_PHASE_MILLIS;
            } else {
                interval = NORMAL_INTERVAL_MILLIS;
                phase = currentBoundary + BOUNDARY_WINDOW_MILLIS;
                regimeEnd = preBoundaryStart;
            }
        }

        long offset = Math.floorMod(nowMs - phase, interval);
        long next = nowMs < phase
                ? phase
                : (offset == 0L ? nowMs : nowMs + interval - offset);
        return Math.max(0L, Math.min(next, regimeEnd) - nowMs);
    }

    private synchronized ExecutorService ensureFetchPool() {
        if (marketFetchPool == null || marketFetchPool.isShutdown()) {
            // Binance/Bybit and BTC/ETH are independent public reads. Fetching
            // in parallel prevents an unrelated ETH request delaying BTC LIVE.
            marketFetchPool = Executors.newFixedThreadPool(4);
        }
        return marketFetchPool;
    }

    private synchronized void runOneShot() {
        if (scheduler != null && !scheduler.isShutdown()) return;
        continuous = false;
        ensureFetchPool();
        scheduler = Executors.newSingleThreadScheduledExecutor();
        scheduler.execute(() -> {
            try {
                relayCycle();
            } catch (Exception e) {
                recordFailure(e);
            } finally {
                prefs().edit().putBoolean("relay_running", false).apply();
                stopSelf();
            }
        });
    }

    private void relayCycle() throws Exception {
        SharedPreferences p = prefs();
        String host = p.getString("relay_host", "34.132.172.40").trim();
        String user = p.getString("relay_user", "kpj3669").trim();
        String remoteDir = p.getString("relay_remote_dir", "/home/kpj3669/.cache/universal-trading-bot").trim();
        String keyPath = p.getString("relay_key_path", "").trim();
        if (host.isEmpty() || user.isEmpty() || remoteDir.isEmpty() || keyPath.isEmpty()) {
            throw new IllegalStateException("서버/SSH 키 설정이 비어 있습니다.");
        }

        long cycleStartedAt = System.currentTimeMillis();
        ExecutorService pool = ensureFetchPool();
        Future<RelayFetch> btcBinanceFuture = pool.submit(() -> fetchWithRolloverRetry(
                "Binance", "BTCUSDT", () -> fetchBinanceRows("BTCUSDT")));
        Future<RelayFetch> btcBybitFuture = pool.submit(() -> fetchWithRolloverRetry(
                "Bybit", "BTCUSDT", () -> fetchBybitRows("BTCUSDT")));
        Future<RelayFetch> ethBinanceFuture = pool.submit(() -> fetchWithRolloverRetry(
                "Binance", "ETHUSDT", () -> fetchBinanceRows("ETHUSDT")));
        Future<RelayFetch> ethBybitFuture = pool.submit(() -> fetchWithRolloverRetry(
                "Bybit", "ETHUSDT", () -> fetchBybitRows("ETHUSDT")));

        RelayFetch btcBinance;
        RelayFetch btcBybit;
        RelayFetch ethBinance;
        RelayFetch ethBybit;
        try {
            btcBinance = await(btcBinanceFuture);
            btcBybit = await(btcBybitFuture);
            ethBinance = await(ethBinanceFuture);
            ethBybit = await(ethBybitFuture);
        } catch (Exception e) {
            btcBinanceFuture.cancel(true);
            btcBybitFuture.cancel(true);
            ethBinanceFuture.cancel(true);
            ethBybitFuture.cancel(true);
            throw e;
        }

        JSONObject payload = new JSONObject();
        payload.put("schema_version", 1);
        // Retain the conservative cycle start for older server versions.
        payload.put("generated_at_ms", cycleStartedAt);
        payload.put("timeframe", RELAY_TIMEFRAME);
        payload.put("source", "android-public-futures-rest");

        JSONObject markets = new JSONObject();
        JSONObject sourceObservedAt = new JSONObject();
        addSymbol(markets, sourceObservedAt, "BTC/USDT:USDT", btcBinance, btcBybit);
        addSymbol(markets, sourceObservedAt, "ETH/USDT:USDT", ethBinance, ethBybit);
        payload.put("markets", markets);
        payload.put("source_observed_at_ms", sourceObservedAt);
        payload.put("snapshot_completed_at_ms", Math.max(cycleStartedAt, System.currentTimeMillis()));

        if (relayClient == null || !relayClient.isConnected()) {
            closeRelayClient();
            relayClient = new SshBridge.RelayClient(host, user, keyPath);
        }
        String remotePath = remoteDir.replaceAll("/+$", "") + "/mobile-market-relay.json";
        relayClient.uploadTextAtomic(remotePath, payload.toString());

        long now = System.currentTimeMillis();
        long boundary = now - Math.floorMod(now, TIMEFRAME_MILLIS);
        if (now - boundary < BOUNDARY_WINDOW_MILLIS) {
            // All four requests passed rollover validation and the atomic SSH upload
            // completed, so the server has the newly opened candle snapshot.
            confirmedBoundaryOpenMs = boundary;
        }
        String status = "정상 · Binance/Bybit 선물 · BTC/ETH · 15분봉 · 적응형 경계동기";
        p.edit()
                .putBoolean("relay_running", continuous)
                .putLong("relay_last_ok_ms", now)
                .putString("relay_status", status)
                .putString("relay_last_error", "")
                .apply();
        appendHistory("성공", status);
        updateNotification(status);
    }

    private void addSymbol(
            JSONObject markets,
            JSONObject sourceObservedAt,
            String canonical,
            RelayFetch binance,
            RelayFetch bybit
    ) throws Exception {
        JSONObject streams = new JSONObject();
        streams.put("binance", binance.rows);
        streams.put("bybit", bybit.rows);
        markets.put(canonical, streams);

        JSONObject observations = new JSONObject();
        observations.put("binance", binance.observedAtMs);
        observations.put("bybit", bybit.observedAtMs);
        sourceObservedAt.put(canonical, observations);
    }

    private RelayFetch fetchWithRolloverRetry(
            String exchange,
            String symbol,
            VenueRequest request
    ) throws Exception {
        RelayFetch last = null;
        for (long delay : ROLLOVER_RETRY_DELAYS_MS) {
            if (delay > 0L) Thread.sleep(delay);
            long observedAt = System.currentTimeMillis();
            JSONArray rows = request.fetch();
            last = new RelayFetch(rows, observedAt);
            if (rolledOverForBoundary(rows, observedAt)) return last;
        }
        throw new IllegalStateException(
                exchange + " " + symbol + " 15분봉 경계 갱신 지연; 이전 정상 스냅샷을 유지합니다."
        );
    }

    private static boolean rolledOverForBoundary(JSONArray rows, long observedAtMs) {
        long elapsed = Math.floorMod(observedAtMs, TIMEFRAME_MILLIS);
        // Outside the post-boundary focus window no rollover confirmation is
        // needed. Inside it, never accept a stale previous candle merely
        // because a slow network request crossed the short retry window.
        if (elapsed >= BOUNDARY_WINDOW_MILLIS) return true;
        long expectedCurrentOpen = observedAtMs - elapsed;
        long latestOpen = Long.MIN_VALUE;
        for (int i = 0; i < rows.length(); i++) {
            JSONArray row = rows.optJSONArray(i);
            if (row != null && row.length() >= 1) {
                latestOpen = Math.max(latestOpen, row.optLong(0, Long.MIN_VALUE));
            }
        }
        return latestOpen >= expectedCurrentOpen;
    }

    private static RelayFetch await(Future<RelayFetch> future) throws Exception {
        try {
            return future.get();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw e;
        } catch (ExecutionException e) {
            Throwable cause = e.getCause();
            if (cause instanceof Exception) throw (Exception) cause;
            throw new IllegalStateException("거래소 중계 작업 실패", cause);
        }
    }

    private JSONArray fetchBinanceRows(String symbol) throws Exception {
        String url = "https://fapi.binance.com/fapi/v1/klines?symbol=" + symbol
                + "&interval=" + RELAY_TIMEFRAME + "&limit=" + CANDLE_LIMIT;
        Object body = new org.json.JSONTokener(get(url)).nextValue();
        if (!(body instanceof JSONArray)) throw new IllegalStateException("Binance 응답 형식 오류");
        JSONArray rows = (JSONArray) body;
        JSONArray out = new JSONArray();
        for (int i = 0; i < rows.length(); i++) {
            JSONArray row = rows.optJSONArray(i);
            if (row == null || row.length() < 6) continue;
            JSONArray compact = new JSONArray();
            compact.put(row.optLong(0));
            compact.put(Double.parseDouble(row.optString(5, "0")));
            out.put(compact);
        }
        if (out.length() < 200) throw new IllegalStateException("Binance 선물 캔들이 부족합니다: " + out.length());
        return out;
    }

    private JSONArray fetchBybitRows(String symbol) throws Exception {
        String url = "https://api.bybit.com/v5/market/kline?category=linear&symbol=" + symbol
                + "&interval=15&limit=" + CANDLE_LIMIT;
        JSONObject body = new JSONObject(get(url));
        if (!"0".equals(String.valueOf(body.opt("retCode")))) {
            throw new IllegalStateException("Bybit 오류: " + body.optString("retMsg"));
        }
        JSONObject result = body.optJSONObject("result");
        JSONArray rows = result == null ? null : result.optJSONArray("list");
        if (rows == null) throw new IllegalStateException("Bybit 응답 형식 오류");
        JSONArray out = new JSONArray();
        for (int i = 0; i < rows.length(); i++) {
            JSONArray row = rows.optJSONArray(i);
            if (row == null || row.length() < 6) continue;
            JSONArray compact = new JSONArray();
            compact.put(Long.parseLong(row.optString(0, "0")));
            compact.put(Double.parseDouble(row.optString(5, "0")));
            out.put(compact);
        }
        if (out.length() < 200) throw new IllegalStateException("Bybit 선물 캔들이 부족합니다: " + out.length());
        return out;
    }

    private String get(String target) throws Exception {
        HttpURLConnection conn = (HttpURLConnection) new URL(target).openConnection();
        try {
            conn.setConnectTimeout(12000);
            conn.setReadTimeout(15000);
            conn.setRequestMethod("GET");
            conn.setRequestProperty("User-Agent", "UniversalTradingBot-Android/1");
            int status = conn.getResponseCode();
            InputStream stream = status >= 200 && status < 300
                    ? conn.getInputStream()
                    : conn.getErrorStream();
            if (stream == null) throw new IllegalStateException("HTTP " + status + " 빈 응답");
            StringBuilder sb = new StringBuilder();
            try (BufferedReader reader = new BufferedReader(new InputStreamReader(
                    stream,
                    StandardCharsets.UTF_8
            ))) {
                String line;
                while ((line = reader.readLine()) != null) sb.append(line);
            }
            if (status < 200 || status >= 300) {
                throw new IllegalStateException(
                        "HTTP " + status + " " + sb.substring(0, Math.min(180, sb.length()))
                );
            }
            return sb.toString();
        } finally {
            conn.disconnect();
        }
    }

    private void recordFailure(Exception e) {
        closeRelayClient();
        String message = e.getClass().getSimpleName() + ": " + String.valueOf(e.getMessage());
        if (message.length() > 220) message = message.substring(0, 220);
        prefs().edit()
                .putBoolean("relay_running", continuous)
                .putString("relay_status", "오류 · " + message)
                .putString("relay_last_error", message)
                .apply();
        appendHistory("오류", message);
        updateNotification("오류 · 앱에서 상태 확인");
    }

    private synchronized void stopRelay() {
        continuous = false;
        if (scheduler != null) {
            scheduler.shutdownNow();
            scheduler = null;
        }
        if (marketFetchPool != null) {
            marketFetchPool.shutdownNow();
            marketFetchPool = null;
        }
        closeRelayClient();
        appendHistory("중지", "중계를 중지했습니다.");
        prefs().edit().putBoolean("relay_running", false).apply();
        stopForeground(STOP_FOREGROUND_REMOVE);
        stopSelf();
    }

    private synchronized void appendHistory(String kind, String detail) {
        String clean = String.valueOf(detail).replace('\n', ' ').replace('\r', ' ').trim();
        String timestamp = new SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.KOREA)
                .format(new Date());
        String entry = timestamp + " · " + kind + " · " + clean;
        SharedPreferences p = prefs();
        String previous = p.getString("relay_log_history", "");
        String combined = previous.isEmpty() ? entry : previous + "\n" + entry;
        String[] lines = combined.split("\\n");
        int start = Math.max(0, lines.length - MAX_HISTORY_LINES);
        StringBuilder kept = new StringBuilder();
        for (int i = start; i < lines.length; i++) {
            if (kept.length() > 0) kept.append('\n');
            kept.append(lines[i]);
        }
        p.edit().putString("relay_log_history", kept.toString()).apply();
    }

    private void closeRelayClient() {
        if (relayClient != null) {
            relayClient.close();
            relayClient = null;
        }
    }

    @Override
    public void onDestroy() {
        continuous = false;
        if (scheduler != null) scheduler.shutdownNow();
        if (marketFetchPool != null) marketFetchPool.shutdownNow();
        closeRelayClient();
        prefs().edit().putBoolean("relay_running", false).apply();
        if (wakeLock != null && wakeLock.isHeld()) wakeLock.release();
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private SharedPreferences prefs() {
        return getSharedPreferences("universal_bot", MODE_PRIVATE);
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                    CHANNEL_ID,
                    "실시간 선물 데이터 중계",
                    NotificationManager.IMPORTANCE_LOW
            );
            channel.setDescription("Binance/Bybit 공개 선물 거래량을 Bitget LIVE 서버로 중계합니다.");
            ((NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE)).createNotificationChannel(channel);
        }
    }

    private Notification notification(String text) {
        Intent launch = new Intent(this, LauncherActivity.class);
        PendingIntent pi = PendingIntent.getActivity(
                this,
                0,
                launch,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );
        Notification.Builder b = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                ? new Notification.Builder(this, CHANNEL_ID)
                : new Notification.Builder(this);
        return b.setContentTitle("Universal Trading Bot · 모바일 중계")
                .setContentText(text)
                .setSmallIcon(android.R.drawable.stat_notify_sync)
                .setOngoing(true)
                .setContentIntent(pi)
                .build();
    }

    private void updateNotification(String text) {
        ((NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE))
                .notify(NOTIFICATION_ID, notification(text));
    }
}
