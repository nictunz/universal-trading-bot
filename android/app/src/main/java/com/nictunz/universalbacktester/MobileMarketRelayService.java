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
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

public class MobileMarketRelayService extends Service {
    public static final String ACTION_START = "com.nictunz.universalbacktester.RELAY_START";
    public static final String ACTION_STOP = "com.nictunz.universalbacktester.RELAY_STOP";
    public static final String ACTION_ONCE = "com.nictunz.universalbacktester.RELAY_ONCE";

    private static final String CHANNEL_ID = "market_relay";
    private static final int NOTIFICATION_ID = 4401;
    private static final int RELAY_INTERVAL_SECONDS = 30;
    private static final String RELAY_TIMEFRAME = "15m";
    private static final int CANDLE_LIMIT = 240;
    private static final int MAX_HISTORY_LINES = 300;

    private ScheduledExecutorService scheduler;
    private SshBridge.RelayClient relayClient;
    private PowerManager.WakeLock wakeLock;
    private volatile boolean continuous = false;

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
        appendHistory("시작", "30초 실시간 중계를 시작했습니다.");
        scheduler = Executors.newSingleThreadScheduledExecutor();
        scheduler.scheduleWithFixedDelay(() -> {
            try {
                relayCycle();
            } catch (Exception e) {
                recordFailure(e);
            }
        }, 0, RELAY_INTERVAL_SECONDS, TimeUnit.SECONDS);
    }

    private synchronized void runOneShot() {
        if (scheduler != null && !scheduler.isShutdown()) return;
        continuous = false;
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

        JSONObject payload = new JSONObject();
        payload.put("schema_version", 1);
        payload.put("generated_at_ms", System.currentTimeMillis());
        payload.put("timeframe", RELAY_TIMEFRAME);
        payload.put("source", "android-public-futures-rest");

        JSONObject markets = new JSONObject();
        addSymbol(markets, "BTC/USDT:USDT", "BTCUSDT");
        addSymbol(markets, "ETH/USDT:USDT", "ETHUSDT");
        payload.put("markets", markets);

        if (relayClient == null || !relayClient.isConnected()) {
            closeRelayClient();
            relayClient = new SshBridge.RelayClient(host, user, keyPath);
        }
        String remotePath = remoteDir.replaceAll("/+$", "") + "/mobile-market-relay.json";
        relayClient.uploadTextAtomic(remotePath, payload.toString());

        long now = System.currentTimeMillis();
        String status = "정상 · Binance/Bybit 선물 · BTC/ETH · 15분봉 · 30초 중계";
        p.edit()
                .putBoolean("relay_running", continuous)
                .putLong("relay_last_ok_ms", now)
                .putString("relay_status", status)
                .putString("relay_last_error", "")
                .apply();
        appendHistory("성공", status);
        updateNotification(status);
    }

    private void addSymbol(JSONObject markets, String canonical, String exchangeSymbol) throws Exception {
        JSONObject streams = new JSONObject();
        streams.put("binance", fetchBinance(exchangeSymbol));
        streams.put("bybit", fetchBybit(exchangeSymbol));
        markets.put(canonical, streams);
    }

    private JSONArray fetchBinance(String symbol) throws Exception {
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

    private JSONArray fetchBybit(String symbol) throws Exception {
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
        conn.setConnectTimeout(12000);
        conn.setReadTimeout(15000);
        conn.setRequestMethod("GET");
        conn.setRequestProperty("User-Agent", "UniversalTradingBot-Android/1");
        int status = conn.getResponseCode();
        BufferedReader reader = new BufferedReader(new InputStreamReader(
                status >= 200 && status < 300 ? conn.getInputStream() : conn.getErrorStream(),
                StandardCharsets.UTF_8
        ));
        StringBuilder sb = new StringBuilder();
        String line;
        while ((line = reader.readLine()) != null) sb.append(line);
        reader.close();
        conn.disconnect();
        if (status < 200 || status >= 300) {
            throw new IllegalStateException("HTTP " + status + " " + sb.substring(0, Math.min(180, sb.length())));
        }
        return sb.toString();
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
