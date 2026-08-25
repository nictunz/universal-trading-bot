package com.nictunz.universalbacktester;

import android.Manifest;
import android.app.AlertDialog;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.net.Uri;
import android.provider.Settings;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONObject;

import java.io.File;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class LauncherActivity extends android.app.Activity {
    private static final int BG = Color.rgb(11, 18, 32);
    private static final int PANEL = Color.rgb(17, 24, 39);
    private static final int BORDER = Color.rgb(38, 50, 71);
    private static final int TEXT = Color.rgb(248, 250, 252);
    private static final int MUTED = Color.rgb(148, 163, 184);
    private static final int PRIMARY = Color.rgb(2, 132, 199);
    private static final int SUCCESS = Color.rgb(4, 120, 87);
    private static final int WARNING = Color.rgb(180, 83, 9);

    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final Handler main = new Handler(Looper.getMainLooper());

    private EditText hostInput;
    private EditText userInput;
    private EditText remoteInput;
    private TextView relayStatus;
    private TextView keyStatus;
    private TextView publicKeyText;
    private TextView updateStatus;
    private Button startRelayButton;
    private Button oneShotButton;
    private Button updateButton;
    private AppUpdateManager.UpdateInfo pendingUpdate;

    private final Runnable statusPoller = new Runnable() {
        @Override
        public void run() {
            refreshRelayStatus();
            main.postDelayed(this, 2000);
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(buildUi());
        refreshRelayStatus();
        resumeRequestedRelay();
    }

    @Override
    protected void onResume() {
        super.onResume();
        main.removeCallbacks(statusPoller);
        main.post(statusPoller);
    }

    @Override
    protected void onPause() {
        main.removeCallbacks(statusPoller);
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        executor.shutdownNow();
        super.onDestroy();
    }

    private View buildUi() {
        SharedPreferences p = prefs();
        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setBackgroundColor(BG);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(16), dp(18), dp(16), dp(28));
        scroll.addView(root);

        root.addView(text("Universal Trading Bot", 25, TEXT, true));
        root.addView(text("모바일 백테스트 · Binance/Bybit 선물 데이터 중계 · 안전 업데이트", 13, MUTED, false), mt(5));

        LinearLayout relay = panel();
        root.addView(relay, mt(16));
        relay.addView(section("📡 LIVE 시장데이터 중계"));
        relay.addView(text(
                "휴대폰에서 Binance/Bybit 공개 USDT 선물 5분봉을 읽고 기존 SSH 키로 서버에 전송합니다. Bitget 주문 API 키는 휴대폰에 저장하지 않습니다.",
                12, MUTED, false
        ), mt(6));

        hostInput = edit(p.getString("relay_host", "34.132.172.40"));
        userInput = edit(p.getString("relay_user", "kpj3669"));
        remoteInput = edit(p.getString("relay_remote_dir", "/home/kpj3669/.cache/universal-trading-bot"));
        relay.addView(labeled("서버", hostInput), mt(12));
        relay.addView(labeled("사용자", userInput), mt(8));
        relay.addView(labeled("서버 캐시 폴더", remoteInput), mt(8));

        Button keyButton = actionButton("🔑 휴대폰 SSH 키 준비 / 확인", Color.rgb(30, 41, 59));
        keyButton.setOnClickListener(v -> ensureKeyOnly());
        relay.addView(keyButton, mt(10));

        keyStatus = text("SSH 키 상태 확인 중...", 11, MUTED, false);
        relay.addView(keyStatus, mt(6));

        Button copyKeyButton = actionButton("📋 SSH 공개키 보기 / 복사", Color.rgb(30, 41, 59));
        copyKeyButton.setOnClickListener(v -> showAndCopyPublicKey());
        relay.addView(copyKeyButton, mt(8));

        publicKeyText = text("", 10, MUTED, false);
        publicKeyText.setTextIsSelectable(true);
        publicKeyText.setPadding(dp(10), dp(10), dp(10), dp(10));
        publicKeyText.setBackground(rounded(Color.rgb(7, 16, 29), 10, BORDER));
        publicKeyText.setVisibility(View.GONE);
        relay.addView(publicKeyText, mt(8));

        oneShotButton = actionButton("🧪 Binance/Bybit + 서버 1회 중계 테스트", WARNING);
        oneShotButton.setOnClickListener(v -> prepareRelay(MobileMarketRelayService.ACTION_ONCE));
        relay.addView(oneShotButton, mt(10));

        startRelayButton = actionButton("▶ 30초 실시간 중계 시작", SUCCESS);
        startRelayButton.setOnClickListener(v -> {
            requestNotificationPermissionIfNeeded();
            prepareRelay(MobileMarketRelayService.ACTION_START);
        });
        relay.addView(startRelayButton, mt(8));

        Button battery = actionButton("🔋 배터리 제한 해제 / 상태 확인", Color.rgb(30, 41, 59));
        battery.setOnClickListener(v -> requestUnlimitedBattery());
        relay.addView(battery, mt(8));

        Button stop = actionButton("■ 중계 중지", Color.rgb(71, 85, 105));
        stop.setOnClickListener(v -> stopRelay());
        relay.addView(stop, mt(8));

        relayStatus = text("중계 상태 확인 중...", 12, TEXT, true);
        relayStatus.setPadding(dp(10), dp(10), dp(10), dp(10));
        relayStatus.setBackground(rounded(Color.rgb(7, 16, 29), 10, BORDER));
        relayStatus.setClickable(true);
        relayStatus.setOnClickListener(v -> showRelayLogDialog());
        relay.addView(relayStatus, mt(10));

        relay.addView(text(
                "LIVE 사용 시 휴대폰 배터리를 '제한 없음'으로 설정하고 인터넷 연결을 유지하세요. 중계가 90초 이상 오래되면 서버는 해당 데이터로 신규 진입하지 않도록 설계됩니다.",
                11, MUTED, false
        ), mt(8));

        LinearLayout update = panel();
        root.addView(update, mt(14));
        update.addView(section("⬆ 앱 업데이트"));
        String current = AppUpdateManager.currentVersionName(this);
        updateStatus = text("현재 버전: " + (current.isEmpty() ? "확인 불가" : current), 12, MUTED, false);
        update.addView(updateStatus, mt(5));
        update.addView(text(
                "GitHub 테스트와 Android 빌드가 모두 성공한 안정 서명 APK만 서버 업데이트 채널에 게시됩니다. 휴대폰에는 GitHub 토큰을 저장하지 않고 기존 SSH 키로 APK를 받아 SHA-256과 Android 서명을 확인합니다.",
                11, MUTED, false
        ), mt(7));
        updateButton = actionButton("업데이트 확인", PRIMARY);
        updateButton.setOnClickListener(v -> checkUpdate());
        update.addView(updateButton, mt(10));

        LinearLayout dashboard = panel();
        root.addView(dashboard, mt(14));
        dashboard.addView(section("🖥 서버 관리 대시보드"));
        dashboard.addView(text(
                "SSH 암호화 터널로 서버의 실제 전략 설정·거래 기록·차트·캐시·LIVE 설정을 앱 안에서 직접 관리합니다.",
                12,
                MUTED,
                false
        ), mt(5));
        Button openDashboard = actionButton("서버 대시보드 열기", SUCCESS);
        openDashboard.setOnClickListener(v ->
                startActivity(new Intent(this, ServerDashboardActivity.class))
        );
        dashboard.addView(openDashboard, mt(10));

        LinearLayout backtest = panel();
        root.addView(backtest, mt(14));
        backtest.addView(section("🧪 로컬 백테스터"));
        backtest.addView(text("기존 캐시 생성 · 1년 백테스트 · 서버 업로드 화면은 그대로 유지됩니다.", 12, MUTED, false), mt(5));
        Button openBacktester = actionButton("Universal Backtester 열기", Color.rgb(30, 41, 59));
        openBacktester.setOnClickListener(v -> startActivity(new Intent(this, MainActivity.class)));
        backtest.addView(openBacktester, mt(10));

        return scroll;
    }

    private void showRelayLogDialog() {
        String history = prefs().getString("relay_log_history", "");
        TextView logView = text(
                history.isEmpty() ? "아직 저장된 중계 로그가 없습니다." : history,
                12,
                TEXT,
                false
        );
        logView.setTextIsSelectable(true);
        logView.setPadding(dp(16), dp(14), dp(16), dp(14));

        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setMinimumHeight(dp(420));
        scroll.addView(logView);

        AlertDialog dialog = new AlertDialog.Builder(this)
                .setTitle("실시간 중계 이전 로그")
                .setMessage("최근 300개 기록 · 성공/오류/시작/중지")
                .setView(scroll)
                .setNegativeButton("닫기", null)
                .create();
        dialog.setOnShowListener(ignored -> scroll.post(() -> scroll.fullScroll(View.FOCUS_DOWN)));
        dialog.show();
    }

    private void ensureKeyOnly() {
        keyStatus.setText("SSH 키 준비 중...");
        executor.execute(() -> {
            try {
                JSONObject obj = new JSONObject(SshBridge.ensureKey(getFilesDir().getAbsolutePath()));
                String keyPath = obj.getString("private_key");
                prefs().edit().putString("relay_key_path", keyPath).apply();
                main.post(() -> {
                    keyStatus.setText("휴대폰 SSH 키 생성됨 · 서버 등록 전이면 아래에서 공개키를 복사하세요");
                    toast("SSH 키 준비 완료");
                });
            } catch (Exception e) {
                main.post(() -> keyStatus.setText("SSH 키 오류: " + shortError(e)));
            }
        });
    }

    private void showAndCopyPublicKey() {
        keyStatus.setText("SSH 공개키 확인 중...");
        executor.execute(() -> {
            try {
                JSONObject obj = new JSONObject(SshBridge.ensureKey(getFilesDir().getAbsolutePath()));
                String keyPath = obj.getString("private_key");
                String publicKey = obj.getString("public_key");
                prefs().edit().putString("relay_key_path", keyPath).apply();
                main.post(() -> {
                    ClipboardManager clipboard =
                            (ClipboardManager) getSystemService(CLIPBOARD_SERVICE);
                    clipboard.setPrimaryClip(
                            ClipData.newPlainText("Universal Backtester SSH public key", publicKey)
                    );
                    publicKeyText.setText(publicKey);
                    publicKeyText.setVisibility(View.VISIBLE);
                    keyStatus.setText("SSH 공개키가 표시되고 클립보드에 복사됐습니다");
                    toast("SSH 공개키 복사 완료");
                });
            } catch (Exception e) {
                main.post(() -> keyStatus.setText("SSH 공개키 오류: " + shortError(e)));
            }
        });
    }

    private void prepareRelay(String action) {
        saveRelayInputs();
        setRelayButtons(false);
        relayStatus.setText("중계 준비 중...");
        executor.execute(() -> {
            try {
                JSONObject key = new JSONObject(SshBridge.ensureKey(getFilesDir().getAbsolutePath()));
                String keyPath = key.getString("private_key");
                prefs().edit().putString("relay_key_path", keyPath).apply();
                main.post(() -> {
                    Intent intent = new Intent(this, MobileMarketRelayService.class);
                    intent.setAction(action);
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) startForegroundService(intent);
                    else startService(intent);
                    if (MobileMarketRelayService.ACTION_START.equals(action)) {
                        toast("실시간 중계를 시작했습니다.");
                    } else {
                        toast("1회 중계 테스트를 시작했습니다.");
                    }
                    setRelayButtons(true);
                });
            } catch (Exception e) {
                main.post(() -> {
                    relayStatus.setText("준비 실패: " + shortError(e));
                    setRelayButtons(true);
                });
            }
        });
    }

    private void stopRelay() {
        Intent intent = new Intent(this, MobileMarketRelayService.class);
        intent.setAction(MobileMarketRelayService.ACTION_STOP);
        startService(intent);
        prefs().edit().putBoolean("relay_requested", false).putBoolean("relay_running", false).apply();
        refreshRelayStatus();
        toast("중계를 중지했습니다.");
    }

    private void saveRelayInputs() {
        prefs().edit()
                .putString("relay_host", hostInput.getText().toString().trim())
                .putString("relay_user", userInput.getText().toString().trim())
                .putString("relay_remote_dir", remoteInput.getText().toString().trim())
                .apply();
    }

    private void refreshRelayStatus() {
        SharedPreferences p = prefs();
        String key = p.getString("relay_key_path", "");
        keyStatus.setText(key.isEmpty() ? "SSH 키 미준비" : "SSH 키 준비됨");
        boolean running = p.getBoolean("relay_running", false);
        boolean requested = p.getBoolean("relay_requested", false);
        long lastOk = p.getLong("relay_last_ok_ms", 0L);
        String detail = p.getString("relay_status", "아직 중계 기록 없음");
        StringBuilder sb = new StringBuilder();
        sb.append(running || requested ? "● 중계 ON" : "○ 중계 OFF");
        if (lastOk > 0) sb.append("\n마지막 성공: ").append(formatTime(lastOk));
        sb.append("\n").append(detail);
        sb.append("\n\n🔎 눌러서 이전 로그 보기");
        relayStatus.setText(sb.toString());
        startRelayButton.setAlpha(running || requested ? 0.55f : 1f);
    }

    private void checkUpdate() {
        if (pendingUpdate != null && pendingUpdate.updateAvailable()) {
            confirmDownload(pendingUpdate);
            return;
        }
        saveRelayInputs();
        updateButton.setEnabled(false);
        updateStatus.setText("서버의 최신 검증 빌드 확인 중...");
        executor.execute(() -> {
            try {
                JSONObject key = new JSONObject(SshBridge.ensureKey(getFilesDir().getAbsolutePath()));
                String keyPath = key.getString("private_key");
                prefs().edit().putString("relay_key_path", keyPath).apply();
                String manifest = ServerUpdateBridge.readManifest(
                        hostInput.getText().toString(),
                        userInput.getText().toString(),
                        remoteInput.getText().toString(),
                        keyPath
                );
                AppUpdateManager.UpdateInfo info = AppUpdateManager.fromManifest(this, manifest);
                main.post(() -> {
                    updateButton.setEnabled(true);
                    if (!info.updateAvailable()) {
                        pendingUpdate = null;
                        updateButton.setText("업데이트 확인");
                        updateStatus.setText("최신 버전입니다 · " + info.versionName);
                    } else {
                        pendingUpdate = info;
                        updateButton.setText("⬇ " + info.versionName + " 다운로드 / 설치");
                        updateStatus.setText(
                                "업데이트 가능: " + info.versionName
                                        + (info.commit.isEmpty() ? "" : " · " + info.commit.substring(0, Math.min(7, info.commit.length())))
                        );
                    }
                });
            } catch (Exception e) {
                main.post(() -> {
                    updateButton.setEnabled(true);
                    updateStatus.setText("업데이트 확인 실패: " + shortError(e));
                });
            }
        });
    }

    private void confirmDownload(AppUpdateManager.UpdateInfo info) {
        new AlertDialog.Builder(this)
                .setTitle("앱 업데이트")
                .setMessage(info.versionName + " 버전을 서버에서 받아 설치할까요?\n\nGitHub 테스트와 Android 빌드가 성공한 안정 서명 APK만 게시됩니다.")
                .setNegativeButton("취소", null)
                .setPositiveButton("업데이트", (d, which) -> downloadUpdate(info))
                .show();
    }

    private void downloadUpdate(AppUpdateManager.UpdateInfo info) {
        saveRelayInputs();
        updateButton.setEnabled(false);
        updateStatus.setText("APK SFTP 다운로드 및 SHA-256 검증 중...");
        executor.execute(() -> {
            try {
                String keyPath = prefs().getString("relay_key_path", "");
                if (keyPath.isEmpty()) {
                    JSONObject key = new JSONObject(SshBridge.ensureKey(getFilesDir().getAbsolutePath()));
                    keyPath = key.getString("private_key");
                    prefs().edit().putString("relay_key_path", keyPath).apply();
                }
                String localPath = ServerUpdateBridge.downloadApk(
                        hostInput.getText().toString(),
                        userInput.getText().toString(),
                        remoteInput.getText().toString(),
                        info.apkName,
                        getCacheDir().getAbsolutePath(),
                        keyPath
                );
                File apk = new File(localPath);
                AppUpdateManager.verifyDownloaded(info, apk);
                main.post(() -> {
                    updateButton.setEnabled(true);
                    updateStatus.setText("APK 검증 완료 · Android 설치 확인을 진행하세요.");
                    boolean launched = AppUpdateManager.requestInstall(this, apk);
                    if (!launched) toast("'이 출처 허용'을 켠 뒤 업데이트 버튼을 다시 누르세요.");
                });
            } catch (Exception e) {
                main.post(() -> {
                    updateButton.setEnabled(true);
                    updateStatus.setText("업데이트 실패: " + shortError(e));
                });
            }
        });
    }

    private void resumeRequestedRelay() {
        SharedPreferences p = prefs();
        if (!p.getBoolean("relay_requested", false)) return;
        Intent intent = new Intent(this, MobileMarketRelayService.class);
        intent.setAction(MobileMarketRelayService.ACTION_START);
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) startForegroundService(intent);
            else startService(intent);
        } catch (Exception e) {
            p.edit()
                    .putBoolean("relay_running", false)
                    .putString("relay_status", "자동 복구 대기 · " + shortError(e))
                    .apply();
        }
    }

    private void requestUnlimitedBattery() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) {
            toast("이 Android 버전은 별도 배터리 제한 해제가 필요하지 않습니다.");
            return;
        }
        PowerManager pm = (PowerManager) getSystemService(POWER_SERVICE);
        String packageName = getPackageName();
        if (pm.isIgnoringBatteryOptimizations(packageName)) {
            toast("배터리 사용량이 이미 제한 없음 상태입니다.");
            return;
        }
        try {
            Intent intent = new Intent(
                    Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                    Uri.parse("package:" + packageName)
            );
            startActivity(intent);
        } catch (Exception e) {
            startActivity(new Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS));
        }
    }

    private void requestNotificationPermissionIfNeeded() {
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 3101);
        }
    }

    private void setRelayButtons(boolean enabled) {
        startRelayButton.setEnabled(enabled);
        oneShotButton.setEnabled(enabled);
    }

    private SharedPreferences prefs() {
        return getSharedPreferences("universal_bot", MODE_PRIVATE);
    }

    private String formatTime(long millis) {
        SimpleDateFormat f = new SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.KOREA);
        f.setTimeZone(TimeZone.getDefault());
        return f.format(new Date(millis));
    }

    private String shortError(Exception e) {
        String text = e.getClass().getSimpleName() + ": " + String.valueOf(e.getMessage());
        return text.length() > 220 ? text.substring(0, 220) : text;
    }

    private void toast(String text) {
        Toast.makeText(this, text, Toast.LENGTH_SHORT).show();
    }

    private LinearLayout panel() {
        LinearLayout p = new LinearLayout(this);
        p.setOrientation(LinearLayout.VERTICAL);
        p.setPadding(dp(14), dp(14), dp(14), dp(14));
        p.setBackground(rounded(PANEL, 14, BORDER));
        return p;
    }

    private View labeled(String label, EditText field) {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.addView(text(label, 12, TEXT, true));
        box.addView(field, new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(48)));
        return box;
    }

    private TextView section(String text) {
        return text(text, 16, TEXT, true);
    }

    private TextView text(String value, int sp, int color, boolean bold) {
        TextView t = new TextView(this);
        t.setText(value);
        t.setTextColor(color);
        t.setTextSize(sp);
        if (bold) t.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        t.setLineSpacing(0f, 1.15f);
        return t;
    }

    private EditText edit(String initial) {
        EditText e = new EditText(this);
        e.setText(initial);
        e.setSingleLine(true);
        e.setTextColor(TEXT);
        e.setTextSize(14);
        e.setPadding(dp(12), 0, dp(12), 0);
        e.setBackground(rounded(Color.rgb(15, 23, 42), 10, BORDER));
        return e;
    }

    private Button actionButton(String label, int color) {
        Button b = new Button(this);
        b.setText(label);
        b.setAllCaps(false);
        b.setTextColor(Color.WHITE);
        b.setTextSize(14);
        b.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        b.setGravity(Gravity.CENTER);
        b.setBackground(rounded(color, 10, color));
        b.setMinHeight(dp(50));
        return b;
    }

    private GradientDrawable rounded(int color, int radiusDp, int stroke) {
        GradientDrawable d = new GradientDrawable();
        d.setColor(color);
        d.setCornerRadius(dp(radiusDp));
        d.setStroke(dp(1), stroke);
        return d;
    }

    private LinearLayout.LayoutParams mt(int topDp) {
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
        );
        p.topMargin = dp(topDp);
        return p;
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
