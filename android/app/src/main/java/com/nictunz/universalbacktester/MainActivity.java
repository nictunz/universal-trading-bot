package com.nictunz.universalbacktester;

import android.app.DatePickerDialog;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;
import android.widget.AutoCompleteTextView;
import android.widget.Button;
import android.widget.EditText;
import android.widget.HorizontalScrollView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.text.SimpleDateFormat;
import java.util.Calendar;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends android.app.Activity {
    private static final int BG = Color.rgb(11, 18, 32);
    private static final int PANEL = Color.rgb(17, 24, 39);
    private static final int CARD = Color.rgb(23, 32, 51);
    private static final int BORDER = Color.rgb(38, 50, 71);
    private static final int TEXT = Color.rgb(248, 250, 252);
    private static final int MUTED = Color.rgb(148, 163, 184);
    private static final int ACCENT = Color.rgb(56, 189, 248);
    private static final int PRIMARY = Color.rgb(2, 132, 199);
    private static final int SUCCESS = Color.rgb(4, 120, 87);

    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final Handler main = new Handler(Looper.getMainLooper());

    private AutoCompleteTextView symbolInput;
    private AutoCompleteTextView timeframeInput;
    private EditText startInput;
    private EditText endInput;
    private EditText hostInput;
    private EditText userInput;
    private EditText remoteInput;
    private Button runButton;
    private Button uploadButton;
    private Button sshTestButton;
    private Button keyButton;
    private TextView statusText;
    private TextView logText;
    private TextView publicKeyText;
    private TextView tradesValue;
    private TextView winRateValue;
    private TextView pfValue;
    private TextView returnValue;
    private TextView mddValue;

    private String lastDbPath = "";
    private String lastResultPath = "";
    private String privateKeyPath = "";
    private boolean lastUploadEligible = false;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        if (!Python.isStarted()) {
            Python.start(new AndroidPlatform(this));
        }
        setContentView(buildUi());
    }

    @Override
    protected void onDestroy() {
        executor.shutdownNow();
        super.onDestroy();
    }

    private View buildUi() {
        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setBackgroundColor(BG);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(16), dp(16), dp(16), dp(28));
        scroll.addView(root, new ScrollView.LayoutParams(ScrollView.LayoutParams.MATCH_PARENT, ScrollView.LayoutParams.WRAP_CONTENT));

        TextView title = text("Universal Trading Backtester", 24, TEXT, true);
        root.addView(title);
        TextView subtitle = text("Android 폰에서 4개 거래소 캐시 생성 · 로컬 백테스트 · 서버 업로드", 13, MUTED, false);
        root.addView(subtitle, marginTop(4));

        LinearLayout backtestCard = panel();
        root.addView(backtestCard, marginTop(16));
        backtestCard.addView(sectionTitle("로컬 캐시 / 백테스트"));

        symbolInput = autocomplete(new String[]{
                "BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "XRP/USDT:USDT",
                "BNB/USDT:USDT", "DOGE/USDT:USDT", "ADA/USDT:USDT", "AVAX/USDT:USDT", "LINK/USDT:USDT"
        }, "ETH/USDT:USDT");
        timeframeInput = autocomplete(new String[]{"1m", "3m", "5m", "15m", "30m", "1h", "4h", "1d"}, "5m");
        backtestCard.addView(labeled("심볼 (선택 또는 직접 입력)", symbolInput));
        backtestCard.addView(labeled("타임프레임 (선택 또는 직접 입력)", timeframeInput), marginTop(10));

        Calendar today = Calendar.getInstance();
        Calendar start = (Calendar) today.clone();
        start.add(Calendar.DAY_OF_YEAR, -364);
        startInput = edit(formatDate(start));
        endInput = edit(formatDate(today));
        backtestCard.addView(dateRow("시작일", startInput));
        backtestCard.addView(dateRow("종료일", endInput), marginTop(8));

        LinearLayout quickRow = new LinearLayout(this);
        quickRow.setOrientation(LinearLayout.HORIZONTAL);
        quickRow.setGravity(Gravity.CENTER_VERTICAL);
        quickRow.addView(text("빠른 기간", 12, MUTED, true));
        quickRow.addView(smallButton("30일", v -> setQuickRange(30)), smallButtonParams());
        quickRow.addView(smallButton("90일", v -> setQuickRange(90)), smallButtonParams());
        quickRow.addView(smallButton("180일", v -> setQuickRange(180)), smallButtonParams());
        quickRow.addView(smallButton("1년", v -> setQuickRange(365)), smallButtonParams());
        backtestCard.addView(quickRow, marginTop(10));

        TextView storageInfo = text("저장 위치: 앱 내부 저장소 / UniversalTradingBotCache", 12, MUTED, false);
        backtestCard.addView(storageInfo, marginTop(10));

        runButton = actionButton("▶ 캐시 생성 + 백테스트", PRIMARY);
        runButton.setOnClickListener(v -> runBacktest());
        backtestCard.addView(runButton, marginTop(12));

        root.addView(buildMetrics(), marginTop(14));

        LinearLayout serverCard = panel();
        root.addView(serverCard, marginTop(14));
        serverCard.addView(sectionTitle("서버 업로드"));
        hostInput = edit("34.132.172.40");
        userInput = edit("kpj3669");
        remoteInput = edit("/home/kpj3669/.cache/universal-trading-bot");
        serverCard.addView(labeled("서버", hostInput));
        serverCard.addView(labeled("사용자", userInput), marginTop(8));
        serverCard.addView(labeled("원격 캐시 폴더", remoteInput), marginTop(8));

        keyButton = actionButton("휴대폰 전용 SSH 키 생성 / 확인", Color.rgb(30, 41, 59));
        keyButton.setOnClickListener(v -> ensurePhoneKey());
        serverCard.addView(keyButton, marginTop(12));

        publicKeyText = text("휴대폰 SSH 키를 생성하면 공개키가 여기에 표시됩니다. 서버 authorized_keys에 한 번만 등록하면 됩니다.", 11, MUTED, false);
        publicKeyText.setTextIsSelectable(true);
        publicKeyText.setPadding(dp(10), dp(10), dp(10), dp(10));
        publicKeyText.setBackground(rounded(Color.rgb(7, 16, 29), 10, BORDER));
        serverCard.addView(publicKeyText, marginTop(8));

        Button copyKeyButton = smallButton("공개키 복사", v -> copyPublicKey());
        serverCard.addView(copyKeyButton, marginTop(8));

        sshTestButton = actionButton("SSH 연결 테스트", Color.rgb(30, 41, 59));
        sshTestButton.setOnClickListener(v -> testSsh());
        serverCard.addView(sshTestButton, marginTop(10));

        uploadButton = actionButton("⬆ 1년 결과 서버 업로드", SUCCESS);
        uploadButton.setEnabled(false);
        uploadButton.setAlpha(0.45f);
        uploadButton.setOnClickListener(v -> uploadLast());
        serverCard.addView(uploadButton, marginTop(8));

        TextView protection = text("안전장치: 360~370일로 완성된 캐시만 서버 업로드가 활성화됩니다.", 11, MUTED, false);
        serverCard.addView(protection, marginTop(8));

        LinearLayout logCard = panel();
        root.addView(logCard, marginTop(14));
        LinearLayout statusRow = new LinearLayout(this);
        statusRow.setOrientation(LinearLayout.HORIZONTAL);
        statusRow.setGravity(Gravity.CENTER_VERTICAL);
        TextView logTitle = sectionTitle("실행 로그");
        statusRow.addView(logTitle, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));
        statusText = text("준비됨", 12, ACCENT, true);
        statusRow.addView(statusText);
        logCard.addView(statusRow);
        logText = text("앱은 로컬에서 실행됩니다. 장시간 백테스트 중에는 앱을 화면에 유지하는 것을 권장합니다.", 11, Color.rgb(219, 234, 254), false);
        logText.setTypeface(Typeface.MONOSPACE);
        logText.setTextIsSelectable(true);
        logText.setPadding(dp(10), dp(10), dp(10), dp(10));
        logText.setBackground(rounded(Color.rgb(7, 16, 29), 10, BORDER));
        logCard.addView(logText, marginTop(8));

        return scroll;
    }

    private View buildMetrics() {
        HorizontalScrollView scroll = new HorizontalScrollView(this);
        scroll.setHorizontalScrollBarEnabled(false);
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        scroll.addView(row);

        tradesValue = metric(row, "거래");
        winRateValue = metric(row, "승률");
        pfValue = metric(row, "Profit Factor");
        returnValue = metric(row, "수익률");
        mddValue = metric(row, "MDD");
        return scroll;
    }

    private TextView metric(LinearLayout row, String title) {
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(dp(14), dp(12), dp(14), dp(12));
        card.setBackground(rounded(CARD, 12, BORDER));
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(dp(132), LinearLayout.LayoutParams.WRAP_CONTENT);
        params.setMargins(0, 0, dp(8), 0);
        row.addView(card, params);
        card.addView(text(title, 11, MUTED, false));
        TextView value = text("—", 20, TEXT, true);
        card.addView(value, marginTop(4));
        return value;
    }

    private LinearLayout dateRow(String label, EditText target) {
        LinearLayout wrap = new LinearLayout(this);
        wrap.setOrientation(LinearLayout.VERTICAL);
        wrap.addView(text(label + " (달력 또는 직접 입력)", 12, TEXT, true));
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.addView(target, new LinearLayout.LayoutParams(0, dp(48), 1f));
        Button calendar = smallButton("달력", v -> openDatePicker(target));
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(dp(78), dp(48));
        p.setMargins(dp(8), 0, 0, 0);
        row.addView(calendar, p);
        wrap.addView(row, marginTop(4));
        return wrap;
    }

    private void openDatePicker(EditText target) {
        Calendar cal = parseDate(target.getText().toString());
        if (cal == null) cal = Calendar.getInstance();
        DatePickerDialog dialog = new DatePickerDialog(
                this,
                (view, year, month, dayOfMonth) -> {
                    Calendar chosen = Calendar.getInstance();
                    chosen.set(year, month, dayOfMonth);
                    target.setText(formatDate(chosen));
                },
                cal.get(Calendar.YEAR),
                cal.get(Calendar.MONTH),
                cal.get(Calendar.DAY_OF_MONTH)
        );
        dialog.show();
    }

    private void setQuickRange(int days) {
        Calendar end = parseDate(endInput.getText().toString());
        if (end == null) end = Calendar.getInstance();
        Calendar start = (Calendar) end.clone();
        start.add(Calendar.DAY_OF_YEAR, -(days - 1));
        startInput.setText(formatDate(start));
    }

    private void runBacktest() {
        String symbol = symbolInput.getText().toString().trim();
        String timeframe = timeframeInput.getText().toString().trim();
        String start = startInput.getText().toString().trim();
        String end = endInput.getText().toString().trim();
        if (symbol.isEmpty() || timeframe.isEmpty() || parseDate(start) == null || parseDate(end) == null) {
            toast("심볼, 타임프레임, 날짜를 확인하세요.");
            return;
        }

        setBusy(true, "백테스트 실행 중...");
        lastDbPath = "";
        lastResultPath = "";
        lastUploadEligible = false;
        enableUpload(false);
        logText.setText("로컬 캐시 생성 및 백테스트 시작...\n");
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);

        File output = new File(getFilesDir(), "UniversalTradingBotCache");
        executor.execute(() -> {
            try {
                Python py = Python.getInstance();
                PyObject bridge = py.getModule("mobile_bridge");
                String jsonText = bridge.callAttr("run_backtest", symbol, timeframe, start, end, output.getAbsolutePath()).toString();
                JSONObject obj = new JSONObject(jsonText);
                JSONObject summary = obj.getJSONObject("summary");
                JSONArray logs = obj.getJSONArray("logs");
                lastDbPath = obj.getString("db");
                lastResultPath = obj.getString("result");
                lastUploadEligible = summary.optBoolean("server_upload_eligible", false);
                StringBuilder sb = new StringBuilder();
                for (int i = 0; i < logs.length(); i++) sb.append(logs.getString(i)).append('\n');

                main.post(() -> {
                    updateMetrics(summary);
                    logText.setText(sb.toString());
                    statusText.setText(lastUploadEligible ? "완료 · 서버 업로드 가능" : "완료 · 로컬 캐시");
                    enableUpload(lastUploadEligible);
                    setBusy(false, statusText.getText().toString());
                    getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
                    toast("백테스트 완료");
                });
            } catch (Exception e) {
                main.post(() -> {
                    logText.append("\nERROR\n" + stackMessage(e));
                    setBusy(false, "오류 발생");
                    getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
                    toast("백테스트 오류 - 로그를 확인하세요.");
                });
            }
        });
    }

    private void ensurePhoneKey() {
        keyButton.setEnabled(false);
        statusText.setText("휴대폰 SSH 키 준비 중...");
        executor.execute(() -> {
            try {
                PyObject bridge = Python.getInstance().getModule("mobile_bridge");
                String text = bridge.callAttr("ensure_ssh_key", getFilesDir().getAbsolutePath()).toString();
                JSONObject obj = new JSONObject(text);
                privateKeyPath = obj.getString("private_key");
                String pub = obj.getString("public_key");
                main.post(() -> {
                    publicKeyText.setText(pub);
                    statusText.setText("휴대폰 SSH 키 준비됨");
                    keyButton.setEnabled(true);
                    toast("공개키를 서버 authorized_keys에 한 번 등록하세요.");
                });
            } catch (Exception e) {
                main.post(() -> {
                    publicKeyText.setText(stackMessage(e));
                    statusText.setText("SSH 키 생성 실패");
                    keyButton.setEnabled(true);
                });
            }
        });
    }

    private void copyPublicKey() {
        String value = publicKeyText.getText().toString();
        if (!value.startsWith("ssh-")) {
            toast("먼저 휴대폰 SSH 키를 생성하세요.");
            return;
        }
        ClipboardManager clipboard = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
        clipboard.setPrimaryClip(ClipData.newPlainText("Universal Backtester public key", value));
        toast("공개키를 복사했습니다.");
    }

    private void testSsh() {
        if (privateKeyPath.isEmpty()) {
            toast("먼저 휴대폰 전용 SSH 키를 생성하고 서버에 공개키를 등록하세요.");
            return;
        }
        sshTestButton.setEnabled(false);
        statusText.setText("SSH 연결 확인 중...");
        executor.execute(() -> {
            try {
                PyObject bridge = Python.getInstance().getModule("mobile_bridge");
                String result = bridge.callAttr("test_ssh", hostInput.getText().toString(), userInput.getText().toString(), privateKeyPath).toString();
                main.post(() -> {
                    statusText.setText("SSH 연결 성공");
                    logText.append("\nSSH TEST: " + result + "\n");
                    sshTestButton.setEnabled(true);
                    toast("SSH 연결 성공");
                });
            } catch (Exception e) {
                main.post(() -> {
                    statusText.setText("SSH 연결 실패");
                    logText.append("\nSSH ERROR\n" + stackMessage(e) + "\n");
                    sshTestButton.setEnabled(true);
                    toast("SSH 연결 실패");
                });
            }
        });
    }

    private void uploadLast() {
        if (!lastUploadEligible || lastDbPath.isEmpty() || lastResultPath.isEmpty()) {
            toast("1년 범위 백테스트를 먼저 완료하세요.");
            return;
        }
        if (privateKeyPath.isEmpty()) {
            toast("휴대폰 SSH 키를 먼저 준비하세요.");
            return;
        }
        enableUpload(false);
        statusText.setText("서버 업로드 중...");
        executor.execute(() -> {
            try {
                PyObject bridge = Python.getInstance().getModule("mobile_bridge");
                String response = bridge.callAttr(
                        "upload_result",
                        lastDbPath,
                        lastResultPath,
                        hostInput.getText().toString(),
                        userInput.getText().toString(),
                        remoteInput.getText().toString(),
                        privateKeyPath
                ).toString();
                JSONObject obj = new JSONObject(response);
                JSONArray logs = obj.getJSONArray("logs");
                StringBuilder sb = new StringBuilder("\n");
                for (int i = 0; i < logs.length(); i++) sb.append(logs.getString(i)).append('\n');
                main.post(() -> {
                    logText.append(sb.toString());
                    statusText.setText("서버 업로드 완료");
                    enableUpload(true);
                    toast("서버 업로드 완료");
                });
            } catch (Exception e) {
                main.post(() -> {
                    logText.append("\nUPLOAD ERROR\n" + stackMessage(e) + "\n");
                    statusText.setText("업로드 실패");
                    enableUpload(true);
                    toast("업로드 실패 - 로그를 확인하세요.");
                });
            }
        });
    }

    private void updateMetrics(JSONObject summary) {
        tradesValue.setText(String.valueOf(summary.optInt("trades", 0)));
        winRateValue.setText(formatMetric(summary, "win_rate", "%"));
        pfValue.setText(formatMetric(summary, "profit_factor", ""));
        returnValue.setText(formatMetric(summary, "return_percent", "%"));
        mddValue.setText(formatMetric(summary, "max_drawdown_percent", "%"));
    }

    private String formatMetric(JSONObject obj, String key, String suffix) {
        if (obj.isNull(key)) return "—";
        double value = obj.optDouble(key, Double.NaN);
        if (Double.isNaN(value) || Double.isInfinite(value)) return "—";
        return String.format(Locale.US, "%.2f%s", value, suffix);
    }

    private void setBusy(boolean busy, String status) {
        runButton.setEnabled(!busy);
        runButton.setAlpha(busy ? 0.45f : 1f);
        statusText.setText(status);
    }

    private void enableUpload(boolean enabled) {
        uploadButton.setEnabled(enabled);
        uploadButton.setAlpha(enabled ? 1f : 0.45f);
    }

    private LinearLayout panel() {
        LinearLayout panel = new LinearLayout(this);
        panel.setOrientation(LinearLayout.VERTICAL);
        panel.setPadding(dp(14), dp(14), dp(14), dp(14));
        panel.setBackground(rounded(PANEL, 14, BORDER));
        return panel;
    }

    private LinearLayout labeled(String label, View field) {
        LinearLayout wrap = new LinearLayout(this);
        wrap.setOrientation(LinearLayout.VERTICAL);
        wrap.addView(text(label, 12, TEXT, true));
        wrap.addView(field, new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(48)));
        return wrap;
    }

    private AutoCompleteTextView autocomplete(String[] values, String initial) {
        AutoCompleteTextView input = new AutoCompleteTextView(this);
        android.widget.ArrayAdapter<String> adapter = new android.widget.ArrayAdapter<>(this, android.R.layout.simple_dropdown_item_1line, values);
        input.setAdapter(adapter);
        input.setThreshold(0);
        input.setText(initial);
        input.setTextColor(TEXT);
        input.setHintTextColor(MUTED);
        input.setSingleLine(true);
        input.setTextSize(15);
        input.setPadding(dp(12), 0, dp(12), 0);
        input.setBackground(rounded(Color.rgb(15, 23, 42), 10, BORDER));
        input.setOnClickListener(v -> input.showDropDown());
        input.setOnFocusChangeListener((v, hasFocus) -> { if (hasFocus) input.showDropDown(); });
        return input;
    }

    private EditText edit(String initial) {
        EditText input = new EditText(this);
        input.setText(initial);
        input.setTextColor(TEXT);
        input.setHintTextColor(MUTED);
        input.setSingleLine(true);
        input.setTextSize(14);
        input.setPadding(dp(12), 0, dp(12), 0);
        input.setBackground(rounded(Color.rgb(15, 23, 42), 10, BORDER));
        return input;
    }

    private Button actionButton(String label, int color) {
        Button button = new Button(this);
        button.setText(label);
        button.setTextColor(Color.WHITE);
        button.setTextSize(14);
        button.setAllCaps(false);
        button.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        button.setBackground(rounded(color, 10, color));
        button.setMinHeight(dp(50));
        return button;
    }

    private Button smallButton(String label, View.OnClickListener listener) {
        Button button = new Button(this);
        button.setText(label);
        button.setTextColor(TEXT);
        button.setTextSize(12);
        button.setAllCaps(false);
        button.setBackground(rounded(Color.rgb(30, 41, 59), 10, BORDER));
        button.setOnClickListener(listener);
        return button;
    }

    private LinearLayout.LayoutParams smallButtonParams() {
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(0, dp(42), 1f);
        p.setMargins(dp(5), 0, 0, 0);
        return p;
    }

    private TextView sectionTitle(String value) {
        TextView v = text(value, 16, TEXT, true);
        v.setPadding(0, 0, 0, dp(10));
        return v;
    }

    private TextView text(String value, int sp, int color, boolean bold) {
        TextView t = new TextView(this);
        t.setText(value);
        t.setTextColor(color);
        t.setTextSize(sp);
        if (bold) t.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        return t;
    }

    private GradientDrawable rounded(int fill, int radiusDp, int stroke) {
        GradientDrawable d = new GradientDrawable();
        d.setColor(fill);
        d.setCornerRadius(dp(radiusDp));
        d.setStroke(dp(1), stroke);
        return d;
    }

    private LinearLayout.LayoutParams marginTop(int dp) {
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        p.setMargins(0, this.dp(dp), 0, 0);
        return p;
    }

    private String formatDate(Calendar cal) {
        return new SimpleDateFormat("yyyy-MM-dd", Locale.US).format(cal.getTime());
    }

    private Calendar parseDate(String value) {
        try {
            SimpleDateFormat f = new SimpleDateFormat("yyyy-MM-dd", Locale.US);
            f.setLenient(false);
            Calendar cal = Calendar.getInstance();
            cal.setTime(f.parse(value));
            return cal;
        } catch (Exception e) {
            return null;
        }
    }

    private String stackMessage(Exception e) {
        String message = e.getMessage();
        if (message == null || message.isEmpty()) message = e.toString();
        return message;
    }

    private void toast(String message) {
        Toast.makeText(this, message, Toast.LENGTH_LONG).show();
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
