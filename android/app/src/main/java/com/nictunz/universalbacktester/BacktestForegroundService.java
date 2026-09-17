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
import java.util.Locale;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class BacktestForegroundService extends Service {
    public static final String ACTION_START = "com.nictunz.universalbacktester.BACKTEST_START";
    public static final String ACTION_PAUSE = "com.nictunz.universalbacktester.BACKTEST_PAUSE";
    public static final String ACTION_RESUME = "com.nictunz.universalbacktester.BACKTEST_RESUME";
    public static final String ACTION_STOP = "com.nictunz.universalbacktester.BACKTEST_STOP";
    public static final String ACTION_DOWNLOAD_DB = "com.nictunz.universalbacktester.DB_DOWNLOAD";
    private static final String REQUEST_PRIORITY_5M_15M = "PRIORITY_5M_15M";
    private static final String CHANNEL_ID = "backtest_worker";
    private static final int NOTIFICATION_ID = 4501;

    private ExecutorService executor;
    private PowerManager.WakeLock wakeLock;
    private static volatile boolean working;
    private static volatile boolean stopRequested;
    private static volatile String activeRequestId = "";

    public static boolean isStopRequested() { return stopRequested; }
    public static boolean isWorkerRunning() { return working; }

    @Override public void onCreate() {
        super.onCreate();
        createNotificationChannel();
        PowerManager pm = (PowerManager) getSystemService(POWER_SERVICE);
        wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "UniversalBacktester:Backtest");
        wakeLock.setReferenceCounted(false);
    }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        String action = intent == null ? null : intent.getAction();
        if (ACTION_PAUSE.equals(action)) {
            if (!working) return START_NOT_STICKY;
            setPythonPaused(true);
            prefs().edit().putBoolean("backtest_paused", true).putString("backtest_status", "PAUSED").apply();
            updateNotification("일시중지됨 · 재개 가능");
            return START_STICKY;
        }
        if (ACTION_RESUME.equals(action)) {
            if (!working) return START_NOT_STICKY;
            setPythonPaused(false);
            prefs().edit().putBoolean("backtest_paused", false).putString("backtest_status", "RUNNING").apply();
            updateNotification("백테스트 실행 중");
            return START_STICKY;
        }
        if (ACTION_STOP.equals(action)) {
            if (!working) {
                stopRequested = false;
                prefs().edit().putBoolean("backtest_requested", false).putBoolean("backtest_paused", false)
                        .putString("backtest_status", "STOPPED").putString("backtest_error", "").apply();
                updateNotification("작업이 이미 종료되었습니다");
                stopSelfResult(startId);
                return START_NOT_STICKY;
            }
            stopRequested = true;
            prefs().edit().putBoolean("backtest_requested", false).putBoolean("backtest_paused", false)
                    .putString("backtest_status", "STOPPING").apply();
            requestPythonStop();
            updateNotification("중지 중 · 체크포인트 저장");
            return START_NOT_STICKY;
        }

        JSONObject request;
        try {
            if ((ACTION_START.equals(action) || ACTION_DOWNLOAD_DB.equals(action)) && intent != null) {
                request = requestFromIntent(intent);
                boolean priorityRequest = REQUEST_PRIORITY_5M_15M.equals(request.optString("request_type", ""));
                if (priorityRequest && !ACTION_START.equals(action))
                    throw new IllegalArgumentException("PRIORITY_5M_15M must use ACTION_START");
                request.put("db_only", priorityRequest ? false : ACTION_DOWNLOAD_DB.equals(action));
                String requestId = UUID.randomUUID().toString();
                request.put("worker_request_id", requestId);
                synchronized (BacktestForegroundService.class) {
                    if (working) {
                        prefs().edit().putString("backtest_busy_error",
                                "BUSY: 기존 작업이 실행 중입니다. 새 요청은 실행하지 않았습니다.").apply();
                        updateNotification("기존 작업 실행 중 · 새 요청은 실행하지 않음");
                        return START_STICKY;
                    }
                    stopRequested = false;
                    activeRequestId = requestId;
                    prefs().edit().putString("backtest_request", request.toString())
                            .putString("backtest_active_request_id", requestId)
                            .putString("backtest_busy_error", "")
                            .putBoolean("backtest_requested", true).putBoolean("backtest_paused", false)
                            .putString("backtest_status", "RUNNING").putString("backtest_log", "")
                            .putString("backtest_result", "").putString("backtest_error", "").apply();
                    working = true;
                }
            } else {
                if (!prefs().getBoolean("backtest_requested", false)) {
                    stopSelfResult(startId);
                    return START_NOT_STICKY;
                }
                request = new JSONObject(prefs().getString("backtest_request", "{}"));
                String requestId = request.optString("worker_request_id", "");
                synchronized (BacktestForegroundService.class) {
                    if (working) return START_STICKY;
                    if (requestId.isEmpty()) {
                        requestId = UUID.randomUUID().toString();
                        request.put("worker_request_id", requestId);
                    }
                    activeRequestId = requestId;
                    working = true;
                }
            }
        } catch (Exception e) {
            recordError(e, "");
            stopSelfResult(startId);
            return START_NOT_STICKY;
        }

        startForeground(NOTIFICATION_ID, notification("백테스트 준비 중"));
        if (!wakeLock.isHeld()) wakeLock.acquire();
        startWorker(request, startId);
        return START_STICKY;
    }

    private void startWorker(JSONObject request, int startId) {
        executor = Executors.newSingleThreadExecutor();
        executor.execute(() -> runBacktest(request, startId));
    }

    private boolean ownsRequest(String requestId) {
        return requestId != null && !requestId.isEmpty() && requestId.equals(activeRequestId)
                && requestId.equals(prefs().getString("backtest_active_request_id", ""));
    }

    private void runBacktest(JSONObject request, int startId) {
        String requestId = request.optString("worker_request_id", "");
        try {
            if (!Python.isStarted()) Python.start(new AndroidPlatform(getApplicationContext()));
            PyObject bridge = Python.getInstance().getModule("mobile_bridge");
            bridge.callAttr("reset_optimization_control");
            if (prefs().getBoolean("backtest_paused", false)) bridge.callAttr("set_optimization_paused", true);
            updateNotification(request.optBoolean("db_only", false) ? "DB 다운로드 중 · 화면을 꺼도 계속됩니다" : "백테스트 실행 중 · 화면을 꺼도 계속됩니다");
            String response;
            boolean priorityRequest = REQUEST_PRIORITY_5M_15M.equals(request.optString("request_type", ""));
            if (priorityRequest) {
                String databasePath = request.optString("database_path", "");
                File priorityDb = new File(databasePath);
                if (!request.optBoolean("priority_live_parity", false)) throw new IllegalArgumentException("PRIORITY_5M_15M missing priority_live_parity=true");
                if (request.optBoolean("db_only", false)) throw new IllegalArgumentException("PRIORITY_5M_15M cannot run as DB download");
                if (!"5m+15m".equals(request.optString("timeframe", ""))) throw new IllegalArgumentException("PRIORITY_5M_15M requires timeframe=5m+15m");
                if (!priorityDb.isFile() || !priorityDb.getName().toLowerCase(Locale.US).endsWith("-5m.db")) throw new IllegalArgumentException("PRIORITY_5M_15M requires an existing -5m.db source");
                updateNotification("LIVE 5분+15분 통합 백테스트 실행 중");
                response = bridge.callAttr("run_priority_live_backtest", request.getString("symbol"), request.getString("start"), request.getString("end"), request.getString("output_dir"), databasePath, request.optDouble("initial_capital", 1000.0), request.optBoolean("compounding_enabled", true)).toString();
            } else if (request.optBoolean("db_only", false)) {
                response = bridge.callAttr("download_cache_only", request.getString("symbol"), request.getString("timeframe"), request.getString("start"), request.getString("end"), request.getString("output_dir")).toString();
            } else {
                response = bridge.callAttr("run_backtest", request.getString("symbol"), request.getString("timeframe"), request.getString("start"), request.getString("end"), request.getString("output_dir"), request.optString("host"), request.optString("username"), request.optString("remote_dir"), request.optString("key_path"), request.optString("risk_profile", "공격형"), request.optInt("broad_optimization_trials", request.optInt("optimization_trials", 1000)), request.optInt("refine_optimization_trials", request.optInt("optimization_trials", 1000)), request.optBoolean("compounding_enabled", true), request.optString("optimization_stage", "broad"), request.optBoolean("all_entries_three_tick", false), request.optString("selected_parameters_json", ""), request.optString("execution_model", "signal_close"), request.optString("optimization_speed", "quick"), request.optBoolean("precheck_enabled", true), request.optBoolean("adaptive_regime_enabled", false), request.optDouble("initial_capital", 1000.0), request.optString("database_path", "")).toString();
            }
            JSONObject obj = new JSONObject(response);
            StringBuilder logs = new StringBuilder();
            JSONArray rows = obj.optJSONArray("logs");
            if (rows != null) for (int i = 0; i < rows.length(); i++) logs.append(rows.optString(i)).append('\n');
            if (ownsRequest(requestId)) {
                if (stopRequested || "STOPPING".equals(prefs().getString("backtest_status", ""))) {
                    prefs().edit().putBoolean("backtest_requested", false).putBoolean("backtest_paused", false)
                            .putString("backtest_status", "STOPPED").putString("backtest_error", "").apply();
                    updateNotification("백테스트 중지됨 · 체크포인트 보존");
                } else {
                    prefs().edit().putBoolean("backtest_requested", false).putBoolean("backtest_paused", false)
                            .putString("backtest_status", "COMPLETE").putString("backtest_db", obj.optString("db"))
                            .putString("backtest_result", obj.optString("result")).putString("backtest_log", trimLog(logs.toString()))
                            .putString("backtest_error", "").apply();
                    updateNotification(request.optBoolean("db_only", false) ? "DB 다운로드 완료 · 앱에서 차트를 열 수 있습니다" : "백테스트 완료 · 앱에서 결과 확인");
                }
            }
        } catch (Exception e) {
            if (ownsRequest(requestId)) {
                if (stopRequested || !prefs().getBoolean("backtest_requested", false)) {
                    prefs().edit().putBoolean("backtest_requested", false).putBoolean("backtest_paused", false)
                            .putString("backtest_status", "STOPPED").putString("backtest_error", "").apply();
                    updateNotification("백테스트 중지됨 · 체크포인트 보존");
                } else recordError(e, requestId);
            }
        } finally {
            synchronized (BacktestForegroundService.class) {
                if (requestId.equals(activeRequestId)) {
                    String status = prefs().getString("backtest_status", "");
                    if ("STOPPING".equals(status)) prefs().edit().putString("backtest_status", "STOPPED").putBoolean("backtest_requested", false).apply();
                    working = false;
                    stopRequested = false;
                    activeRequestId = "";
                    prefs().edit().putString("backtest_active_request_id", "").apply();
                }
            }
            if (executor != null) executor.shutdown();
            releaseWakeLock();
            stopForeground(false);
            stopSelfResult(startId);
        }
    }

    private JSONObject requestFromIntent(Intent intent) throws Exception {
        JSONObject r = new JSONObject();
        r.put("symbol", intent.getStringExtra("symbol")); r.put("chart_request_id", intent.getStringExtra("chart_request_id"));
        r.put("timeframe", intent.getStringExtra("timeframe")); r.put("start", intent.getStringExtra("start")); r.put("end", intent.getStringExtra("end"));
        r.put("output_dir", new File(getFilesDir(), "UniversalTradingBotCache").getAbsolutePath());
        r.put("host", intent.getStringExtra("host")); r.put("username", intent.getStringExtra("username")); r.put("remote_dir", intent.getStringExtra("remote_dir")); r.put("key_path", intent.getStringExtra("key_path"));
        r.put("risk_profile", intent.getStringExtra("risk_profile")); r.put("optimization_trials", intent.getIntExtra("optimization_trials", 1000));
        r.put("broad_optimization_trials", intent.getIntExtra("broad_optimization_trials", intent.getIntExtra("optimization_trials", 1000))); r.put("refine_optimization_trials", intent.getIntExtra("refine_optimization_trials", intent.getIntExtra("optimization_trials", 1000)));
        r.put("all_entries_three_tick", intent.getBooleanExtra("all_entries_three_tick", false)); r.put("compounding_enabled", intent.getBooleanExtra("compounding_enabled", true)); r.put("initial_capital", intent.getDoubleExtra("initial_capital", 1000.0));
        r.put("optimization_stage", intent.getStringExtra("optimization_stage")); r.put("selected_parameters_json", intent.getStringExtra("selected_parameters_json")); r.put("execution_model", intent.getStringExtra("execution_model")); r.put("optimization_speed", intent.getStringExtra("optimization_speed"));
        r.put("precheck_enabled", intent.getBooleanExtra("precheck_enabled", true)); r.put("adaptive_regime_enabled", intent.getBooleanExtra("adaptive_regime_enabled", false)); r.put("database_path", intent.getStringExtra("database_path"));
        r.put("priority_live_parity", intent.getBooleanExtra("priority_live_parity", false)); r.put("request_type", intent.getStringExtra("request_type"));
        return r;
    }

    private void setPythonPaused(boolean paused) { try { if (Python.isStarted()) Python.getInstance().getModule("mobile_bridge").callAttr("set_optimization_paused", paused); } catch (Exception ignored) {} }
    private void requestPythonStop() { try { if (Python.isStarted()) Python.getInstance().getModule("mobile_bridge").callAttr("request_optimization_stop"); } catch (Exception ignored) {} }
    private void recordError(Exception e, String requestId) {
        if (!requestId.isEmpty() && !ownsRequest(requestId)) return;
        String message = e.getClass().getSimpleName() + ": " + String.valueOf(e.getMessage());
        if (message.length() > 4000) message = message.substring(0, 4000);
        prefs().edit().putBoolean("backtest_requested", false).putBoolean("backtest_paused", false).putString("backtest_status", "ERROR").putString("backtest_error", message).apply();
        updateNotification("백테스트 오류 · 앱에서 로그 확인");
    }
    private String trimLog(String value) { int limit = 50000; return value.length() <= limit ? value : value.substring(value.length() - limit); }
    private void releaseWakeLock() { if (wakeLock != null && wakeLock.isHeld()) wakeLock.release(); }
    @Override public void onDestroy() { releaseWakeLock(); super.onDestroy(); }
    @Override public IBinder onBind(Intent intent) { return null; }
    private SharedPreferences prefs() { return getSharedPreferences("universal_bot", MODE_PRIVATE); }
    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(CHANNEL_ID, "백그라운드 백테스트", NotificationManager.IMPORTANCE_LOW);
            channel.setDescription("장시간 캐시 생성과 전략 최적화를 백그라운드에서 실행합니다.");
            ((NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE)).createNotificationChannel(channel);
        }
    }
    private PendingIntent action(String action, int requestCode) {
        Intent intent = new Intent(this, BacktestForegroundService.class); intent.setAction(action);
        return PendingIntent.getService(this, requestCode, intent, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }
    private Notification notification(String text) {
        Intent launch = new Intent(this, MainActivity.class);
        PendingIntent open = PendingIntent.getActivity(this, 0, launch, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        Notification.Builder b = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O ? new Notification.Builder(this, CHANNEL_ID) : new Notification.Builder(this);
        boolean paused = prefs().getBoolean("backtest_paused", false);
        b.setContentTitle("Universal Trading Bot · 백테스트").setContentText(text).setSmallIcon(android.R.drawable.stat_notify_sync)
                .setOngoing(prefs().getBoolean("backtest_requested", false)).setContentIntent(open)
                .addAction(0, paused ? "재개" : "일시중지", action(paused ? ACTION_RESUME : ACTION_PAUSE, 1))
                .addAction(0, "중지", action(ACTION_STOP, 2));
        return b.build();
    }
    private void updateNotification(String text) { ((NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE)).notify(NOTIFICATION_ID, notification(text)); }
}
