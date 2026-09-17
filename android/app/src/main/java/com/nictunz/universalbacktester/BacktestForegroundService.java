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

import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class BacktestForegroundService extends Service {
    public static final String ACTION_START = "com.nictunz.universalbacktester.BACKTEST_START";
    public static final String ACTION_PAUSE = "com.nictunz.universalbacktester.BACKTEST_PAUSE";
    public static final String ACTION_RESUME = "com.nictunz.universalbacktester.BACKTEST_RESUME";
    public static final String ACTION_STOP = "com.nictunz.universalbacktester.BACKTEST_STOP";
    public static final String ACTION_DOWNLOAD_DB = "com.nictunz.universalbacktester.DB_DOWNLOAD";

    private static final String CHANNEL_ID = "backtest_worker";
    private static final int NOTIFICATION_ID = 4501;
    private ExecutorService executor;
    private PowerManager.WakeLock wakeLock;
    private static volatile boolean working;
    private static volatile boolean stopRequested;

    public static boolean isStopRequested() {
        return stopRequested;
    }

    public static boolean isWorkerRunning() {
        return working;
    }

    @Override
    public void onCreate() {
        super.onCreate();
        createNotificationChannel();
        PowerManager pm = (PowerManager) getSystemService(POWER_SERVICE);
        wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "UniversalBacktester:Backtest");
        wakeLock.setReferenceCounted(false);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        String action = intent == null ? null : intent.getAction();
        if (ACTION_PAUSE.equals(action)) {
            setPythonPaused(true);
            prefs().edit().putBoolean("backtest_paused", true).putString("backtest_status", "PAUSED").apply();
            updateNotification("일시중지됨 · 재개 가능");
            return START_STICKY;
        }
        if (ACTION_RESUME.equals(action)) {
            setPythonPaused(false);
            prefs().edit().putBoolean("backtest_paused", false).putString("backtest_status", "RUNNING").apply();
            updateNotification("백테스트 실행 중");
            return START_STICKY;
        }
        if (ACTION_STOP.equals(action)) {
            stopRequested = true;
            prefs().edit().putBoolean("backtest_requested", false).putBoolean("backtest_paused", false)
                    .putString("backtest_status", "STOPPING").apply();
            requestPythonStop();
            updateNotification("중지 중 · 체크포인트 저장");
            return START_NOT_STICKY;
        }

        if(working && (ACTION_START.equals(action)||ACTION_DOWNLOAD_DB.equals(action))) return START_STICKY;
        JSONObject request;
        try {
            if ((ACTION_START.equals(action) || ACTION_DOWNLOAD_DB.equals(action)) && intent != null) {
                stopRequested = false;
                request = requestFromIntent(intent);
                request.put("db_only", ACTION_DOWNLOAD_DB.equals(action));
                prefs().edit().putString("backtest_request", request.toString())
                        .putBoolean("backtest_requested", true)
                        .putBoolean("backtest_paused", false)
                        .putString("backtest_status", "RUNNING")
                        .putString("backtest_log", "")
                        .putString("backtest_result", "")
                        .putString("backtest_error", "")
                        .apply();
            } else {
                if (!prefs().getBoolean("backtest_requested", false)) {
                    stopSelf();
                    return START_NOT_STICKY;
                }
                request = new JSONObject(prefs().getString("backtest_request", "{}"));
            }
        } catch (Exception e) {
            recordError(e);
            return START_NOT_STICKY;
        }

        startForeground(NOTIFICATION_ID, notification("백테스트 준비 중"));
        if (!wakeLock.isHeld()) wakeLock.acquire();
        startWorker(request);
        return START_STICKY;
    }

    private synchronized void startWorker(JSONObject request) {
        if (working) return;
        working = true;
        executor = Executors.newSingleThreadExecutor();
        executor.execute(() -> runBacktest(request));
    }

    private void runBacktest(JSONObject request) {
        try {
            if (!Python.isStarted()) {
                Python.start(new AndroidPlatform(getApplicationContext()));
            }
            PyObject bridge = Python.getInstance().getModule("mobile_bridge");
            bridge.callAttr("reset_optimization_control");
            if (prefs().getBoolean("backtest_paused", false)) {
                bridge.callAttr("set_optimization_paused", true);
            }
            updateNotification(request.optBoolean("db_only", false)
                    ? "DB 다운로드 중 · 화면을 꺼도 계속됩니다"
                    : "백테스트 실행 중 · 화면을 꺼도 계속됩니다");
            String response;
            if (request.optBoolean("db_only", false)) {
                response = bridge.callAttr(
                        "download_cache_only",
                        request.getString("symbol"),
                        request.getString("timeframe"),
                        request.getString("start"),
                        request.getString("end"),
                        request.getString("output_dir")
                ).toString();
            } else if (request.optBoolean("priority_live_parity", false)) {
                updateNotification("LIVE 5분+15분 통합 백테스트 실행 중");
                response = bridge.callAttr(
                    "run_priority_live_backtest",
                    request.getString("symbol"), request.getString("start"), request.getString("end"),
                    request.getString("output_dir"), request.optString("database_path", ""),
                    request.optDouble("initial_capital", 1000.0), request.optBoolean("compounding_enabled", true)
                ).toString();
            } else {
                response = bridge.callAttr(
                    "run_backtest",
                    request.getString("symbol"),
                    request.getString("timeframe"),
                    request.getString("start"),
                    request.getString("end"),
                    request.getString("output_dir"),
                    request.optString("host"),
                    request.optString("username"),
                    request.optString("remote_dir"),
                    request.optString("key_path"),
                    request.optString("risk_profile", "공격형"),
                    request.optInt("broad_optimization_trials", request.optInt("optimization_trials", 1000)),
                    request.optInt("refine_optimization_trials", request.optInt("optimization_trials", 1000)),
                    request.optBoolean("compounding_enabled", true),
                    request.optString("optimization_stage", "broad"),
                    request.optBoolean("all_entries_three_tick", false),
                    request.optString("selected_parameters_json", ""),
                    request.optString("execution_model", "signal_close"),
                    request.optString("optimization_speed", "quick"),
                    request.optBoolean("precheck_enabled", true),
                    request.optBoolean("adaptive_regime_enabled", false),
                    request.optDouble("initial_capital", 1000.0),
                    request.optString("database_path", "")
                ).toString();
            }
            JSONObject obj = new JSONObject(response);
            StringBuilder logs = new StringBuilder();
            JSONArray rows = obj.optJSONArray("logs");
            if (rows != null) {
                for (int i = 0; i < rows.length(); i++) logs.append(rows.optString(i)).append('\n');
            }
            prefs().edit()
                    .putBoolean("backtest_requested", false)
                    .putBoolean("backtest_paused", false)
                    .putString("backtest_status", "COMPLETE")
                    .putString("backtest_db", obj.optString("db"))
                    .putString("backtest_result", obj.optString("result"))
                    .putString("backtest_log", trimLog(logs.toString()))
                    .putString("backtest_error", "")
                    .apply();
            updateNotification(request.optBoolean("db_only", false)
                    ? "DB 다운로드 완료 · 앱에서 차트를 열 수 있습니다"
                    : "백테스트 완료 · 앱에서 결과 확인");
        } catch (Exception e) {
            if (!prefs().getBoolean("backtest_requested", false)) {
                prefs().edit().putString("backtest_status", "STOPPED")
                        .putString("backtest_error", "")
                        .apply();
                updateNotification("백테스트 중지됨 · 체크포인트 보존");
            } else {
                recordError(e);
            }
        } finally {
            working = false;
            releaseWakeLock();
            stopForeground(false);
            stopSelf();
        }
    }

    private JSONObject requestFromIntent(Intent intent) throws Exception {
        JSONObject request = new JSONObject();
        request.put("symbol", intent.getStringExtra("symbol"));
        request.put("chart_request_id", intent.getStringExtra("chart_request_id"));
        request.put("timeframe", intent.getStringExtra("timeframe"));
        request.put("start", intent.getStringExtra("start"));
        request.put("end", intent.getStringExtra("end"));
        request.put("output_dir", new File(getFilesDir(), "UniversalTradingBotCache").getAbsolutePath());
        request.put("host", intent.getStringExtra("host"));
        request.put("username", intent.getStringExtra("username"));
        request.put("remote_dir", intent.getStringExtra("remote_dir"));
        request.put("key_path", intent.getStringExtra("key_path"));
        request.put("risk_profile", intent.getStringExtra("risk_profile"));
        request.put("optimization_trials", intent.getIntExtra("optimization_trials", 1000));
        request.put("broad_optimization_trials", intent.getIntExtra("broad_optimization_trials", intent.getIntExtra("optimization_trials", 1000)));
        request.put("refine_optimization_trials", intent.getIntExtra("refine_optimization_trials", intent.getIntExtra("optimization_trials", 1000)));
        request.put("all_entries_three_tick", intent.getBooleanExtra("all_entries_three_tick", false));
        request.put("compounding_enabled", intent.getBooleanExtra("compounding_enabled", true));
        request.put("initial_capital", intent.getDoubleExtra("initial_capital", 1000.0));
        request.put("optimization_stage", intent.getStringExtra("optimization_stage"));
        request.put("selected_parameters_json", intent.getStringExtra("selected_parameters_json"));
        request.put("execution_model", intent.getStringExtra("execution_model"));
        request.put("optimization_speed", intent.getStringExtra("optimization_speed"));
        request.put("precheck_enabled", intent.getBooleanExtra("precheck_enabled", true));
        request.put("adaptive_regime_enabled", intent.getBooleanExtra("adaptive_regime_enabled", false));
        request.put("database_path", intent.getStringExtra("database_path"));
        request.put("priority_live_parity", intent.getBooleanExtra("priority_live_parity", false));
        return request;
    }

    private void setPythonPaused(boolean paused) {
        try {
            if (Python.isStarted()) Python.getInstance().getModule("mobile_bridge")
                    .callAttr("set_optimization_paused", paused);
        } catch (Exception ignored) {
        }
    }

    private void requestPythonStop() {
        try {
            if (Python.isStarted()) Python.getInstance().getModule("mobile_bridge")
                    .callAttr("request_optimization_stop");
        } catch (Exception ignored) {
        }
    }

    private void recordError(Exception e) {
        String message = e.getClass().getSimpleName() + ": " + String.valueOf(e.getMessage());
        if (message.length() > 4000) message = message.substring(0, 4000);
        prefs().edit().putBoolean("backtest_requested", false)
                .putBoolean("backtest_paused", false)
                .putString("backtest_status", "ERROR")
                .putString("backtest_error", message)
                .apply();
        updateNotification("백테스트 오류 · 앱에서 로그 확인");
        releaseWakeLock();
    }

    private String trimLog(String value) {
        int limit = 50000;
        return value.length() <= limit ? value : value.substring(value.length() - limit);
    }

    private void releaseWakeLock() {
        if (wakeLock != null && wakeLock.isHeld()) wakeLock.release();
    }

    @Override
    public void onDestroy() {
        releaseWakeLock();
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
                    CHANNEL_ID, "백그라운드 백테스트", NotificationManager.IMPORTANCE_LOW);
            channel.setDescription("장시간 캐시 생성과 전략 최적화를 백그라운드에서 실행합니다.");
            ((NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE))
                    .createNotificationChannel(channel);
        }
    }

    private PendingIntent action(String action, int requestCode) {
        Intent intent = new Intent(this, BacktestForegroundService.class);
        intent.setAction(action);
        return PendingIntent.getService(this, requestCode, intent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }

    private Notification notification(String text) {
        Intent launch = new Intent(this, MainActivity.class);
        PendingIntent open = PendingIntent.getActivity(this, 0, launch,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        Notification.Builder builder = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                ? new Notification.Builder(this, CHANNEL_ID) : new Notification.Builder(this);
        boolean paused = prefs().getBoolean("backtest_paused", false);
        builder.setContentTitle("Universal Trading Bot · 백테스트")
                .setContentText(text)
                .setSmallIcon(android.R.drawable.stat_notify_sync)
                .setOngoing(prefs().getBoolean("backtest_requested", false))
                .setContentIntent(open)
                .addAction(0, paused ? "재개" : "일시중지",
                        action(paused ? ACTION_RESUME : ACTION_PAUSE, 1))
                .addAction(0, "중지", action(ACTION_STOP, 2));
        return builder.build();
    }

    private void updateNotification(String text) {
        ((NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE))
                .notify(NOTIFICATION_ID, notification(text));
    }
}
