package com.nictunz.universalbacktester;

import android.app.AlertDialog;
import android.app.DatePickerDialog;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.Editable;
import android.text.InputType;
import android.text.TextWatcher;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;
import android.widget.AutoCompleteTextView;
import android.widget.Button;
import android.widget.EditText;
import android.widget.HorizontalScrollView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Switch;
import android.widget.TableLayout;
import android.widget.TableRow;
import android.widget.TextView;
import android.widget.Toast;

import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.Calendar;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends android.app.Activity {
    private static final String ENGINE_SCHEMA = "universal-vector-event-v5";
    private static final int REQUEST_OPEN_JSON = 4107;
    private static final int MAX_IMPORTED_JSON_CHARS = 8 * 1024 * 1024;
    private static final int BG = Color.rgb(11, 18, 32);
    private static final int PANEL = Color.rgb(17, 24, 39);
    private static final int CARD = Color.rgb(23, 32, 51);
    private static final int BORDER = Color.rgb(38, 50, 71);
    private static final int TEXT = Color.rgb(248, 250, 252);
    private static final int MUTED = Color.rgb(148, 163, 184);
    private static final int ACCENT = Color.rgb(56, 189, 248);
    private static final int PRIMARY = Color.rgb(2, 132, 199);
    private static final int SUCCESS = Color.rgb(4, 120, 87);

    // type, label, JSON key, minimum, maximum, fallback. entry_multiplier is
    // intentionally not a second input: it is always derived from order % so
    // the two equivalent sizing values cannot silently disagree.
    private static final String[][] STRATEGY_EDITOR_FIELDS = {
            {"section", "① 진입 방향·규모", "", "", "", ""},
            {"bool", "LONG 허용", "allow_long", "", "", "true"},
            {"bool", "SHORT 허용", "allow_short", "", "", "true"},
            {"int", "첫 진입 확인 연속봉 (1~10)", "first_entry_consecutive_candles", "1", "10", "1"},
            {"bool", "추가 진입에도 연속봉 조건 적용", "apply_consecutive_candles_to_all_entries", "", "", "false"},
            {"decimal", "1회 진입 비중 % (500=자산 5배)", "order_percent_of_equity", "1", "2500", "100"},
            {"int", "최대 진입 횟수 (1~5)", "max_pyramiding", "1", "5", "1"},

            {"section", "② 거래량·기본 변동성", "", "", "", ""},
            {"int", "거래량 SMA 기간", "volume_lookback", "2", "2000", "70"},
            {"decimal", "거래량 폭등 배수", "volume_break_multiplier", "0.1", "100", "8"},
            {"decimal", "1봉 변동 최소 %", "min_one_bar_vol", "0", "100", "0.1"},
            {"decimal", "1봉 변동 최대 %", "max_one_bar_vol", "0", "100", "1"},
            {"int", "TP·SL 변동성 기준 봉", "volatility_bars", "2", "10000", "288"},

            {"section", "③ 익절·손절", "", "", "", ""},
            {"decimal", "TP 변동성 배수", "tp_vol_multiplier", "0.01", "100", "0.4"},
            {"decimal", "SL 변동성 배수", "sl_vol_multiplier", "0.01", "100", "0.8"},
            {"decimal", "TP 최소 %", "min_tp_percent", "0.01", "100", "0.2"},
            {"decimal", "TP 최대 %", "max_tp_percent", "0.01", "100", "2"},
            {"decimal", "SL 최소 %", "min_sl_percent", "0.01", "100", "0.3"},
            {"decimal", "SL 최대 %", "max_sl_percent", "0.01", "100", "2"},

            {"section", "④ N봉 급변동 차단", "", "", "", ""},
            {"bool", "N봉 급변동 차단 사용", "use_nbar_volatility_block", "", "", "true"},
            {"int", "N봉 기준 봉 수", "nbar_volatility_bars", "2", "10000", "200"},
            {"decimal", "N봉 최대 변동 %", "max_nbar_volatility", "0.01", "100", "5"},

            {"section", "⑤ RSI", "", "", "", ""},
            {"bool", "RSI 필터 사용", "use_rsi_filter", "", "", "true"},
            {"int", "RSI 기간", "rsi_length", "2", "100", "8"},
            {"decimal", "RSI 과매도 최소", "rsi_oversold_min", "0", "100", "10"},
            {"decimal", "RSI 과매도 최대", "rsi_oversold_max", "0", "100", "25"},
            {"decimal", "RSI 과매수 최소", "rsi_overbought_min", "0", "100", "75"},
            {"decimal", "RSI 과매수 최대", "rsi_overbought_max", "0", "100", "90"},

            {"section", "⑥ ADX·재진입", "", "", "", ""},
            {"bool", "ADX 필터 사용", "use_adx_filter", "", "", "false"},
            {"int", "ADX 기간", "adx_length", "2", "100", "14"},
            {"decimal", "ADX 최소", "adx_min", "0", "100", "20"},
            {"decimal", "ADX 최대", "adx_max", "0", "100", "100"},
            {"int", "쿨다운 봉", "cooldown_bars", "0", "10000", "6"},
            {"int", "재진입 대기 봉", "reentry_bars", "0", "10000", "6"},

            {"section", "⑦ 시간·시장 국면", "", "", "", ""},
            {"bool", "주말 진입 차단", "block_weekend", "", "", "false"},
            {"text", "제외 시간 UTC (예: 00,13,23 · 없으면 비움)", "excluded_hours", "", "", ""},
            {"bool", "시장 국면 자동 전환", "adaptive_regime_enabled", "", "", "false"},
            {"int", "시장 국면 판단 봉", "regime_lookback_bars", "2", "10000", "288"},
            {"decimal", "추세 판정 변동 %", "regime_trend_threshold_percent", "0", "100", "2"},
            {"decimal", "고변동성 판정 %", "regime_high_volatility_percent", "0", "100", "0.8"},
            {"decimal", "고변동성 진입 축소 배수", "regime_high_volatility_risk_multiplier", "0", "1", "0.5"},

            {"section", "⑧ 백테스트 계산", "", "", "", ""},
            {"decimal", "초기자산 USDT", "initial_capital", "10", "1000000000", "1000"},
            {"bool", "복리 계산", "backtest_compounding_enabled", "", "", "true"},
            {"choice", "체결 모델", "backtest_execution_model", "", "", "next_open"},
            {"decimal", "수수료 편도 %", "backtest_fee_percent", "0", "5", "0.02"},
            {"decimal", "슬리피지 편도 %", "backtest_slippage_percent", "0", "5", "0.01"},
            {"int", "레버리지", "leverage", "1", "125", "50"},
            {"decimal", "최대 총노출 배수", "backtest_max_total_multiplier", "1", "100", "15"},
            {"decimal", "유지증거금 %", "backtest_maintenance_margin_percent", "0", "100", "0.5"},
            {"decimal", "교차청산 안전버퍼 %", "backtest_cross_liquidation_buffer_percent", "0", "100", "25"},
    };

    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final Handler main = new Handler(Looper.getMainLooper());

    private AutoCompleteTextView symbolInput;
    private AutoCompleteTextView timeframeInput;
    private AutoCompleteTextView riskProfileInput;
    private AutoCompleteTextView sizingModeInput;
    private AutoCompleteTextView executionModelInput;
    private AutoCompleteTextView optimizationStageInput;
    private AutoCompleteTextView optimizationSpeedInput;
    private AutoCompleteTextView precheckInput;
    private AutoCompleteTextView adaptiveRegimeInput;
    private AutoCompleteTextView broadTrialCountInput;
    private AutoCompleteTextView refineTrialCountInput;
    private AutoCompleteTextView threeTickModeInput;
    private EditText startInput;
    private EditText endInput;
    private EditText initialCapitalInput;
    private EditText hostInput;
    private EditText userInput;
    private EditText remoteInput;
    private Button runButton;
    private Button uploadButton;
    private Button sshTestButton;
    private Button keyButton;
    private Button pauseBacktestButton;
    private Button resumeBacktestButton;
    private Button stopBacktestButton;
    private TextView statusText;
    private TextView logText;
    private TextView publicKeyText;
    private TextView tradesValue;
    private TextView qualityValue;
    private TextView winRateValue;
    private TextView pfValue;
    private TextView returnValue;
    private TextView mddValue;
    private Button resultSummaryButton;
    private Button tradeHistoryButton;
    private Button chartButton;
    private Button deepBacktestButton;
    private JSONObject lastSummary;
    private JSONObject selectedStrategyParameters;
    private JSONObject selectedStrategyRow;
    private TextView selectedStrategyText;
    private TextView pinnedResultText;
    private EditText pendingJsonInput;

    private String lastDbPath = "";
    private String selectedDbPath = "";
    private String lastResultPath = "";
    private String privateKeyPath = "";
    private boolean lastUploadEligible = false;
    private boolean workloadConfirmed = false;
    private String appliedServiceResultPath = "";
    private String latestFullLog = "";

    private final Runnable backtestStatusPoller = new Runnable() {
        @Override
        public void run() {
            refreshBackgroundBacktestStatus();
            main.postDelayed(this, 1500);
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        if (!Python.isStarted()) {
            Python.start(new AndroidPlatform(this));
        }
        setContentView(buildUi());
        selectedDbPath = getSharedPreferences("universal_bot", MODE_PRIVATE)
                .getString("selected_db_path", "");
        if (!new File(selectedDbPath).isFile()) selectedDbPath = "";
        else restoreSelectedDatabaseSettings(new File(selectedDbPath));
        restorePinnedSelections();
        loadPhoneKey();
        loadSavedResults(true);
    }

    @Override
    protected void onResume() {
        super.onResume();
        main.removeCallbacks(backtestStatusPoller);
        main.post(backtestStatusPoller);
    }

    @Override
    protected void onPause() {
        main.removeCallbacks(backtestStatusPoller);
        super.onPause();
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

        TextView title = text("전략 백테스트", 24, TEXT, true);
        root.addView(title);
        TextView subtitle = text("설정과 결과를 나눠 확인하세요. 선택한 전략과 기존 기능은 유지됩니다.", 13, MUTED, false);
        root.addView(subtitle, marginTop(4));
        Button engineStatusButton = actionButton(
                "⚡ Universal Vector Engine 5 · 상태 확인",
                SUCCESS
        );
        engineStatusButton.setOnClickListener(v -> showEngineStatus());
        root.addView(engineStatusButton, marginTop(10));
        TextView engineHint = text("동일 데이터·전체 설정·엔진 코드가 모두 같을 때만 TOP10 체크포인트를 재사용합니다.", 11, MUTED, false);
        root.addView(engineHint, marginTop(5));

        LinearLayout backtestCard = panel();
        root.addView(backtestCard, marginTop(16));
        backtestCard.addView(sectionTitle("로컬 캐시 / 백테스트"));

        symbolInput = autocomplete(new String[]{
                "BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "XRP/USDT:USDT",
                "BNB/USDT:USDT", "DOGE/USDT:USDT", "ADA/USDT:USDT", "AVAX/USDT:USDT",
                "LINK/USDT:USDT", "DOT/USDT:USDT", "LTC/USDT:USDT", "BCH/USDT:USDT",
                "TRX/USDT:USDT", "TON/USDT:USDT", "SUI/USDT:USDT", "APT/USDT:USDT",
                "NEAR/USDT:USDT", "UNI/USDT:USDT", "FIL/USDT:USDT", "ATOM/USDT:USDT",
                "ETC/USDT:USDT", "AAVE/USDT:USDT", "ARB/USDT:USDT", "OP/USDT:USDT"
        }, "ETH/USDT:USDT");
        timeframeInput = autocomplete(new String[]{"1m", "3m", "5m", "15m", "30m", "1h", "4h", "1d"}, "5m");
        backtestCard.addView(labeled("심볼 (목록 선택 또는 직접 입력)", symbolInput));
        backtestCard.addView(quickChoiceRow(
                "자주 쓰는 코인",
                symbolInput,
                new String[]{"BTC", "ETH", "SOL", "XRP", "BNB", "DOGE", "ADA", "AVAX", "LINK", "DOT", "LTC", "BCH", "TRX", "TON", "SUI", "APT", "NEAR", "UNI", "FIL", "ATOM", "ETC", "AAVE", "ARB", "OP"},
                new String[]{
                        "BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "XRP/USDT:USDT",
                        "BNB/USDT:USDT", "DOGE/USDT:USDT", "ADA/USDT:USDT", "AVAX/USDT:USDT",
                        "LINK/USDT:USDT", "DOT/USDT:USDT", "LTC/USDT:USDT", "BCH/USDT:USDT",
                        "TRX/USDT:USDT", "TON/USDT:USDT", "SUI/USDT:USDT", "APT/USDT:USDT",
                        "NEAR/USDT:USDT", "UNI/USDT:USDT", "FIL/USDT:USDT", "ATOM/USDT:USDT",
                        "ETC/USDT:USDT", "AAVE/USDT:USDT", "ARB/USDT:USDT", "OP/USDT:USDT"
                }
        ), marginTop(8));
        backtestCard.addView(labeled("타임프레임 (목록 선택 또는 직접 입력)", timeframeInput), marginTop(10));
        backtestCard.addView(quickChoiceRow(
                "자주 쓰는 주기",
                timeframeInput,
                new String[]{"1분", "3분", "5분", "15분", "30분", "1시간", "4시간", "1일"},
                new String[]{"1m", "3m", "5m", "15m", "30m", "1h", "4h", "1d"}
        ), marginTop(8));

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
        quickRow.addView(smallButton("1년", v -> setQuickRange(365)), smallButtonParams());
        quickRow.addView(smallButton("2년", v -> setQuickRange(730)), smallButtonParams());
        quickRow.addView(smallButton("3년", v -> setQuickRange(1095)), smallButtonParams());
        quickRow.addView(smallButton("5년", v -> setQuickRange(1826)), smallButtonParams());
        quickRow.addView(smallButton("10년", v -> setQuickRange(3653)), smallButtonParams());
        backtestCard.addView(quickRow, marginTop(10));

        riskProfileInput = autocomplete(new String[]{"공격형", "중간형", "안전형", "3봉 분할형"}, "공격형");
        riskProfileInput.setOnItemClickListener((parent, view, position, id) ->
                applyRiskProfile(parent.getItemAtPosition(position).toString()));
        backtestCard.addView(labeled("백테스트 위험 프로필", riskProfileInput), marginTop(12));

        LinearLayout profileRow = new LinearLayout(this);
        profileRow.setOrientation(LinearLayout.HORIZONTAL);
        profileRow.setGravity(Gravity.CENTER_VERTICAL);
        profileRow.addView(smallButton("공격형", v -> applyRiskProfile("공격형")), smallButtonParams());
        profileRow.addView(smallButton("중간형", v -> applyRiskProfile("중간형")), smallButtonParams());
        profileRow.addView(smallButton("안전형", v -> applyRiskProfile("안전형")), smallButtonParams());
        profileRow.addView(smallButton("3봉 분할", v -> applyRiskProfile("3봉 분할형")), smallButtonParams());
        backtestCard.addView(profileRow, marginTop(8));
        backtestCard.addView(text(
                "기간은 직접 선택합니다. 3봉 분할형=첫 진입 3연속 하락/상승봉 역추세·회당 1~3배·최대 1~5회(총 15배)이며, 나머지 전략 수치를 함께 최적화합니다.",
                11, MUTED, false
        ), marginTop(7));

        initialCapitalInput = edit("1000");
        backtestCard.addView(labeled("초기자산 (USDT)", initialCapitalInput), marginTop(12));
        backtestCard.addView(text(
                "예: 1000 · 허용 범위 10~1,000,000,000 USDT",
                11, MUTED, false
        ), marginTop(7));

        sizingModeInput = autocomplete(new String[]{"복리식", "고정식"}, "복리식");
        backtestCard.addView(binaryChoiceRow(
                "자산 계산 방식", sizingModeInput,
                new String[]{"복리식", "고정식"},
                new String[]{"복리식", "고정식"}
        ), marginTop(12));
        backtestCard.addView(text(
                "복리식=현재 순자산 기준으로 다음 진입 규모를 재계산 · 고정식=입력한 초기자산 기준을 계속 사용",
                11, MUTED, false
        ), marginTop(7));

        executionModelInput = autocomplete(
                new String[]{"현실형 · 다음 봉 시가 체결", "기존형 · 신호 봉 종가 체결"},
                "현실형 · 다음 봉 시가 체결"
        );
        backtestCard.addView(binaryChoiceRow(
                "백테스트 체결 모델", executionModelInput,
                new String[]{"현실형(추천)", "기존형(비교)"},
                new String[]{"현실형 · 다음 봉 시가 체결", "기존형 · 신호 봉 종가 체결"}
        ), marginTop(12));
        backtestCard.addView(text(
                "현실형=신호 확정 후 다음 봉 시가 진입 · 기존형=예전 결과와 비교하기 위한 신호 봉 종가 진입",
                11, MUTED, false
        ), marginTop(7));

        optimizationSpeedInput = autocomplete(
                new String[]{"빠른 탐색 · 추천", "표준 탐색", "정밀 탐색"},
                "빠른 탐색 · 추천"
        );
        backtestCard.addView(labeled("휴대폰 최적화 속도", optimizationSpeedInput), marginTop(12));
        backtestCard.addView(quickChoiceRow(
                "속도 선택", optimizationSpeedInput,
                new String[]{"빠른(추천)", "표준", "정밀"},
                new String[]{"빠른 탐색 · 추천", "표준 탐색", "정밀 탐색"}
        ), marginTop(8));
        backtestCard.addView(text(
                "빠른=1차 100·TOP3×100 · 표준=1차 500·TOP5×300 · 정밀=입력값·TOP10. 동일 설정은 체크포인트를 재사용합니다.",
                11, MUTED, false
        ), marginTop(7));

        adaptiveRegimeInput = autocomplete(
                new String[]{"자동 전환 사용", "고정 전략 사용 · 기본"},
                "고정 전략 사용 · 기본"
        );
        backtestCard.addView(binaryChoiceRow(
                "시장 국면별 전략 자동 전환", adaptiveRegimeInput,
                new String[]{"자동 전환", "고정 전략(기본)"},
                new String[]{"자동 전환 사용", "고정 전략 사용 · 기본"}
        ), marginTop(12));
        backtestCard.addView(text(
                "기본값은 고정 전략입니다. 필요할 때만 자동 전환을 켜면 과거 288개 마감봉으로 시장 국면을 판단합니다.",
                11, MUTED, false
        ), marginTop(7));

        precheckInput = autocomplete(
                new String[]{"사용 · 추천", "사용 안 함"},
                "사용 · 추천"
        );
        backtestCard.addView(binaryChoiceRow(
                "최근 30일 빠른 사전검사", precheckInput,
                new String[]{"사용(추천)", "사용 안 함"},
                new String[]{"사용 · 추천", "사용 안 함"}
        ), marginTop(12));
        backtestCard.addView(text(
                "거래 없음·청산·과도한 낙폭 후보만 먼저 제외합니다. 통과 후보가 너무 적으면 자동으로 전체 검사를 수행합니다.",
                11, MUTED, false
        ), marginTop(7));

        optimizationStageInput = autocomplete(
                new String[]{"1차 전체 탐색", "상위 후보 정밀 탐색", "6개월 → 3개월 롤링 + 최종 선정", "전체 자동 실행"},
                "전체 자동 실행"
        );
        backtestCard.addView(labeled("자동 최적화 단계", optimizationStageInput), marginTop(12));
        backtestCard.addView(quickChoiceRow(
                "단계 선택",
                optimizationStageInput,
                new String[]{"1차 탐색", "정밀 탐색", "6→3개월 롤링", "전체 자동"},
                new String[]{"1차 전체 탐색", "상위 후보 정밀 탐색", "6개월 → 3개월 롤링 + 최종 선정", "전체 자동 실행"}
        ), marginTop(8));
        backtestCard.addView(text(
                "후속 단계는 앞 단계 체크포인트를 자동 재사용합니다. 전체 자동은 1차→TOP10 후보별 정밀→6개월 롤링→3개월 롤링→최종 선정을 순서대로 실행합니다.",
                11, MUTED, false
        ), marginTop(7));

        broadTrialCountInput = autocomplete(new String[]{"100", "500", "1000", "2000", "3000", "5000"}, "100");
        backtestCard.addView(labeled("1차 전체 탐색 조합 수 (1~5000)", broadTrialCountInput), marginTop(12));
        backtestCard.addView(quickChoiceRow(
                "1차 빠른 선택", broadTrialCountInput,
                new String[]{"100회", "500회", "1000회", "3000회", "5000회"},
                new String[]{"100", "500", "1000", "3000", "5000"}
        ), marginTop(8));

        refineTrialCountInput = autocomplete(new String[]{"100", "300", "500", "1000", "2000", "3000", "5000"}, "100");
        backtestCard.addView(labeled("2차 정밀 탐색 · TOP10 후보당 조합 수 (1~5000)", refineTrialCountInput), marginTop(12));
        backtestCard.addView(quickChoiceRow(
                "정밀 빠른 선택", refineTrialCountInput,
                new String[]{"100회", "500회", "1000회", "3000회", "5000회"},
                new String[]{"100", "500", "1000", "3000", "5000"}
        ), marginTop(8));
        backtestCard.addView(text(
                "예: 후보당 5,000회 선택 시 1차 TOP10 각각을 정밀 탐색하여 최대 50,000개 조합을 검사합니다.",
                11, MUTED, false
        ), marginTop(7));

        threeTickModeInput = autocomplete(new String[]{"첫 진입만 3틱룰", "모든 진입 3틱룰"}, "첫 진입만 3틱룰");
        backtestCard.addView(binaryChoiceRow(
                "3틱룰 적용 범위", threeTickModeInput,
                new String[]{"첫 진입만", "모든 진입"},
                new String[]{"첫 진입만 3틱룰", "모든 진입 3틱룰"}
        ), marginTop(12));

        TextView storageInfo = text("저장 위치: 앱 내부 저장소 / UniversalTradingBotCache", 12, MUTED, false);
        backtestCard.addView(storageInfo, marginTop(10));

        runButton = actionButton("▶ 백그라운드 캐시 생성 + 백테스트", PRIMARY);
        runButton.setOnClickListener(v -> runBacktest());
        backtestCard.addView(runButton, marginTop(12));
        Button downloadDbButton = actionButton("⬇ 코인·기간·주기 DB만 다운로드", SUCCESS);
        downloadDbButton.setOnClickListener(v -> downloadDatabaseOnly());
        backtestCard.addView(downloadDbButton, marginTop(8));
        Button selectDbButton = actionButton("🗄 저장된 DB 선택 · DB별 수치", Color.rgb(30, 41, 59));
        selectDbButton.setOnClickListener(v -> showSavedDatabasePicker());
        backtestCard.addView(selectDbButton, marginTop(8));
        backtestCard.addView(text(
                "현재 선택한 코인·타임프레임·시작일~종료일의 Binance/Bitget/OKX/Bybit SQLite만 저장하고 백테스트는 실행하지 않습니다.",
                11, MUTED, false
        ), marginTop(5));

        Button topStrategiesButton = actionButton("🏆 수익률 TOP10 전략 선택", Color.rgb(30, 41, 59));
        topStrategiesButton.setOnClickListener(v -> showTopStrategies(false));
        backtestCard.addView(topStrategiesButton, marginTop(8));
        Button pasteJsonButton = actionButton("📋 JSON 붙여넣기 / 파일 불러오기", PRIMARY);
        pasteJsonButton.setOnClickListener(v -> showJsonPasteDialog());
        backtestCard.addView(pasteJsonButton, marginTop(8));
        backtestCard.addView(text(
                "클립보드에 붙여넣거나 휴대폰의 JSON 파일을 선택하면 전략 수치와 JSON 기간을 자동 입력합니다.",
                11, MUTED, false
        ), marginTop(5));
        selectedStrategyText = text(
                "선택된 전략 없음 · 최적화 완료 후 TOP10에서 선택하면 모든 전략 수치가 자동 입력됩니다.",
                11, MUTED, false
        );
        backtestCard.addView(selectedStrategyText, marginTop(6));
        Button selectedDetailsButton = actionButton("📋 선택된 전략 전체 수치 보기", Color.rgb(30, 41, 59));
        selectedDetailsButton.setOnClickListener(v -> showSelectedStrategyDetails());
        backtestCard.addView(selectedDetailsButton, marginTop(8));
        Button editSelectedButton = actionButton("✏ 불러온/선택한 전략 수치 직접 수정", PRIMARY);
        editSelectedButton.setOnClickListener(v -> showStrategyParameterEditor());
        backtestCard.addView(editSelectedButton, marginTop(8));
        Button selectedBacktestButton = actionButton("▶ 선택/수정한 수치로 기간 재백테스트", SUCCESS);
        selectedBacktestButton.setOnClickListener(v -> runSelectedStrategyBacktest());
        backtestCard.addView(selectedBacktestButton, marginTop(8));

        LinearLayout controlRow = new LinearLayout(this);
        controlRow.setOrientation(LinearLayout.HORIZONTAL);
        pauseBacktestButton = smallButton("⏸ 일시중지", v -> controlBacktest(BacktestForegroundService.ACTION_PAUSE));
        resumeBacktestButton = smallButton("▶ 재개", v -> controlBacktest(BacktestForegroundService.ACTION_RESUME));
        stopBacktestButton = smallButton("■ 중지", v -> controlBacktest(BacktestForegroundService.ACTION_STOP));
        controlRow.addView(pauseBacktestButton, smallButtonParams());
        controlRow.addView(resumeBacktestButton, smallButtonParams());
        controlRow.addView(stopBacktestButton, smallButtonParams());
        backtestCard.addView(controlRow, marginTop(8));
        Button fullExportButton = actionButton(
                "📤 전체 자동 결과 파일 보내기 (MDD 70% 초과 포함)",
                Color.rgb(30, 41, 59)
        );
        fullExportButton.setOnClickListener(v -> exportAndShareOptimizationResults());
        backtestCard.addView(fullExportButton, marginTop(8));
        backtestCard.addView(text(
                "완료 후 1차·정밀·3개월 롤링·최종 선정과 MDD 제한 초과 후보까지 한 JSON으로 공유합니다.",
                11, MUTED, false
        ), marginTop(5));
        setBacktestControlState("IDLE");
        Button strategyLabButton = actionButton("⚙ 서버와 동일한 전략 수치 조정 / 백테스트", Color.rgb(30, 41, 59));
        strategyLabButton.setOnClickListener(v -> {
            Intent intent = new Intent(this, ServerDashboardActivity.class);
            intent.putExtra("dashboard_path", "/strategy");
            startActivity(intent);
        });
        backtestCard.addView(strategyLabButton, marginTop(8));
        TextView rangeHint = text("모든 USDT 무기한 선물 심볼 직접 입력 가능 · 최대 10년 · 실제 시작일은 4개 거래소 공통 상장 이력에 따라 달라집니다.", 11, MUTED, false);
        backtestCard.addView(rangeHint, marginTop(8));

        View metricsPanel = buildMetrics();
        root.addView(metricsPanel, 2, marginTop(14));

LinearLayout resultActions = panel();
root.addView(resultActions, 3, marginTop(12));
resultActions.addView(sectionTitle("성과 분석 대시보드"));

resultActions.addView(resultGroupTitle("① 핵심 분석", "요약 · 차트 · 모든 거래를 한곳에서 확인"));
resultSummaryButton = actionButton("📊 성과 요약 보기", PRIMARY);
resultSummaryButton.setOnClickListener(v -> showResultSummary());
tradeHistoryButton = actionButton("📋 전체 거래내역 보기", Color.rgb(30, 41, 59));
tradeHistoryButton.setOnClickListener(v -> showTradeHistory());
chartButton = actionButton("📈 순자산·낙폭 차트 + 거래 표시", Color.rgb(30, 41, 59));
chartButton.setOnClickListener(v -> showBacktestChart());
Button localChartButton = actionButton("🕯 코인 DB 차트 · 캔들 / TP·SL / 거래", PRIMARY);
localChartButton.setOnClickListener(v -> {
    Intent chartIntent = new Intent(this, LocalMarketChartActivity.class);
    chartIntent.putExtra("db_path", lastDbPath);
    chartIntent.putExtra("result_path", lastResultPath);
    startActivity(chartIntent);
});
resultActions.addView(localChartButton, marginTop(6));
deepBacktestButton = actionButton("📊 딥백테스트 리포트", PRIMARY);
deepBacktestButton.setOnClickListener(v -> showDeepBacktestReport());
resultActions.addView(deepBacktestButton, marginTop(6));
Button regimeButton = actionButton("🌦 시장 국면별 성과·자동전환 확인", PRIMARY);
regimeButton.setOnClickListener(v -> showMarketRegimePerformance());
resultActions.addView(regimeButton, marginTop(6));
Button validationButton = actionButton("🛡 다중 검증·실전 안전게이트", SUCCESS);
validationButton.setOnClickListener(v -> showValidationSuite());
resultActions.addView(validationButton, marginTop(6));
Button comparisonButton = actionButton("🔎 저장 결과 찾기·비교·재검증", Color.rgb(30, 41, 59));
comparisonButton.setOnClickListener(v -> showRecentResultComparison());
resultActions.addView(comparisonButton, marginTop(6));
pinnedResultText = text("고정된 저장 결과 없음", 12, MUTED, false);
resultActions.addView(pinnedResultText, marginTop(6));
Button reopenPinnedButton = actionButton("📌 고정된 결과 다시 열기", Color.rgb(30, 41, 59));
reopenPinnedButton.setOnClickListener(v -> reopenPinnedResult());
resultActions.addView(reopenPinnedButton, marginTop(6));
Button monthlyButton = actionButton("🗓 월별 성과·손실 구간 보기", Color.rgb(30, 41, 59));
monthlyButton.setOnClickListener(v -> showMonthlyPerformance());
resultActions.addView(monthlyButton, marginTop(6));
Button reproducibilityButton = actionButton("🔒 결과 재현 정보·실행 지문", Color.rgb(30, 41, 59));
reproducibilityButton.setOnClickListener(v -> showReproducibility());
resultActions.addView(reproducibilityButton, marginTop(6));

resultActions.addView(resultGroupTitle("② 단계별 결과 파일", "각 단계 결과를 따로 JSON으로 저장·공유"), marginTop(14));
resultActions.addView(stageExportButton("1차 전체 탐색 결과", "broad"), marginTop(6));
resultActions.addView(stageExportButton("2차 정밀 탐색 결과", "refined"), marginTop(6));
resultActions.addView(stageExportButton("3차 6개월 롤링 결과", "rolling6"), marginTop(6));
resultActions.addView(stageExportButton("4차 3개월 롤링 결과", "rolling3"), marginTop(6));
resultActions.addView(stageExportButton("5차 최종 선정 결과", "final"), marginTop(6));

resultActions.addView(resultGroupTitle("③ 전체 묶음", "모든 단계 + MDD 초과 후보 포함"), marginTop(14));
Button shareResultButton = actionButton("최종 백테스트 원본 JSON 공유", Color.rgb(30, 41, 59));
shareResultButton.setOnClickListener(v -> shareBacktestFile(lastResultPath, "application/json", "최종 백테스트 원본 JSON 공유"));
resultActions.addView(shareResultButton, marginTop(6));
Button bundleButton = actionButton("📦 요약·거래·월별 성과 전체 ZIP 공유", SUCCESS);
bundleButton.setOnClickListener(v -> exportAndShareAnalysisBundle());
resultActions.addView(bundleButton, marginTop(6));
Button shareOptimizationButton = actionButton("전체 최적화 통합 JSON 공유", Color.rgb(30, 41, 59));
shareOptimizationButton.setOnClickListener(v -> exportAndShareOptimizationResults());
resultActions.addView(shareOptimizationButton, marginTop(6));

resultActions.addView(resultGroupTitle("④ 원본 데이터 / 캐시", "재백테스트용 SQLite 데이터"), marginTop(14));
Button shareCacheButton = actionButton("현재 캐시 DB 공유", Color.rgb(30, 41, 59));
shareCacheButton.setOnClickListener(v -> shareBacktestFile(lastDbPath, "application/vnd.sqlite3", "백테스트 캐시 DB 공유"));
resultActions.addView(shareCacheButton, marginTop(6));
enableResultActions(false);

        LinearLayout serverCard = panel();
        root.addView(serverCard, marginTop(14));
        serverCard.addView(sectionTitle("서버 업로드"));
        hostInput = edit("34.132.172.40");
        userInput = edit("kpj3669");
        remoteInput = edit("/home/kpj3669/.cache/universal-trading-bot");
        serverCard.addView(labeled("서버", hostInput));
        serverCard.addView(labeled("사용자", userInput), marginTop(8));
        serverCard.addView(labeled("원격 캐시 폴더", remoteInput), marginTop(8));

        keyButton = actionButton("휴대폰 SSH 키 불러오기 / 다시 확인", Color.rgb(30, 41, 59));
        keyButton.setOnClickListener(v -> ensurePhoneKey());
        serverCard.addView(keyButton, marginTop(12));

        publicKeyText = text("휴대폰 SSH 키를 생성하면 공개키가 여기에 표시됩니다. 서버 authorized_keys에 한 번만 등록하면 됩니다.", 11, MUTED, false);
        publicKeyText.setTextIsSelectable(true);
        publicKeyText.setPadding(dp(10), dp(10), dp(10), dp(10));
        publicKeyText.setBackground(rounded(Color.rgb(7, 16, 29), 10, BORDER));
        serverCard.addView(publicKeyText, marginTop(8));

        Button copyKeyButton = smallButton("공개키 복사", v -> copyPublicKey());
        serverCard.addView(copyKeyButton, marginTop(8));

        sshTestButton = actionButton("SSH 서버 연결 다시 확인", Color.rgb(30, 41, 59));
        sshTestButton.setOnClickListener(v -> testSsh());
        serverCard.addView(sshTestButton, marginTop(10));

        Button inspectCacheButton = actionButton("서버 백테스트 캐시 연결 / 목록 확인", Color.rgb(30, 41, 59));
        inspectCacheButton.setOnClickListener(v -> inspectServerCache(inspectCacheButton));
        serverCard.addView(inspectCacheButton, marginTop(8));

        uploadButton = actionButton("⬆ 완료된 결과 서버 업로드 (최대 10년)", SUCCESS);
        uploadButton.setEnabled(false);
        uploadButton.setAlpha(0.45f);
        uploadButton.setOnClickListener(v -> uploadLast());
        serverCard.addView(uploadButton, marginTop(8));

        TextView protection = text("안전장치: 1일~10년 범위에서 완성·검증된 캐시만 서버 업로드가 활성화됩니다.", 11, MUTED, false);
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
        logText = text("앱은 로컬에서 실행됩니다. 백그라운드 실행 중에는 진행 로그가 자동으로 갱신됩니다.", 11, Color.rgb(219, 234, 254), false);
        logText.setTypeface(Typeface.MONOSPACE);
        logText.setTextIsSelectable(true);
        logText.setPadding(dp(10), dp(10), dp(10), dp(10));
        logText.setBackground(rounded(Color.rgb(7, 16, 29), 10, BORDER));
        logText.setClickable(true);
        logText.setFocusable(true);
        logText.setOnClickListener(v -> showTextDialog("전체 실행 로그 · 최신순", newestLogFirst(latestFullLog)));
        statusText.setClickable(true);
        statusText.setOnClickListener(v -> showTextDialog("전체 실행 로그 · 최신순", newestLogFirst(latestFullLog)));
        logCard.addView(logText, marginTop(8));
        TextView logHint = text("최근 10줄만 표시 · 누르면 최신 로그부터 전체 내용이 열립니다.", 11, ACCENT, false);
        logCard.addView(logHint, marginTop(7));

        LinearLayout navigation = new LinearLayout(this);
        navigation.setOrientation(LinearLayout.HORIZONTAL);
        root.addView(navigation, 2, marginTop(14));
        logCard.removeView(statusRow);
        logTitle.setText("작업 상태");
        root.addView(statusRow, 3, marginTop(10));
        View[] pages = {backtestCard, resultActions, serverCard, logCard};
        String[] labels = {"설정", "결과", "서버", "로그"};
        Button[] tabs = new Button[labels.length];
        android.content.SharedPreferences uiPrefs = getSharedPreferences("backtester_ui", MODE_PRIVATE);
        java.util.function.IntConsumer selectTab = selected -> {
            for (int i = 0; i < pages.length; i++) {
                pages[i].setVisibility(i == selected ? View.VISIBLE : View.GONE);
                tabs[i].setSelected(i == selected);
                tabs[i].setBackground(rounded(i == selected ? PRIMARY : Color.rgb(30, 41, 59), 10, BORDER));
                tabs[i].setContentDescription(labels[i] + (i == selected ? " · 선택됨" : ""));
            }
            metricsPanel.setVisibility(selected == 1 ? View.VISIBLE : View.GONE);
            engineStatusButton.setVisibility(selected == 3 ? View.VISIBLE : View.GONE);
            engineHint.setVisibility(selected == 3 ? View.VISIBLE : View.GONE);
            uiPrefs.edit().putInt("selected_tab", selected).apply();
        };
        for (int i = 0; i < labels.length; i++) {
            final int selected = i;
            tabs[i] = smallButton(labels[i], v -> selectTab.accept(selected));
            tabs[i].setMinHeight(dp(48));
            LinearLayout.LayoutParams tabParams = smallButtonParams();
            tabParams.height = dp(48);
            navigation.addView(tabs[i], tabParams);
        }
        selectTab.accept(Math.max(0, Math.min(3, uiPrefs.getInt("selected_tab", 0))));
        return scroll;
    }

    private View buildMetrics() {
        LinearLayout dashboard = panel();
        dashboard.addView(sectionTitle("최근 백테스트 핵심 성과"));
        dashboard.addView(text("수익성과 위험을 먼저 확인하고 아래에서 상세 분석하세요.", 11, MUTED, false));

        HorizontalScrollView scroll = new HorizontalScrollView(this);
        scroll.setHorizontalScrollBarEnabled(false);
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        scroll.addView(row);

        returnValue = metric(row, "총 수익률");
        mddValue = metric(row, "최대 낙폭");
        winRateValue = metric(row, "승률");
        pfValue = metric(row, "Profit Factor");
        tradesValue = metric(row, "거래 수");
        qualityValue = metric(row, "신뢰도");
        dashboard.addView(scroll, marginTop(10));
        return dashboard;
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

    private void applyRiskProfile(String profile) {
        String normalized = profile == null ? "공격형" : profile.trim();
        if (!"공격형".equals(normalized) && !"중간형".equals(normalized) && !"안전형".equals(normalized) && !"3봉 분할형".equals(normalized)) {
            normalized = "공격형";
        }
        riskProfileInput.setText(normalized, false);
        toast(normalized + " MDD 제한과 진입 탐색 범위를 적용했습니다. 기간은 변경하지 않습니다.");
    }

    private void runBacktest() {
        startBacktest(null);
    }

    private void runSelectedStrategyBacktest() {
        if (selectedStrategyParameters == null) {
            toast("먼저 수익률 TOP10에서 전략을 선택하세요.");
            return;
        }
        startBacktest(selectedStrategyParameters);
    }

    private void showJsonPasteDialog() {
        LinearLayout content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(dp(18), dp(4), dp(18), 0);
        content.addView(text(
                "백테스트 원본 JSON, 전체 자동 결과, 단계별 결과 또는 TOP 후보 JSON을 붙여넣거나 파일로 선택하세요. JSON에 기간이 있으면 화면 기간도 자동으로 바뀝니다.",
                12, MUTED, false
        ));

        EditText jsonInput = edit("");
        jsonInput.setHint("{\n  \"symbol\": \"BTC/USDT:USDT\",\n  ...\n}");
        jsonInput.setSingleLine(false);
        jsonInput.setGravity(Gravity.TOP | Gravity.START);
        jsonInput.setMinLines(10);
        jsonInput.setMaxLines(18);
        jsonInput.setHorizontallyScrolling(false);
        jsonInput.setPadding(dp(12), dp(12), dp(12), dp(12));
        content.addView(jsonInput, marginTop(10));

        Button clipboardButton = smallButton("클립보드 내용 붙여넣기", v -> {
            ClipboardManager manager = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
            ClipData clip = manager == null ? null : manager.getPrimaryClip();
            if (clip == null || clip.getItemCount() == 0) {
                toast("클립보드에 붙여넣을 내용이 없습니다.");
                return;
            }
            CharSequence value = clip.getItemAt(0).coerceToText(this);
            jsonInput.setText(value == null ? "" : value.toString());
            jsonInput.setSelection(jsonInput.length());
        });
        content.addView(clipboardButton, marginTop(8));

        Button fileButton = smallButton("📂 휴대폰에서 JSON 파일 선택", v ->
                openJsonFilePicker(jsonInput));
        content.addView(fileButton, marginTop(8));

        AlertDialog dialog = new AlertDialog.Builder(this)
                .setTitle("JSON 전략 불러오기")
                .setView(content)
                .setPositiveButton("읽기", null)
                .setNegativeButton("취소", null)
                .create();
        dialog.setOnShowListener(ignored -> dialog.getButton(AlertDialog.BUTTON_POSITIVE)
                .setOnClickListener(v -> {
                    String raw = jsonInput.getText().toString().trim();
                    if (raw.isEmpty()) {
                        toast("JSON을 붙여넣으세요.");
                        return;
                    }
                    dialog.getButton(AlertDialog.BUTTON_POSITIVE).setEnabled(false);
                    parsePastedBacktestJson(raw, dialog);
                }));
        dialog.setOnDismissListener(ignored -> {
            if (pendingJsonInput == jsonInput) pendingJsonInput = null;
        });
        dialog.show();
    }

    private void openJsonFilePicker(EditText target) {
        pendingJsonInput = target;
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("application/json");
        intent.putExtra(Intent.EXTRA_MIME_TYPES, new String[]{
                "application/json", "text/json", "text/plain", "application/octet-stream"
        });
        try {
            startActivityForResult(intent, REQUEST_OPEN_JSON);
        } catch (Exception e) {
            pendingJsonInput = null;
            toast("JSON 파일 선택기를 열 수 없습니다.");
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != REQUEST_OPEN_JSON || resultCode != RESULT_OK || data == null) return;
        Uri uri = data.getData();
        EditText target = pendingJsonInput;
        if (uri == null || target == null) {
            toast("선택한 JSON 파일을 읽을 수 없습니다.");
            return;
        }
        toast("JSON 파일을 읽는 중입니다.");
        executor.execute(() -> {
            try {
                String raw = readJsonDocument(uri);
                main.post(() -> {
                    if (pendingJsonInput != target) return;
                    target.setText(raw);
                    target.setSelection(target.length());
                    toast("JSON 파일을 불러왔습니다. 내용을 확인하고 '읽기'를 누르세요.");
                });
            } catch (Exception e) {
                main.post(() -> showTextDialog("JSON 파일 불러오기 실패", stackMessage(e)));
            }
        });
    }

    private String readJsonDocument(Uri uri) throws Exception {
        InputStream stream = getContentResolver().openInputStream(uri);
        if (stream == null) throw new IllegalArgumentException("파일 내용을 열 수 없습니다.");
        try (InputStream input = stream;
             BufferedReader reader = new BufferedReader(new InputStreamReader(input, StandardCharsets.UTF_8))) {
            StringBuilder raw = new StringBuilder();
            char[] buffer = new char[8192];
            int count;
            while ((count = reader.read(buffer)) >= 0) {
                raw.append(buffer, 0, count);
                if (raw.length() > MAX_IMPORTED_JSON_CHARS) {
                    throw new IllegalArgumentException("JSON 파일은 8MB 이하만 불러올 수 있습니다.");
                }
            }
            if (raw.toString().trim().isEmpty()) {
                throw new IllegalArgumentException("선택한 JSON 파일이 비어 있습니다.");
            }
            return raw.toString();
        }
    }

    private void parsePastedBacktestJson(String raw, AlertDialog dialog) {
        executor.execute(() -> {
            try {
                PyObject bridge = Python.getInstance().getModule("mobile_bridge");
                JSONObject parsed = new JSONObject(
                        bridge.callAttr("parse_pasted_backtest_json", raw).toString()
                );
                main.post(() -> {
                    dialog.dismiss();
                    showImportedJsonCandidates(parsed);
                });
            } catch (Exception e) {
                main.post(() -> {
                    dialog.getButton(AlertDialog.BUTTON_POSITIVE).setEnabled(true);
                    appendFullLog("\nJSON IMPORT ERROR\n" + stackMessage(e) + "\n");
                    showTextDialog("JSON 불러오기 실패", stackMessage(e));
                });
            }
        });
    }

    private void showImportedJsonCandidates(JSONObject parsed) {
        JSONArray items = parsed.optJSONArray("items");
        if (items == null || items.length() == 0) {
            toast("JSON에서 실행할 전략 수치를 찾지 못했습니다.");
            return;
        }
        if (items.length() == 1) {
            applyImportedJsonCandidate(parsed, items.optJSONObject(0));
            return;
        }
        String[] labels = new String[items.length()];
        for (int i = 0; i < items.length(); i++) {
            JSONObject item = items.optJSONObject(i);
            JSONObject result = item == null ? null : item.optJSONObject("result");
            boolean hasMetrics = result != null
                    && result.has("return_percent") && result.has("max_drawdown_percent");
            labels[i] = hasMetrics
                    ? String.format(
                    Locale.KOREA,
                    "%d위 · 수익률 %.2f%% · MDD %.2f%% · %s",
                    i + 1,
                    result.optDouble("return_percent", 0.0),
                    result.optDouble("max_drawdown_percent", 0.0),
                    item == null ? "JSON 후보" : item.optString("label", "JSON 후보")
            ) : String.format(
                    Locale.KOREA,
                    "%d위 · 원본 성과 없음 · %s",
                    i + 1,
                    item == null ? "JSON 후보" : item.optString("label", "JSON 후보")
            );
        }
        new AlertDialog.Builder(this)
                .setTitle("JSON 후보 선택 · 최대 10개")
                .setItems(labels, (whichDialog, which) ->
                        applyImportedJsonCandidate(parsed, items.optJSONObject(which)))
                .setNegativeButton("취소", null)
                .show();
    }

    private void applyImportedJsonCandidate(JSONObject parsed, JSONObject item) {
        if (item == null) {
            toast("선택한 JSON 후보를 읽지 못했습니다.");
            return;
        }
        JSONObject parameters = item.optJSONObject("effective_parameters");
        if (parameters == null) parameters = item.optJSONObject("parameters");
        if (parameters == null) {
            toast("선택한 JSON 후보에 전략 파라미터가 없습니다.");
            return;
        }
        selectedStrategyParameters = parameters;
        selectedStrategyRow = item;
        try {
            selectedStrategyRow.put("imported_json", true);
        } catch (Exception ignored) {
        }

        String symbol = parsed.optString("symbol", "").trim();
        String timeframe = parsed.optString("timeframe", "").trim();
        String start = parsed.optString("requested_start", "").trim();
        String end = parsed.optString("requested_end", "").trim();
        if (!symbol.isEmpty()) symbolInput.setText(symbol, false);
        if (!timeframe.isEmpty()) timeframeInput.setText(timeframe, false);
        if (!start.isEmpty()) startInput.setText(start);
        if (!end.isEmpty()) endInput.setText(end);

        String riskProfile = parsed.optString("risk_profile", "").trim();
        if ("공격형".equals(riskProfile) || "중간형".equals(riskProfile)
                || "안전형".equals(riskProfile) || "3봉 분할형".equals(riskProfile)) {
            riskProfileInput.setText(riskProfile, false);
        }
        if (parsed.has("initial_capital") && !parsed.isNull("initial_capital")) {
            double capital = parsed.optDouble("initial_capital", Double.NaN);
            if (!Double.isNaN(capital) && capital >= 10.0 && capital <= 1_000_000_000.0) {
                initialCapitalInput.setText(String.valueOf(capital));
            }
        }
        if (parsed.has("compounding_enabled") && !parsed.isNull("compounding_enabled")) {
            sizingModeInput.setText(parsed.optBoolean("compounding_enabled", true) ? "복리식" : "고정식", false);
        }
        String executionModel = parsed.optString("execution_model", "");
        if ("next_open".equals(executionModel) || "signal_close".equals(executionModel)) {
            executionModelInput.setText(
                    "next_open".equals(executionModel)
                            ? "현실형 · 다음 봉 시가 체결"
                            : "기존형 · 신호 봉 종가 체결",
                    false
            );
        }
        if (parameters.has("adaptive_regime_enabled")) {
            adaptiveRegimeInput.setText(
                    parameters.optBoolean("adaptive_regime_enabled", false)
                            ? "자동 전환 사용 · 추천" : "고정 전략 사용",
                    false
            );
        }
        if (parameters.has("apply_consecutive_candles_to_all_entries")) {
            threeTickModeInput.setText(
                    parameters.optBoolean("apply_consecutive_candles_to_all_entries", false)
                            ? "모든 진입 3틱룰" : "첫 진입만 3틱룰",
                    false
            );
        }

        JSONObject result = item.optJSONObject("result");
        String candidateLabel = item.optString("label", "JSON 전략");
        boolean hasOriginalMetrics = result != null
                && result.has("return_percent") && result.has("max_drawdown_percent");
        String originalMetrics = hasOriginalMetrics
                ? String.format(
                Locale.KOREA,
                "원본 수익률 %.2f%% · MDD %.2f%%",
                result.optDouble("return_percent", 0.0),
                result.optDouble("max_drawdown_percent", 0.0)
        ) : "원본 성과 없음 · 독립 백테스트 설정";
        selectedStrategyText.setText(String.format(
                Locale.KOREA,
                "JSON 불러오기 완료 · %s\n%s %s · %s ~ %s\n%s · 진입 %.2f배 · 최대 %d회",
                candidateLabel,
                symbolInput.getText().toString().trim(),
                timeframeInput.getText().toString().trim(),
                startInput.getText().toString().trim(),
                endInput.getText().toString().trim(),
                originalMetrics,
                parameters.optDouble("entry_multiplier", 1.0),
                parameters.optInt("max_pyramiding", 1)
        ));
        selectedStrategyText.setTextColor(ACCENT);
        persistSelectedStrategy();

        String periodSource = parsed.optBoolean("uses_json_period", false)
                ? "JSON에 저장된 기간" : "현재 화면의 기간(JSON에 기간 없음)";
        new AlertDialog.Builder(this)
                .setTitle("JSON 전략 준비 완료")
                .setMessage("전략 수치·심볼·타임프레임을 불러왔습니다.\n\n"
                        + periodSource + ": " + startInput.getText() + " ~ " + endInput.getText()
                        + "\n체결: " + executionModelInput.getText()
                        + "\n계산: " + sizingModeInput.getText()
                        + "\n\n수치를 직접 수정하면 원본 재현이 아닌 새 변형 전략으로 안전하게 구분합니다.")
                .setPositiveButton("수치 확인·수정", (confirmDialog, which) ->
                        showStrategyParameterEditor())
                .setNeutralButton("바로 실행", (confirmDialog, which) ->
                        startBacktest(selectedStrategyParameters))
                .setNegativeButton("불러오기만", null)
                .show();
    }

    private void showStrategyParameterEditor() {
        if (selectedStrategyParameters == null || selectedStrategyRow == null) {
            toast("먼저 JSON을 불러오거나 TOP10 전략을 선택하세요.");
            return;
        }

        JSONObject current;
        try {
            current = new JSONObject(selectedStrategyParameters.toString());
        } catch (Exception e) {
            showTextDialog("전략 수치 읽기 실패", stackMessage(e));
            return;
        }

        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        LinearLayout content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(dp(18), dp(8), dp(18), dp(18));
        content.addView(text(
                "JSON 또는 TOP10에서 불러온 값을 항목별로 수정합니다. 심볼·기간·타임프레임은 메인 화면에서 별도로 바꿀 수 있습니다.\n"
                        + "진입 비중만 입력하면 진입 배수는 자동 계산되며, 수정본은 원본 재현과 분리해 저장합니다.",
                12, MUTED, false
        ));

        Map<String, EditText> valueInputs = new LinkedHashMap<>();
        Map<String, Switch> boolInputs = new LinkedHashMap<>();
        Map<String, AutoCompleteTextView> choiceInputs = new LinkedHashMap<>();
        Map<String, String> initialValues = new LinkedHashMap<>();

        for (String[] spec : STRATEGY_EDITOR_FIELDS) {
            String type = spec[0];
            String label = spec[1];
            String key = spec[2];
            if ("section".equals(type)) {
                TextView section = sectionTitle(label);
                section.setTextColor(ACCENT);
                content.addView(section, marginTop(16));
                continue;
            }
            if ("bool".equals(type)) {
                boolean checked = editorBooleanValue(current, key, Boolean.parseBoolean(spec[5]));
                Switch toggle = new Switch(this);
                toggle.setChecked(checked);
                toggle.setText(checked ? "켜짐" : "꺼짐");
                toggle.setTextColor(TEXT);
                toggle.setTextSize(14);
                toggle.setPadding(dp(8), 0, dp(8), 0);
                toggle.setOnCheckedChangeListener((button, enabled) ->
                        button.setText(enabled ? "켜짐" : "꺼짐"));
                boolInputs.put(key, toggle);
                initialValues.put(key, String.valueOf(checked));
                content.addView(labeled(label, toggle), marginTop(8));
                continue;
            }
            if ("choice".equals(type)) {
                String model = editorStringValue(current, key, spec[5], type);
                AutoCompleteTextView choice = autocomplete(
                        new String[]{"현실형 · 다음 봉 시가 체결", "기존형 · 신호 봉 종가 체결"},
                        "next_open".equals(model)
                                ? "현실형 · 다음 봉 시가 체결"
                                : "기존형 · 신호 봉 종가 체결"
                );
                choiceInputs.put(key, choice);
                initialValues.put(key, model);
                content.addView(labeled(label, choice), marginTop(8));
                continue;
            }

            String value = editorStringValue(current, key, spec[5], type);
            EditText input = edit(value);
            if ("int".equals(type)) {
                input.setInputType(InputType.TYPE_CLASS_NUMBER | InputType.TYPE_NUMBER_FLAG_SIGNED);
            } else if ("decimal".equals(type)) {
                input.setInputType(InputType.TYPE_CLASS_NUMBER
                        | InputType.TYPE_NUMBER_FLAG_DECIMAL
                        | InputType.TYPE_NUMBER_FLAG_SIGNED);
            }
            valueInputs.put(key, input);
            initialValues.put(key, value);
            content.addView(labeled(label, input), marginTop(8));
        }
        scroll.addView(content, new ScrollView.LayoutParams(
                ScrollView.LayoutParams.MATCH_PARENT,
                ScrollView.LayoutParams.WRAP_CONTENT
        ));

        AlertDialog.Builder builder = new AlertDialog.Builder(this)
                .setTitle("전략 전체 수치 직접 수정")
                .setView(scroll)
                .setPositiveButton("수정 적용", null)
                .setNegativeButton("취소", null);
        JSONObject base = selectedStrategyRow.optJSONObject("manual_edit_base_parameters");
        if (base != null) {
            builder.setNeutralButton("불러온 원본 복원", (ignored, which) ->
                    restoreManualEditBase());
        }
        AlertDialog dialog = builder.create();
        dialog.setOnShowListener(ignored -> {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v ->
                    applyManualStrategyEdits(
                            dialog, current, valueInputs, boolInputs, choiceInputs, initialValues
                    ));
            if (dialog.getWindow() != null) {
                dialog.getWindow().setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE);
            }
        });
        dialog.show();
    }

    private boolean editorBooleanValue(JSONObject parameters, String key, boolean fallback) {
        if ("backtest_compounding_enabled".equals(key)) {
            return !"고정식".equals(sizingModeInput.getText().toString().trim());
        }
        if ("adaptive_regime_enabled".equals(key)) {
            return adaptiveRegimeInput.getText().toString().startsWith("자동");
        }
        if ("apply_consecutive_candles_to_all_entries".equals(key)) {
            return "모든 진입 3틱룰".equals(threeTickModeInput.getText().toString().trim());
        }
        return parameters.has(key) && !parameters.isNull(key)
                ? parameters.optBoolean(key, fallback) : fallback;
    }

    private String editorStringValue(
            JSONObject parameters, String key, String fallback, String type
    ) {
        if ("initial_capital".equals(key)) {
            return initialCapitalInput.getText().toString().trim().replace(",", "");
        }
        if ("backtest_execution_model".equals(key)) {
            return executionModelInput.getText().toString().contains("다음 봉")
                    ? "next_open" : "signal_close";
        }
        Object raw = parameters.has(key) && !parameters.isNull(key)
                ? parameters.opt(key) : fallback;
        if ("int".equals(type)) {
            try {
                return String.valueOf((int) Math.rint(Double.parseDouble(String.valueOf(raw))));
            } catch (Exception ignored) {
                return fallback;
            }
        }
        if ("decimal".equals(type)) {
            try {
                return compactNumber(Double.parseDouble(String.valueOf(raw)));
            } catch (Exception ignored) {
                return fallback;
            }
        }
        return raw == null ? fallback : String.valueOf(raw);
    }

    private void applyManualStrategyEdits(
            AlertDialog dialog,
            JSONObject original,
            Map<String, EditText> valueInputs,
            Map<String, Switch> boolInputs,
            Map<String, AutoCompleteTextView> choiceInputs,
            Map<String, String> initialValues
    ) {
        try {
            JSONObject edited = new JSONObject(original.toString());
            Map<String, Double> numericValues = new LinkedHashMap<>();
            Map<String, Boolean> booleanValues = new LinkedHashMap<>();
            Map<String, String> normalizedValues = new LinkedHashMap<>();
            int changed = 0;

            for (String[] spec : STRATEGY_EDITOR_FIELDS) {
                String type = spec[0];
                String label = spec[1];
                String key = spec[2];
                if ("section".equals(type)) continue;

                if ("bool".equals(type)) {
                    boolean value = boolInputs.get(key).isChecked();
                    booleanValues.put(key, value);
                    String normalized = String.valueOf(value);
                    normalizedValues.put(key, normalized);
                    if (!normalized.equals(initialValues.get(key))) {
                        edited.put(key, value);
                        changed++;
                    }
                    continue;
                }

                if ("choice".equals(type)) {
                    String value = choiceInputs.get(key).getText().toString().contains("다음 봉")
                            ? "next_open" : "signal_close";
                    normalizedValues.put(key, value);
                    if (!value.equals(initialValues.get(key))) {
                        edited.put(key, value);
                        changed++;
                    }
                    continue;
                }

                EditText input = valueInputs.get(key);
                String raw = input.getText().toString().trim();
                if ("text".equals(type)) {
                    String value = "excluded_hours".equals(key)
                            ? normalizeExcludedHours(raw) : raw;
                    normalizedValues.put(key, value);
                    if (!value.equals(initialValues.get(key))) {
                        edited.put(key, value);
                        changed++;
                    }
                    continue;
                }

                if (raw.isEmpty()) {
                    throw new IllegalArgumentException(label + " 값을 입력하세요.");
                }
                double value;
                try {
                    value = Double.parseDouble(raw.replace(",", ""));
                } catch (Exception e) {
                    throw new IllegalArgumentException(label + " 값을 숫자로 입력하세요.");
                }
                if (Double.isNaN(value) || Double.isInfinite(value)) {
                    throw new IllegalArgumentException(label + " 값이 올바르지 않습니다.");
                }
                double minimum = Double.parseDouble(spec[3]);
                double maximum = Double.parseDouble(spec[4]);
                if (value < minimum || value > maximum) {
                    throw new IllegalArgumentException(
                            label + " 값은 " + compactNumber(minimum) + "~"
                                    + compactNumber(maximum) + " 범위여야 합니다."
                    );
                }
                if ("int".equals(type) && Math.abs(value - Math.rint(value)) > 1e-9) {
                    throw new IllegalArgumentException(label + " 값은 정수로 입력하세요.");
                }
                numericValues.put(key, value);
                String normalized = "int".equals(type)
                        ? String.valueOf((int) Math.rint(value)) : compactNumber(value);
                normalizedValues.put(key, normalized);
                if (!sameNumericText(normalized, initialValues.get(key))) {
                    edited.put(key, "int".equals(type) ? (int) Math.rint(value) : value);
                    changed++;
                }
            }

            validateManualStrategyValues(numericValues, booleanValues);

            double orderPercent = numericValues.get("order_percent_of_equity");
            double entryMultiplier = orderPercent / 100.0;
            double oldEntry = edited.optDouble("entry_multiplier", Double.NaN);
            if (Double.isNaN(oldEntry) || Math.abs(oldEntry - entryMultiplier) > 1e-9) {
                edited.put("entry_multiplier", entryMultiplier);
                changed++;
            }

            if (changed == 0) {
                dialog.dismiss();
                toast("변경된 전략 수치가 없습니다.");
                return;
            }

            // These settings also have visible controls on the main screen.
            // Store and update both places so the run cannot use a hidden value.
            double capital = numericValues.get("initial_capital");
            boolean compounding = booleanValues.get("backtest_compounding_enabled");
            boolean adaptive = booleanValues.get("adaptive_regime_enabled");
            boolean allEntriesThreeTick = booleanValues.get(
                    "apply_consecutive_candles_to_all_entries"
            );
            String execution = normalizedValues.get("backtest_execution_model");
            edited.put("initial_capital", capital);
            edited.put("backtest_compounding_enabled", compounding);
            edited.put("adaptive_regime_enabled", adaptive);
            edited.put("apply_consecutive_candles_to_all_entries", allEntriesThreeTick);
            edited.put("backtest_execution_model", execution);

            JSONObject row = new JSONObject(selectedStrategyRow.toString());
            if (row.optJSONObject("manual_edit_base_parameters") == null) {
                row.put("manual_edit_base_parameters", new JSONObject(original.toString()));
            }
            row.put("parameters", edited);
            row.put("effective_parameters", edited);
            row.put("manually_edited", true);
            row.put("manual_edit_count", row.optInt("manual_edit_count", 0) + changed);
            selectedStrategyParameters = edited;
            selectedStrategyRow = row;
            persistDbStrategyParameters();

            initialCapitalInput.setText(compactNumber(capital));
            sizingModeInput.setText(compounding ? "복리식" : "고정식", false);
            executionModelInput.setText(
                    "next_open".equals(execution)
                            ? "현실형 · 다음 봉 시가 체결"
                            : "기존형 · 신호 봉 종가 체결",
                    false
            );
            adaptiveRegimeInput.setText(
                    adaptive ? "자동 전환 사용 · 추천" : "고정 전략 사용", false
            );
            threeTickModeInput.setText(
                    allEntriesThreeTick ? "모든 진입 3틱룰" : "첫 진입만 3틱룰", false
            );
            selectedStrategyText.setText(String.format(
                    Locale.KOREA,
                    "수동 수정 전략 저장 완료 · 이번 %d개 변경\n진입 %.2f배 · 최대 %d회 · %s · %s",
                    changed,
                    entryMultiplier,
                    edited.optInt("max_pyramiding", 1),
                    "next_open".equals(execution) ? "다음 봉 시가" : "신호 봉 종가",
                    compounding ? "복리식" : "고정식"
            ));
            selectedStrategyText.setTextColor(Color.rgb(250, 204, 21));
            persistSelectedStrategy();
            dialog.dismiss();

            double requestedExposure = entryMultiplier
                    * numericValues.get("max_pyramiding");
            double exposureCap = numericValues.get("backtest_max_total_multiplier");
            String exposureNote = requestedExposure > exposureCap + 1e-9
                    ? String.format(
                            Locale.KOREA,
                            "\n\n주의: 입력상 총진입 %.2f배지만 엔진 최대 총노출 %.2f배에서 제한됩니다.",
                            requestedExposure, exposureCap
                    ) : "";
            new AlertDialog.Builder(this)
                    .setTitle("수동 수정 전략 저장 완료")
                    .setMessage("수정본은 원본 TOP10 재현 결과를 덮어쓰지 않습니다.\n"
                            + "백테스트 결과에는 '변형 전략 · 독립 백테스트'로 표시됩니다."
                            + exposureNote)
                    .setPositiveButton("이 수치로 실행", (ignored, which) ->
                            startBacktest(selectedStrategyParameters))
                    .setNeutralButton("전체 수치 보기", (ignored, which) ->
                            showSelectedStrategyDetails())
                    .setNegativeButton("닫기", null)
                    .show();
        } catch (Exception e) {
            showTextDialog(
                    "수치 확인 필요",
                    e.getMessage() == null ? stackMessage(e) : e.getMessage()
            );
        }
    }

    private void validateManualStrategyValues(
            Map<String, Double> numbers,
            Map<String, Boolean> booleans
    ) {
        if (!Boolean.TRUE.equals(booleans.get("allow_long"))
                && !Boolean.TRUE.equals(booleans.get("allow_short"))) {
            throw new IllegalArgumentException("LONG 또는 SHORT 중 하나 이상은 허용해야 합니다.");
        }
        requireOrdered(numbers, "min_one_bar_vol", "max_one_bar_vol", "1봉 변동 최소·최대");
        requireOrdered(numbers, "min_tp_percent", "max_tp_percent", "TP 최소·최대");
        requireOrdered(numbers, "min_sl_percent", "max_sl_percent", "SL 최소·최대");
        requireOrdered(numbers, "rsi_oversold_min", "rsi_oversold_max", "RSI 과매도 최소·최대");
        requireOrdered(numbers, "rsi_overbought_min", "rsi_overbought_max", "RSI 과매수 최소·최대");
        requireOrdered(numbers, "adx_min", "adx_max", "ADX 최소·최대");
        if (numbers.get("rsi_oversold_max") >= numbers.get("rsi_overbought_min")) {
            throw new IllegalArgumentException(
                    "RSI 과매도 최대는 과매수 최소보다 작아야 합니다. 두 구간이 겹치지 않게 입력하세요."
            );
        }
    }

    private void requireOrdered(
            Map<String, Double> values, String minimumKey, String maximumKey, String label
    ) {
        if (values.get(minimumKey) > values.get(maximumKey)) {
            throw new IllegalArgumentException(label + " 순서가 반대입니다. 최소값을 최대값 이하로 입력하세요.");
        }
    }

    private String normalizeExcludedHours(String raw) {
        String text = String.valueOf(raw == null ? "" : raw)
                .trim().replace('，', ',');
        if (text.isEmpty()) return "";
        String[] tokens = text.split("[,\\s]+");
        LinkedHashMap<Integer, Boolean> hours = new LinkedHashMap<>();
        for (String token : tokens) {
            if (token.isEmpty()) continue;
            int hour;
            try {
                hour = Integer.parseInt(token);
            } catch (Exception e) {
                throw new IllegalArgumentException(
                        "제외 시간 UTC는 0~23을 쉼표로 구분하세요. 예: 00,13,23"
                );
            }
            if (hour < 0 || hour > 23) {
                throw new IllegalArgumentException("제외 시간 UTC는 0~23 범위여야 합니다.");
            }
            hours.put(hour, true);
        }
        StringBuilder normalized = new StringBuilder();
        for (Integer hour : hours.keySet()) {
            if (normalized.length() > 0) normalized.append(',');
            normalized.append(String.format(Locale.US, "%02d", hour));
        }
        return normalized.toString();
    }

    private boolean sameNumericText(String left, String right) {
        try {
            return Math.abs(
                    Double.parseDouble(left) - Double.parseDouble(String.valueOf(right))
            ) <= 1e-9;
        } catch (Exception ignored) {
            return String.valueOf(left).equals(String.valueOf(right));
        }
    }

    private String compactNumber(double value) {
        if (Math.abs(value - Math.rint(value)) <= 1e-9) {
            return String.format(Locale.US, "%.0f", value);
        }
        String formatted = String.format(Locale.US, "%.10f", value);
        return formatted.replaceFirst("0+$", "").replaceFirst("\\.$", "");
    }

    private void restoreManualEditBase() {
        if (selectedStrategyRow == null) return;
        JSONObject base = selectedStrategyRow.optJSONObject("manual_edit_base_parameters");
        if (base == null) {
            toast("복원할 불러오기 원본이 없습니다.");
            return;
        }
        try {
            JSONObject restored = new JSONObject(base.toString());
            JSONObject row = new JSONObject(selectedStrategyRow.toString());
            row.put("parameters", restored);
            row.put("effective_parameters", restored);
            row.remove("manually_edited");
            row.remove("manual_edit_count");
            row.remove("manual_edit_base_parameters");
            selectedStrategyParameters = restored;
            selectedStrategyRow = row;
            syncMainControlsFromStrategy(restored);
            selectedStrategyText.setText("불러온 원본 전략 수치로 복원했습니다.");
            selectedStrategyText.setTextColor(ACCENT);
            persistSelectedStrategy();
            toast("수동 수정값을 취소하고 원본 수치를 복원했습니다.");
        } catch (Exception e) {
            showTextDialog("원본 수치 복원 실패", stackMessage(e));
        }
    }

    private void syncMainControlsFromStrategy(JSONObject parameters) {
        if (parameters.has("initial_capital")) {
            initialCapitalInput.setText(compactNumber(parameters.optDouble("initial_capital", 1000.0)));
        }
        if (parameters.has("backtest_compounding_enabled")) {
            sizingModeInput.setText(
                    parameters.optBoolean("backtest_compounding_enabled", true)
                            ? "복리식" : "고정식", false
            );
        }
        String execution = parameters.optString("backtest_execution_model", "");
        if ("next_open".equals(execution) || "signal_close".equals(execution)) {
            executionModelInput.setText(
                    "next_open".equals(execution)
                            ? "현실형 · 다음 봉 시가 체결"
                            : "기존형 · 신호 봉 종가 체결",
                    false
            );
        }
        if (parameters.has("adaptive_regime_enabled")) {
            adaptiveRegimeInput.setText(
                    parameters.optBoolean("adaptive_regime_enabled", false)
                            ? "자동 전환 사용 · 추천" : "고정 전략 사용", false
            );
        }
        if (parameters.has("apply_consecutive_candles_to_all_entries")) {
            threeTickModeInput.setText(
                    parameters.optBoolean("apply_consecutive_candles_to_all_entries", false)
                            ? "모든 진입 3틱룰" : "첫 진입만 3틱룰", false
            );
        }
    }

    private boolean replaySettingDiffers(JSONObject parameters, String key, Object value) {
        if (parameters == null || !parameters.has(key) || parameters.isNull(key)) return false;
        Object stored = parameters.opt(key);
        if (stored instanceof Number && value instanceof Number) {
            return Math.abs(((Number) stored).doubleValue() - ((Number) value).doubleValue()) > 1e-9;
        }
        if (stored instanceof Boolean && value instanceof Boolean) {
            return !stored.equals(value);
        }
        return !String.valueOf(stored).equals(String.valueOf(value));
    }

    private void startBacktest(JSONObject fixedParameters) {
        String symbol = symbolInput.getText().toString().trim();
        String timeframe = timeframeInput.getText().toString().trim();
        String riskProfile = riskProfileInput.getText().toString().trim();
        String sizingMode = sizingModeInput.getText().toString().trim();
        boolean compoundingEnabled = !"고정식".equals(sizingMode);
        sizingMode = compoundingEnabled ? "복리식" : "고정식";
        double initialCapital;
        try {
            initialCapital = Double.parseDouble(initialCapitalInput.getText().toString().trim().replace(",", ""));
        } catch (Exception ignored) {
            toast("초기자산을 숫자로 입력하세요. 예: 1000");
            return;
        }
        if (initialCapital < 10.0 || initialCapital > 1_000_000_000.0) {
            toast("초기자산은 10~1,000,000,000 USDT 범위로 입력하세요.");
            return;
        }
        String executionModel = executionModelInput.getText().toString().contains("다음 봉")
                ? "next_open" : "signal_close";
        String speedLabel = optimizationSpeedInput.getText().toString().trim();
        String optimizationSpeed = speedLabel.startsWith("정밀") ? "deep" : (speedLabel.startsWith("표준") ? "standard" : "quick");
        String stageLabel = optimizationStageInput.getText().toString().trim();
        String optimizationStage;
        if ("상위 후보 정밀 탐색".equals(stageLabel)) optimizationStage = "refine";
        else if ("6개월 → 3개월 롤링 + 최종 선정".equals(stageLabel)) optimizationStage = "rolling";
        else if ("전체 자동 실행".equals(stageLabel)) optimizationStage = "auto";
        else optimizationStage = "broad";
        int broadOptimizationTrials;
        int refineOptimizationTrials;
        try {
            broadOptimizationTrials = Integer.parseInt(broadTrialCountInput.getText().toString().trim());
            refineOptimizationTrials = Integer.parseInt(refineTrialCountInput.getText().toString().trim());
        } catch (Exception ignored) {
            toast("1차/정밀 조합 수는 각각 1~5000 사이 숫자로 입력하세요.");
            return;
        }
        if (broadOptimizationTrials < 1 || broadOptimizationTrials > 5000
                || refineOptimizationTrials < 1 || refineOptimizationTrials > 5000) {
            toast("1차/정밀 조합 수는 각각 1~5000 사이로 입력하세요.");
            return;
        }
        boolean allEntriesThreeTick = "모든 진입 3틱룰".equals(threeTickModeInput.getText().toString().trim());
        boolean precheckEnabled = !precheckInput.getText().toString().startsWith("사용 안");
        boolean adaptiveRegimeEnabled = adaptiveRegimeInput.getText().toString().startsWith("자동");
        String start = startInput.getText().toString().trim();
        String end = endInput.getText().toString().trim();
        Calendar startCal = parseDate(start);
        Calendar endCal = parseDate(end);
        if (symbol.isEmpty() || timeframe.isEmpty() || startCal == null || endCal == null) {
            toast("심볼, 타임프레임, 날짜를 확인하세요.");
            return;
        }
        long rangeDays = (endCal.getTimeInMillis() - startCal.getTimeInMillis()) / 86_400_000L + 1L;
        if (rangeDays <= 0L || rangeDays > 3660L) {
            toast("백테스트 기간은 1일 이상 최대 10년(3660일)까지 가능합니다.");
            return;
        }

        if (fixedParameters == null && !workloadConfirmed) {
            int topN = "quick".equals(optimizationSpeed) ? 3 : ("standard".equals(optimizationSpeed) ? 5 : 10);
            int broadCount = "quick".equals(optimizationSpeed) ? Math.min(100, broadOptimizationTrials)
                    : ("standard".equals(optimizationSpeed) ? Math.min(500, broadOptimizationTrials) : broadOptimizationTrials);
            int refineCount = "quick".equals(optimizationSpeed) ? Math.min(100, refineOptimizationTrials)
                    : ("standard".equals(optimizationSpeed) ? Math.min(300, refineOptimizationTrials) : refineOptimizationTrials);
            int estimated = broadCount + (("broad".equals(optimizationStage)) ? 0 : topN * refineCount);
            String estimateText = estimated < 500 ? "약 10~40분" : (estimated < 2500 ? "약 30분~2시간" : "수 시간 이상");
            new AlertDialog.Builder(this)
                    .setTitle("백테스트 실행 전 확인")
                    .setMessage("예상 핵심 조합 " + estimated + "회\n후속 후보 TOP" + topN
                            + "\n예상 시간 " + estimateText
                            + "\n사전검사 " + (precheckEnabled ? "사용" : "사용 안 함")
                            + "\n시장 국면 자동 전환 " + (adaptiveRegimeEnabled ? "사용" : "고정 전략")
                            + "\n\n기기 성능과 거래 수에 따라 실제 시간은 달라집니다.")
                    .setPositiveButton("실행", (dialog, which) -> {
                        workloadConfirmed = true;
                        startBacktest(null);
                    })
                    .setNegativeButton("설정 수정", null)
                    .show();
            return;
        }
        workloadConfirmed = false;

        JSONObject fixedParametersForRun = fixedParameters;
        boolean manuallyEditedReplay = selectedStrategyRow != null
                && selectedStrategyRow.optBoolean("manually_edited", false);
        if (fixedParameters != null) {
            try {
                fixedParametersForRun = new JSONObject(fixedParameters.toString());
                boolean visibleSettingsChanged =
                        replaySettingDiffers(fixedParameters, "initial_capital", initialCapital)
                                || replaySettingDiffers(
                                fixedParameters, "backtest_compounding_enabled", compoundingEnabled
                        )
                                || replaySettingDiffers(
                                fixedParameters, "backtest_execution_model", executionModel
                        )
                                || replaySettingDiffers(
                                fixedParameters, "adaptive_regime_enabled", adaptiveRegimeEnabled
                        )
                                || replaySettingDiffers(
                                fixedParameters,
                                "apply_consecutive_candles_to_all_entries",
                                allEntriesThreeTick
                        );
                manuallyEditedReplay = manuallyEditedReplay || visibleSettingsChanged;
                fixedParametersForRun.put("initial_capital", initialCapital);
                fixedParametersForRun.put("backtest_compounding_enabled", compoundingEnabled);
                fixedParametersForRun.put("backtest_execution_model", executionModel);
                fixedParametersForRun.put("adaptive_regime_enabled", adaptiveRegimeEnabled);
                fixedParametersForRun.put(
                        "apply_consecutive_candles_to_all_entries", allEntriesThreeTick
                );
            } catch (Exception e) {
                showTextDialog("선택 전략 준비 실패", stackMessage(e));
                return;
            }
        }

        Intent intent = new Intent(this, BacktestForegroundService.class);
        intent.setAction(BacktestForegroundService.ACTION_START);
        intent.putExtra("symbol", symbol);
        intent.putExtra("timeframe", timeframe);
        intent.putExtra("start", start);
        intent.putExtra("end", end);
        intent.putExtra("host", hostInput.getText().toString().trim());
        intent.putExtra("username", userInput.getText().toString().trim());
        intent.putExtra("remote_dir", remoteInput.getText().toString().trim());
        intent.putExtra("key_path", privateKeyPath);
        intent.putExtra("database_path", selectedDbPath);
        intent.putExtra("risk_profile", riskProfile);
        intent.putExtra("optimization_trials", broadOptimizationTrials);
        intent.putExtra("broad_optimization_trials", broadOptimizationTrials);
        intent.putExtra("refine_optimization_trials", refineOptimizationTrials);
        intent.putExtra("all_entries_three_tick", allEntriesThreeTick);
        intent.putExtra("compounding_enabled", compoundingEnabled);
        intent.putExtra("initial_capital", initialCapital);
        intent.putExtra("optimization_stage", optimizationStage);
        intent.putExtra("execution_model", executionModel);
        intent.putExtra("optimization_speed", optimizationSpeed);
        intent.putExtra("precheck_enabled", precheckEnabled);
        intent.putExtra("adaptive_regime_enabled", adaptiveRegimeEnabled);
        if (fixedParameters != null) {
            JSONObject replayPayload = new JSONObject();
            try {
                replayPayload.put("parameters", fixedParametersForRun);
                replayPayload.put("execution_model_override", executionModel);
                replayPayload.put(
                        "imported_json",
                        selectedStrategyRow != null && selectedStrategyRow.optBoolean("imported_json", false)
                );
                replayPayload.put("manually_edited", manuallyEditedReplay);
                if (selectedStrategyRow != null) {
                    JSONObject originalResult = selectedStrategyRow.optJSONObject("result");
                    if (originalResult == null) {
                        originalResult = selectedStrategyRow.optJSONObject("original_result");
                    }
                    replayPayload.put("original_result", originalResult == null ? new JSONObject() : originalResult);
                    replayPayload.put("source_context", selectedStrategyRow.optJSONObject("source_context"));
                    replayPayload.put("source_rank", selectedStrategyRow.optInt("rank", 0));
                }
            } catch (Exception ignored) {
            }
            intent.putExtra("selected_parameters_json", replayPayload.toString());
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(intent);
        } else {
            startService(intent);
        }
        lastDbPath = "";
        lastResultPath = "";
        lastUploadEligible = false;
        lastSummary = null;
        enableUpload(false);
        enableResultActions(false);
        setFullLog((fixedParameters == null ? "백그라운드 최적화 시작\n" : "선택 전략 기간 재백테스트 시작\n") + "프로필: " + riskProfile
                + " · 초기자산: " + String.format(Locale.KOREA, "%,.2f USDT", initialCapital)
                + " · 계산: " + sizingMode
                + " · 체결: " + ("next_open".equals(executionModel) ? "다음 봉 시가" : "신호 봉 종가")
                + " · 속도: " + (optimizationSpeed.equals("quick") ? "빠른" : (optimizationSpeed.equals("standard") ? "표준" : "정밀"))
                + " · 국면: " + (adaptiveRegimeEnabled ? "자동 전환" : "고정")
                + " · 단계: " + stageLabel
                + " · 1차: " + broadOptimizationTrials + "회"
                + " · 정밀: TOP10×" + refineOptimizationTrials + "회"
                + " · 3틱룰: " + (allEntriesThreeTick ? "모든 진입" : "첫 진입만") + "\n"
                + (fixedParameters == null ? "" : (
                        manuallyEditedReplay
                                ? "수동 변경 수치를 사용하는 변형 전략이며 재최적화하지 않습니다.\n"
                                : selectedStrategyRow != null && selectedStrategyRow.optBoolean("imported_json", false)
                                ? "불러온 JSON 전략 수치를 그대로 사용하며 재최적화하지 않습니다.\n"
                                : "TOP10에서 고른 전략 수치를 그대로 사용하며 재최적화하지 않습니다.\n"
                ))
                + "앱을 내리거나 화면을 꺼도 알림 서비스에서 계속 실행됩니다.\n");
        setBusy(true, "백그라운드 실행 중");
        setBacktestControlState("RUNNING");
        toast(fixedParameters == null ? "백그라운드 백테스트를 시작했습니다."
                : (manuallyEditedReplay
                ? "수동 수정 전략으로 독립 백테스트를 시작했습니다."
                : selectedStrategyRow != null && selectedStrategyRow.optBoolean("imported_json", false)
                ? "JSON 전략으로 해당 기간 재백테스트를 시작했습니다."
                : "선택한 수치로 기간 재백테스트를 시작했습니다."));
    }

    private void controlBacktest(String action) {
        Intent intent = new Intent(this, BacktestForegroundService.class);
        intent.setAction(action);
        startService(intent);
        if (BacktestForegroundService.ACTION_PAUSE.equals(action)) {
            setBacktestControlState("PAUSED");
            toast("완료된 지점에서 일시중지합니다.");
        } else if (BacktestForegroundService.ACTION_RESUME.equals(action)) {
            setBacktestControlState("RUNNING");
            toast("백테스트를 재개합니다.");
        } else {
            setBacktestControlState("STOPPING");
            toast("중지 중입니다. 체크포인트는 보존됩니다.");
        }
    }

    private void downloadDatabaseOnly() {
        String symbol = symbolInput.getText().toString().trim();
        String timeframe = timeframeInput.getText().toString().trim();
        String start = startInput.getText().toString().trim();
        String end = endInput.getText().toString().trim();
        if (symbol.isEmpty() || timeframe.isEmpty() || parseDate(start) == null || parseDate(end) == null) {
            toast("DB 다운로드 전 코인, 주기, 시작일, 종료일을 확인하세요.");
            return;
        }
        Calendar startCal = parseDate(start);
        Calendar endCal = parseDate(end);
        long rangeDays = (endCal.getTimeInMillis() - startCal.getTimeInMillis()) / 86_400_000L + 1L;
        if (rangeDays <= 0L || rangeDays > 3660L) {
            toast("DB 다운로드 기간은 1일 이상 최대 10년(3660일)까지 가능합니다.");
            return;
        }
        new AlertDialog.Builder(this)
                .setTitle("DB만 다운로드")
                .setMessage(symbol + " · " + timeframe + "\n" + start + " ~ " + end
                        + "\n\n4개 거래소 원본 캔들을 SQLite로 저장합니다. 백테스트는 실행하지 않습니다.")
                .setPositiveButton("다운로드", (dialog, which) -> {
                    Intent intent = new Intent(this, BacktestForegroundService.class);
                    intent.setAction(BacktestForegroundService.ACTION_DOWNLOAD_DB);
                    intent.putExtra("symbol", symbol);
                    intent.putExtra("timeframe", timeframe);
                    intent.putExtra("start", start);
                    intent.putExtra("end", end);
                    startService(intent);
                    setBacktestControlState("RUNNING");
                    setBusy(true, "DB 다운로드 중");
                    toast("DB 다운로드를 시작했습니다. 화면을 꺼도 계속됩니다.");
                })
                .setNegativeButton("취소", null)
                .show();
    }

    private void showSavedDatabasePicker() {
        File root = new File(getFilesDir(), "UniversalTradingBotCache");
        java.util.ArrayList<File> files = new java.util.ArrayList<>();
        collectDatabaseFiles(root, files);
        if (files.isEmpty()) {
            toast("저장된 DB가 없습니다. 먼저 DB만 다운로드를 실행하세요.");
            return;
        }
        files.sort((a, b) -> Long.compare(b.lastModified(), a.lastModified()));
        String[] labels = new String[files.size()];
        for (int i = 0; i < files.size(); i++) {
            File f = files.get(i);
            labels[i] = f.getName() + " · " + readableBytes(f.length());
        }
        new AlertDialog.Builder(this)
                .setTitle("백테스트에 사용할 저장 DB 선택")
                .setItems(labels, (dialog, which) -> {
                    File chosen = files.get(which);
                    selectedDbPath = chosen.getAbsolutePath();
                    lastDbPath = selectedDbPath;
                    getSharedPreferences("universal_bot", MODE_PRIVATE).edit()
                            .putString("selected_db_path", selectedDbPath).apply();
                    applySavedDatabaseSelection(chosen);
                })
                .setNegativeButton("닫기", null)
                .show();
    }

    private void collectDatabaseFiles(File dir, java.util.ArrayList<File> out) {
        if (dir == null || !dir.isDirectory()) return;
        File[] children = dir.listFiles();
        if (children == null) return;
        for (File child : children) {
            if (child.isDirectory()) collectDatabaseFiles(child, out);
            else if (child.isFile() && child.getName().toLowerCase(Locale.US).endsWith(".db")) out.add(child);
        }
    }

    private String readableBytes(long bytes) {
        if (bytes >= 1_000_000_000L) return String.format(Locale.US, "%.1f GB", bytes / 1_000_000_000.0);
        if (bytes >= 1_000_000L) return String.format(Locale.US, "%.1f MB", bytes / 1_000_000.0);
        return String.format(Locale.US, "%.1f KB", bytes / 1_000.0);
    }

    private String dbSettingsKey(String path) {
        return "db_strategy_" + Integer.toHexString(path == null ? 0 : path.hashCode());
    }

    private JSONObject defaultDbStrategyParameters() {
        JSONObject out = new JSONObject();
        try {
            for (String[] spec : STRATEGY_EDITOR_FIELDS) {
                String type = spec[0], key = spec[2];
                if ("section".equals(type)) continue;
                if ("bool".equals(type)) out.put(key, Boolean.parseBoolean(spec[5]));
                else if ("int".equals(type)) out.put(key, Integer.parseInt(spec[5]));
                else if ("decimal".equals(type)) out.put(key, Double.parseDouble(spec[5]));
                else if ("choice".equals(type)) out.put(key, spec[5]);
                else out.put(key, spec[5]);
            }
            out.put("entry_multiplier", out.optDouble("order_percent_of_equity", 100.0) / 100.0);
            out.put("database_defaults", true);
        } catch (Exception ignored) {
        }
        return out;
    }

    private JSONObject loadDbStrategyParameters(String path) {
        String raw = getSharedPreferences("universal_bot", MODE_PRIVATE)
                .getString(dbSettingsKey(path), "");
        if (!raw.isEmpty()) {
            try { return new JSONObject(raw); } catch (Exception ignored) { }
        }
        JSONObject defaults = defaultDbStrategyParameters();
        getSharedPreferences("universal_bot", MODE_PRIVATE).edit()
                .putString(dbSettingsKey(path), defaults.toString())
                .apply();
        return defaults;
    }

    private void persistDbStrategyParameters() {
        if (selectedDbPath == null || selectedDbPath.isEmpty() || selectedStrategyParameters == null) return;
        getSharedPreferences("universal_bot", MODE_PRIVATE).edit()
                .putString(dbSettingsKey(selectedDbPath), selectedStrategyParameters.toString())
                .apply();
    }

    private void applySavedDatabaseSelection(File chosen) {
        restoreSelectedDatabaseSettings(chosen);
        JSONObject parameters = selectedStrategyParameters;
        syncMainControlsFromStrategy(parameters);
        selectedStrategyText.setText(
                "DB 선택됨 · " + chosen.getName() + "\nDB별 전략 수치를 수정한 뒤 선택 DB로 백테스트합니다."
        );
        selectedStrategyText.setTextColor(ACCENT);
        toast("DB를 선택했습니다. '불러온/선택한 전략 수치 직접 수정'에서 DB별 값을 바꿀 수 있습니다.");
        showStrategyParameterEditor();
    }

    private void restoreSelectedDatabaseSettings(File chosen) {
        JSONObject parameters = loadDbStrategyParameters(chosen.getAbsolutePath());
        selectedStrategyParameters = parameters;
        selectedStrategyRow = new JSONObject();
        try {
            selectedStrategyRow.put("parameters", parameters);
            selectedStrategyRow.put("effective_parameters", parameters);
            selectedStrategyRow.put("manually_edited", true);
            selectedStrategyRow.put("database_path", chosen.getAbsolutePath());
        } catch (Exception ignored) {
        }
        syncMainControlsFromStrategy(parameters);
    }

    private void refreshBackgroundBacktestStatus() {
        SharedPreferences p = getSharedPreferences("universal_bot", MODE_PRIVATE);
        String state = p.getString("backtest_status", "IDLE");
        // A force-stop kills the service before its finally block can replace
        // STOPPING with STOPPED. Reconcile that persisted UI state on relaunch.
        if ("STOPPING".equals(state) && !BacktestForegroundService.isWorkerRunning()) {
            state = "STOPPED";
            p.edit()
                    .putBoolean("backtest_requested", false)
                    .putBoolean("backtest_paused", false)
                    .putString("backtest_status", "STOPPED")
                    .putString("backtest_error", "")
                    .apply();
        }
        setBacktestControlState(state);
        if ("RUNNING".equals(state)) {
            setBusy(true, "백그라운드 실행 중");
        } else if ("PAUSED".equals(state)) {
            setBusy(true, "일시중지됨");
        } else if ("STOPPING".equals(state)) {
            setBusy(true, "중지 중...");
        } else {
            setBusy(false, "COMPLETE".equals(state) ? "백테스트 완료" :
                    ("ERROR".equals(state) ? "백테스트 오류" :
                            ("STOPPED".equals(state) ? "중지됨 · 재실행 시 이어받기" : "준비됨")));
        }
        if ("RUNNING".equals(state) || "PAUSED".equals(state) || "STOPPING".equals(state)) {
            String liveLog = readLiveBacktestLog();
            if (!liveLog.isEmpty() && !latestFullLog.equals(liveLog)) {
                setFullLog(liveLog);
            }
        }
        if ("ERROR".equals(state)) {
            String error = p.getString("backtest_error", "");
            if (!error.isEmpty() && !latestFullLog.contains(error)) {
                appendFullLog("\nBACKGROUND ERROR\n" + error + "\n");
            }
        }
        if ("COMPLETE".equals(state)) {
            String path = p.getString("backtest_result", "");
            String logs = p.getString("backtest_log", "");
            if (!logs.isEmpty() && !latestFullLog.equals(logs)) {
                setFullLog(logs);
            }
            if (!path.isEmpty() && !path.equals(appliedServiceResultPath)) {
                appliedServiceResultPath = path;
                loadCompletedServiceResult(path);
            }
        }
    }

    private void setFullLog(String value) {
        latestFullLog = value == null ? "" : value;
        logText.setText(lastLogLines(latestFullLog, 10));
    }

    private void appendFullLog(String value) {
        latestFullLog += value == null ? "" : value;
        logText.setText(lastLogLines(latestFullLog, 10));
    }

    private String newestLogFirst(String value) {
        if (value == null || value.isEmpty()) return "";
        String normalized = value.replace("\r\n", "\n").replace('\r', '\n');
        String[] lines = normalized.split("\n", -1);
        int end = lines.length;
        while (end > 0 && lines[end - 1].isEmpty()) end--;
        StringBuilder newestFirst = new StringBuilder();
        for (int i = end - 1; i >= 0; i--) {
            if (newestFirst.length() > 0) newestFirst.append('\n');
            newestFirst.append(lines[i]);
        }
        return newestFirst.toString();
    }

    private String lastLogLines(String value, int maxLines) {
        if (value == null || value.isEmpty()) return "";
        String normalized = value.replace("\r\n", "\n").replace('\r', '\n');
        String[] lines = normalized.split("\n", -1);
        int end = lines.length;
        while (end > 0 && lines[end - 1].isEmpty()) end--;
        int start = Math.max(0, end - Math.max(1, maxLines));
        StringBuilder preview = new StringBuilder();
        for (int i = start; i < end; i++) {
            if (preview.length() > 0) preview.append('\n');
            preview.append(lines[i]);
        }
        return preview.toString();
    }

    private String readLiveBacktestLog() {
        File file = new File(new File(getFilesDir(), "UniversalTradingBotCache"), "backtest-progress.log");
        if (!file.isFile()) return "";
        StringBuilder out = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(new FileReader(file))) {
            String line;
            while ((line = reader.readLine()) != null) out.append(line).append('\n');
        } catch (Exception ignored) {
            return "";
        }
        int limit = 50000;
        return out.length() <= limit ? out.toString() : out.substring(out.length() - limit);
    }

    private void loadCompletedServiceResult(String path) {
        executor.execute(() -> {
            try {
                PyObject bridge = Python.getInstance().getModule("mobile_bridge");
                JSONObject item = new JSONObject(bridge.callAttr("load_saved_result", path).toString());
                JSONObject wrapper = new JSONObject();
                wrapper.put("path", item.optString("result", path));
                wrapper.put("db", item.optString("db", ""));
                wrapper.put("summary", item.optJSONObject("summary"));
                wrapper.put("label", "백그라운드 백테스트 완료");
                main.post(() -> {
                    applySavedResult(wrapper, false);
                    boolean cacheOnly = lastSummary != null && lastSummary.optBoolean("cache_only", false);
                    toast(cacheOnly ? "DB 다운로드가 완료됐습니다. 코인 DB 차트에서 확인하세요." : "백그라운드 백테스트가 완료됐습니다.");
                    if (cacheOnly) {
                        return;
                    }
                    if (lastSummary != null && !lastSummary.optBoolean("selected_strategy_retest", false)) {
                        showTopStrategies(true);
                    } else if (lastSummary != null) {
                        showReproductionComparison();
                    }
                });
            } catch (Exception e) {
                main.post(() -> appendFullLog("\nRESULT LOAD ERROR\n" + stackMessage(e) + "\n"));
            }
        });
    }

    private void setBacktestControlState(String state) {
        if (pauseBacktestButton == null) return;
        boolean running = "RUNNING".equals(state);
        boolean paused = "PAUSED".equals(state);
        boolean active = running || paused || "STOPPING".equals(state);
        pauseBacktestButton.setEnabled(running);
        pauseBacktestButton.setAlpha(running ? 1f : 0.45f);
        resumeBacktestButton.setEnabled(paused);
        resumeBacktestButton.setAlpha(paused ? 1f : 0.45f);
        stopBacktestButton.setEnabled(active);
        stopBacktestButton.setAlpha(active ? 1f : 0.45f);
    }


private View resultGroupTitle(String title, String subtitle) {
    LinearLayout wrap = new LinearLayout(this);
    wrap.setOrientation(LinearLayout.VERTICAL);
    wrap.addView(text(title, 13, ACCENT, true));
    wrap.addView(text(subtitle, 11, MUTED, false), marginTop(2));
    return wrap;
}

private Button stageExportButton(String label, String stage) {
    Button button = actionButton("⬇ " + label + " JSON", Color.rgb(30, 41, 59));
    button.setOnClickListener(v -> exportAndShareOptimizationStage(stage, label));
    return button;
}

private void exportAndShareOptimizationStage(String stage, String label) {
    if (lastResultPath == null || lastResultPath.trim().isEmpty()) {
        toast("먼저 완료된 최적화 결과를 불러오세요.");
        return;
    }
    statusText.setText(label + " 파일 생성 중");
    executor.execute(() -> {
        try {
            PyObject bridge = Python.getInstance().getModule("mobile_bridge");
            JSONObject exported = new JSONObject(bridge.callAttr("export_optimization_stage", lastResultPath, stage).toString());
            String path = exported.getString("path");
            int count = exported.optInt("count", 0);
            main.post(() -> {
                statusText.setText(label + " · " + count + "개");
                shareBacktestFile(path, "application/json", label + " JSON 공유");
            });
        } catch (Exception e) {
            main.post(() -> {
                appendFullLog("\nSTAGE EXPORT ERROR\n" + stackMessage(e) + "\n");
                statusText.setText(label + " 생성 오류");
                toast(label + " 파일 생성 실패");
            });
        }
    });
}

    private void exportAndShareOptimizationResults() {
        if (lastResultPath == null || lastResultPath.trim().isEmpty()) {
            toast("먼저 완료된 최적화 결과를 불러오세요.");
            return;
        }
        statusText.setText("전체 최적화 순위 생성 중");
        executor.execute(() -> {
            try {
                PyObject bridge = Python.getInstance().getModule("mobile_bridge");
                JSONObject exported = new JSONObject(
                        bridge.callAttr("export_optimization_results", lastResultPath).toString()
                );
                String path = exported.getString("path");
                int completed = exported.optInt("completed_trials", 0);
                int overLimit = exported.optInt("mdd_over_limit_trials", 0);
                int refined = exported.optInt("refined_trials", 0);
                int rolling = exported.optInt("rolling_candidates", 0);
                main.post(() -> {
                    statusText.setText("전체 결과 " + completed + "개 · MDD 초과 "
                            + overLimit + "개 · 정밀 " + refined + "개 · 롤링 " + rolling + "개");
                    shareBacktestFile(path, "application/json", "전체 자동 최적화 결과 JSON 공유");
                });
            } catch (Exception e) {
                main.post(() -> {
                    appendFullLog("\nOPTIMIZATION EXPORT ERROR\n" + stackMessage(e) + "\n");
                    statusText.setText("전체 순위 내보내기 오류");
                    toast("전체 순위 생성 실패 - 실행 로그를 확인하세요.");
                });
            }
        });
    }

    private void shareBacktestFile(String path, String mimeType, String chooserTitle) {
        if (path == null || path.trim().isEmpty()) {
            toast("먼저 백테스트를 완료하거나 저장된 결과를 불러오세요.");
            return;
        }
        File file = new File(path);
        if (!file.isFile()) {
            toast("공유할 파일을 찾을 수 없습니다.");
            return;
        }
        try {
            android.net.Uri uri = androidx.core.content.FileProvider.getUriForFile(
                    this,
                    getPackageName() + ".fileprovider",
                    file
            );
            Intent intent = new Intent(Intent.ACTION_SEND);
            intent.setType(mimeType);
            intent.putExtra(Intent.EXTRA_STREAM, uri);
            intent.putExtra(Intent.EXTRA_SUBJECT, file.getName());
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            startActivity(Intent.createChooser(intent, chooserTitle));
        } catch (Exception e) {
            appendFullLog("\nFILE SHARE ERROR\n" + stackMessage(e) + "\n");
            toast("파일 공유 실패 - 실행 로그를 확인하세요.");
        }
    }

    private void loadPhoneKey() {
        executor.execute(() -> {
            try {
                PyObject bridge = Python.getInstance().getModule("mobile_bridge");
                String value = bridge.callAttr(
                        "ensure_ssh_key",
                        getFilesDir().getAbsolutePath()
                ).toString();
                JSONObject obj = new JSONObject(value);
                privateKeyPath = obj.getString("private_key");
                String pub = obj.getString("public_key");
                main.post(() -> {
                    publicKeyText.setText(pub);
                    statusText.setText("기존 휴대폰 SSH 키 불러옴");
                });
            } catch (Exception e) {
                main.post(() -> statusText.setText("SSH 키 확인 필요"));
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
                    appendFullLog("\nSSH TEST: " + result + "\n");
                    sshTestButton.setEnabled(true);
                    toast("SSH 연결 성공");
                });
            } catch (Exception e) {
                main.post(() -> {
                    statusText.setText("SSH 연결 실패");
                    appendFullLog("\nSSH ERROR\n" + stackMessage(e) + "\n");
                    sshTestButton.setEnabled(true);
                    toast("SSH 연결 실패");
                });
            }
        });
    }

    private void inspectServerCache(Button button) {
        if (privateKeyPath.isEmpty()) {
            toast("휴대폰 SSH 키를 확인한 뒤 다시 시도하세요.");
            loadPhoneKey();
            return;
        }
        button.setEnabled(false);
        statusText.setText("서버 캐시 목록 확인 중...");
        executor.execute(() -> {
            try {
                PyObject bridge = Python.getInstance().getModule("mobile_bridge");
                String response = bridge.callAttr(
                        "inspect_server_cache",
                        hostInput.getText().toString(),
                        userInput.getText().toString(),
                        remoteInput.getText().toString(),
                        privateKeyPath
                ).toString();
                JSONObject obj = new JSONObject(response);
                JSONArray files = obj.getJSONArray("files");
                StringBuilder sb = new StringBuilder();
                sb.append("\n===== SERVER BACKTEST CACHE =====\n");
                sb.append(obj.getString("server"))
                        .append(" · ")
                        .append(obj.getString("remote_dir"))
                        .append("\n");
                if (files.length() == 0) {
                    sb.append("백테스트 캐시 파일 없음\n");
                } else {
                    for (int i = 0; i < files.length(); i++) {
                        JSONObject file = files.getJSONObject(i);
                        double mb = file.optLong("size", 0L) / 1024.0 / 1024.0;
                        sb.append(String.format(
                                Locale.US,
                                "%s · %.2f MB\n",
                                file.optString("name"),
                                mb
                        ));
                    }
                }
                main.post(() -> {
                    appendFullLog(sb.toString());
                    statusText.setText("서버 캐시 연결 정상 · " + files.length() + "개");
                    button.setEnabled(true);
                    toast("서버 백테스트 캐시 확인 완료");
                });
            } catch (Exception e) {
                main.post(() -> {
                    appendFullLog("\nSERVER CACHE ERROR\n" + stackMessage(e) + "\n");
                    statusText.setText("서버 캐시 연결 실패");
                    button.setEnabled(true);
                    toast("서버 캐시 연결 실패");
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
                    appendFullLog(sb.toString());
                    statusText.setText("서버 업로드 완료");
                    enableUpload(true);
                    toast("서버 업로드 완료");
                });
            } catch (Exception e) {
                main.post(() -> {
                    appendFullLog("\nUPLOAD ERROR\n" + stackMessage(e) + "\n");
                    statusText.setText("업로드 실패");
                    enableUpload(true);
                    toast("업로드 실패 - 로그를 확인하세요.");
                });
            }
        });
    }


    private void loadSavedResults(boolean restoreLatestOnly) {
        File output = new File(getFilesDir(), "UniversalTradingBotCache");
        executor.execute(() -> {
            try {
                PyObject bridge = Python.getInstance().getModule("mobile_bridge");
                JSONObject response = new JSONObject(
                        bridge.callAttr("list_saved_results", output.getAbsolutePath()).toString()
                );
                JSONArray items = response.optJSONArray("items");
                if (items == null || items.length() == 0) {
                    if (!restoreLatestOnly) main.post(() -> toast("저장된 백테스트 결과가 없습니다."));
                    return;
                }
                if (restoreLatestOnly) {
                    JSONObject latest = items.getJSONObject(0);
                    main.post(() -> applySavedResult(latest, true));
                    return;
                }
                String[] labels = new String[items.length()];
                for (int i = 0; i < items.length(); i++) {
                    labels[i] = items.getJSONObject(i).optString("label", "백테스트 " + (i + 1));
                }
                main.post(() -> new AlertDialog.Builder(this)
                        .setTitle("저장된 백테스트 기록 · " + items.length() + "개")
                        .setItems(labels, (dialog, which) -> {
                            JSONObject selected = items.optJSONObject(which);
                            if (selected != null) showSavedResultActions(selected);
                        })
                        .setNegativeButton("닫기", null)
                        .show());
            } catch (Exception e) {
                if (!restoreLatestOnly) {
                    main.post(() -> {
                        appendFullLog("\nSAVED RESULT ERROR\n" + stackMessage(e) + "\n");
                        toast("저장된 결과 불러오기 실패");
                    });
                }
            }
        });
    }

    private void applySavedResult(JSONObject item, boolean automatic) {
        JSONObject summary = item.optJSONObject("summary");
        if (summary == null) {
            toast("저장된 결과 형식이 올바르지 않습니다.");
            return;
        }
        lastSummary = summary;
        lastResultPath = item.optString("path", "");
        lastDbPath = item.optString("db", summary.optString("database", ""));
        if (!lastDbPath.isEmpty() && new File(lastDbPath).isFile()) {
            selectedDbPath = lastDbPath;
            getSharedPreferences("universal_bot", MODE_PRIVATE).edit()
                    .putString("selected_db_path", selectedDbPath).apply();
        }
        lastUploadEligible = summary.optBoolean("server_upload_eligible", false);
        String savedSymbol = summary.optString("symbol", "");
        String savedTimeframe = summary.optString("timeframe", "");
        if (!savedSymbol.isEmpty()) symbolInput.setText(savedSymbol, false);
        if (!savedTimeframe.isEmpty()) timeframeInput.setText(savedTimeframe, false);
        if (!automatic && summary.has("initial_capital")) {
            initialCapitalInput.setText(String.valueOf(summary.optDouble("initial_capital", 1000.0)));
        }
        String savedSizingMode = summary.optString("sizing_mode", "");
        if (!automatic && !savedSizingMode.isEmpty()) {
            sizingModeInput.setText(
                    "compound_current_equity".equals(savedSizingMode) ? "복리식" : "고정식",
                    false
            );
        }
        String savedExecutionModel = summary.optString("execution_model", "");
        if (!savedExecutionModel.isEmpty()) {
            executionModelInput.setText(
                    "next_open".equals(savedExecutionModel)
                            ? "현실형 · 다음 봉 시가 체결"
                            : "기존형 · 신호 봉 종가 체결",
                    false
            );
        }
        String savedStart = summary.optString("requested_start", "");
        String savedEnd = summary.optString("requested_end", "");
        if (!savedStart.isEmpty()) startInput.setText(savedStart);
        if (!savedEnd.isEmpty()) endInput.setText(savedEnd);
        updateMetrics(summary);
        enableResultActions(true);
        enableUpload(lastUploadEligible && new File(lastDbPath).isFile() && new File(lastResultPath).isFile());
        statusText.setText(automatic ? "최근 백테스트 자동 복원됨" : "저장된 백테스트 불러옴");
        appendFullLog("\n저장 결과 불러옴: " + item.optString("label", lastResultPath) + "\n");
        if (!automatic) toast("결과·차트·거래내역을 복원했습니다.");
    }

    private void showTopStrategies(boolean automatic) {
        if (lastResultPath == null || lastResultPath.isEmpty()) {
            if (!automatic) toast("최적화 결과를 먼저 완료하거나 저장된 결과를 불러오세요.");
            return;
        }
        executor.execute(() -> {
            try {
                PyObject bridge = Python.getInstance().getModule("mobile_bridge");
                JSONObject response = new JSONObject(
                        bridge.callAttr("list_top_strategies", lastResultPath, 10).toString()
                );
                JSONArray items = response.optJSONArray("items");
                if (items == null || items.length() == 0) {
                    if (!automatic) main.post(() -> toast("선택할 수 있는 최적화 후보가 없습니다."));
                    return;
                }
                String[] labels = new String[items.length()];
                for (int i = 0; i < items.length(); i++) {
                    JSONObject row = items.optJSONObject(i);
                    JSONObject result = row == null ? null : row.optJSONObject("result");
                    labels[i] = String.format(
                            Locale.KOREA,
                            "🔒 %d위 · 수익률 %.2f%% · MDD %.2f%% · 승률 %.1f%% · PF %.2f · 종합 %.1f",
                            i + 1,
                            result == null ? 0.0 : result.optDouble("return_percent", 0.0),
                            result == null ? 0.0 : result.optDouble("max_drawdown_percent", 0.0),
                            result == null ? 0.0 : result.optDouble("win_rate", 0.0),
                            result == null ? 0.0 : result.optDouble("profit_factor", 0.0),
                            row == null ? 0.0 : row.optDouble("composite_score", 0.0)
                    );
                }
                main.post(() -> new AlertDialog.Builder(this)
                        .setTitle("수익률 TOP" + items.length() + " · 전략 선택")
                        .setItems(labels, (dialog, which) -> {
                            JSONObject row = items.optJSONObject(which);
                            if (row == null) return;
                            selectedStrategyRow = row;
                            selectedStrategyParameters = row.optJSONObject("effective_parameters");
                            if (selectedStrategyParameters == null) {
                                selectedStrategyParameters = row.optJSONObject("parameters");
                            }
                            JSONObject result = row.optJSONObject("result");
                            if (selectedStrategyParameters == null) {
                                toast("선택한 후보의 전략 수치를 읽지 못했습니다.");
                                return;
                            }
                            syncMainControlsFromStrategy(selectedStrategyParameters);
                            selectedStrategyText.setText(String.format(
                                    Locale.KOREA,
                                    "%d위 수치 자동입력 완료 · 수익률 %.2f%% · MDD %.2f%%\n진입 %.0f배 · 최대 %d회 · 거래량 %.2f배 · RSI %d · ADX %d · TP %.2f~%.2f%% · SL %.2f~%.2f%%",
                                    which + 1,
                                    result == null ? 0.0 : result.optDouble("return_percent", 0.0),
                                    result == null ? 0.0 : result.optDouble("max_drawdown_percent", 0.0),
                                    selectedStrategyParameters.optDouble("entry_multiplier", 0.0),
                                    selectedStrategyParameters.optInt("max_pyramiding", 1),
                                    selectedStrategyParameters.optDouble("volume_break_multiplier", 0.0),
                                    selectedStrategyParameters.optInt("rsi_length", 0),
                                    selectedStrategyParameters.optInt("adx_length", 0),
                                    selectedStrategyParameters.optDouble("min_tp_percent", 0.0),
                                    selectedStrategyParameters.optDouble("max_tp_percent", 0.0),
                                    selectedStrategyParameters.optDouble("min_sl_percent", 0.0),
                                    selectedStrategyParameters.optDouble("max_sl_percent", 0.0)
                            ));
                            selectedStrategyText.setTextColor(ACCENT);
                            persistSelectedStrategy();
                            toast("전략 수치를 저장했습니다. 앱을 나가도 선택이 유지됩니다.");
                        })
                        .setNegativeButton("닫기", null)
                        .show());
            } catch (Exception e) {
                if (!automatic) main.post(() -> {
                    appendFullLog("\nTOP10 ERROR\n" + stackMessage(e) + "\n");
                    showTextDialog("TOP10 후보 불러오기 실패", stackMessage(e));
                });
            }
        });
    }

    private void showSelectedStrategyDetails() {
        if (selectedStrategyParameters == null) {
            toast("먼저 수익률 TOP10에서 전략을 선택하세요.");
            return;
        }
        JSONObject p = selectedStrategyParameters;
        StringBuilder sb = new StringBuilder();
        appendSettingGroup(sb, "진입 설정", p,
                new String[][]{{"롱 허용","allow_long"},{"숏 허용","allow_short"},{"첫 진입 연속봉","first_entry_consecutive_candles"},{"진입 배수","entry_multiplier"},{"주문 비율(%)","order_percent_of_equity"},{"최대 진입 횟수","max_pyramiding"},{"모든 진입 3틱룰","apply_consecutive_candles_to_all_entries"}});
        appendSettingGroup(sb, "거래량·변동성", p,
                new String[][]{{"거래량 평균 기간","volume_lookback"},{"거래량 돌파 배수","volume_break_multiplier"},{"1봉 변동 최소(%)","min_one_bar_vol"},{"1봉 변동 최대(%)","max_one_bar_vol"},{"변동성 계산 봉","volatility_bars"},{"N봉 차단 사용","use_nbar_volatility_block"},{"N봉 차단 기간","nbar_volatility_bars"},{"N봉 최대 변동(%)","max_nbar_volatility"}});
        appendSettingGroup(sb, "익절·손절", p,
                new String[][]{{"TP 변동성 배수","tp_vol_multiplier"},{"SL 변동성 배수","sl_vol_multiplier"},{"최소 TP(%)","min_tp_percent"},{"최대 TP(%)","max_tp_percent"},{"최소 SL(%)","min_sl_percent"},{"최대 SL(%)","max_sl_percent"}});
        appendSettingGroup(sb, "RSI", p,
                new String[][]{{"RSI 사용","use_rsi_filter"},{"RSI 기간","rsi_length"},{"과매도 최소","rsi_oversold_min"},{"과매도 최대","rsi_oversold_max"},{"과매수 최소","rsi_overbought_min"},{"과매수 최대","rsi_overbought_max"}});
        appendSettingGroup(sb, "ADX·재진입", p,
                new String[][]{{"ADX 사용","use_adx_filter"},{"ADX 기간","adx_length"},{"ADX 최소","adx_min"},{"ADX 최대","adx_max"},{"쿨다운 봉","cooldown_bars"},{"재진입 대기 봉","reentry_bars"}});
        appendSettingGroup(sb, "시장 국면", p,
                new String[][]{{"자동 전환","adaptive_regime_enabled"},{"판단 봉","regime_lookback_bars"},{"추세 판정 변동(%)","regime_trend_threshold_percent"},{"고변동성 판정(%)","regime_high_volatility_percent"},{"고변동성 진입 배수","regime_high_volatility_risk_multiplier"}});
        appendSettingGroup(sb, "시간·계산", p,
                new String[][]{{"체결 모델","backtest_execution_model"},{"주말 차단","block_weekend"},{"제외 시간","excluded_hours"},{"초기자산","initial_capital"},{"복리 계산","backtest_compounding_enabled"},{"레버리지","leverage"},{"수수료 편도(%)","backtest_fee_percent"},{"슬리피지 편도(%)","backtest_slippage_percent"},{"최대 총노출 배수","backtest_max_total_multiplier"},{"유지증거금(%)","backtest_maintenance_margin_percent"},{"교차청산 버퍼(%)","backtest_cross_liquidation_buffer_percent"}});
        try {
            sb.append("【원본 전체 수치 · 누락 없이 확인】\n")
                    .append(p.toString(2));
        } catch (Exception ignored) {
            sb.append("【원본 전체 수치】\n").append(p.toString());
        }
        showTextDialog("선택된 전략 전체 수치", sb.toString());
    }

    private void showReproductionComparison() {
        if (lastSummary == null) return;
        JSONObject comparison = lastSummary.optJSONObject("reproduction_comparison");
        if (comparison == null) return;
        boolean comparisonAvailable = comparison.optBoolean("comparison_available", true);
        String comparisonStatus = comparison.optString("status", "");
        if (!comparisonAvailable || "NOT_COMPARABLE".equals(comparisonStatus)) {
            boolean manuallyEdited = comparison.optBoolean("manually_edited", false);
            String retestModel = "next_open".equals(comparison.optString(
                    "retest_execution_model", lastSummary.optString("execution_model", "")))
                    ? "현실형 · 다음 봉 시가" : "기존형 · 신호 봉 종가";
            String compounding = comparison.optBoolean(
                    "retest_compounding", lastSummary.optBoolean("compounding_enabled", true))
                    ? "복리식" : "고정식";
            String message = String.format(
                    Locale.KOREA,
                    "재현 판정: 비교 대상 아님 · 독립 백테스트\n\n"
                            + (manuallyEdited
                            ? "불러온 전략 수치를 직접 수정했으므로 원본 TOP10과 다른 새 변형 전략입니다. "
                            + "의도된 변경을 FAIL로 판정하지 않습니다.\n\n"
                            : "직접 입력 설정 JSON에는 원래 TOP10 수익률·MDD, 요청 기간, 캐시 SHA256, "
                            + "엔진 코드와 후보 서명이 없습니다. 따라서 FAIL로 판정하지 않습니다.\n\n")
                            + "이번 수익률: %.2f%%\n이번 MDD: %.2f%%\n거래 수: %d회\n"
                            + "실제 기간: %s ~ %s\n실제 봉 수: %d\n체결 모델: %s\n계산 방식: %s\n\n"
                            + (manuallyEdited
                            ? "원본 수치로 복원한 뒤 실행하면 다시 동일 조건 재현 판정을 할 수 있습니다."
                            : "원본 TOP10 결과 JSON을 불러온 경우에만 동일 조건 재현 판정을 수행합니다."),
                    comparison.optDouble("retest_return_percent", lastSummary.optDouble("return_percent", 0.0)),
                    comparison.optDouble("retest_mdd_percent", lastSummary.optDouble("max_drawdown_percent", 0.0)),
                    lastSummary.optInt("trades", 0),
                    lastSummary.optString("data_start", lastSummary.optString("requested_start", "-")),
                    lastSummary.optString("data_end", lastSummary.optString("requested_end", "-")),
                    lastSummary.optInt("bars", 0),
                    retestModel,
                    compounding
            );
            showTextDialog(manuallyEdited ? "수동 수정 전략 백테스트" : "직접 입력 JSON 백테스트", message);
            return;
        }
        String period = comparison.optBoolean("same_requested_period", false) ? "동일" : "다름";
        String cache = comparison.optBoolean("same_cache_sha256", false) ? "동일" : "변경됨";
        String model = comparison.optBoolean("same_execution_model", false) ? "동일" : "다름";
        String originalModel = "next_open".equals(comparison.optString("original_execution_model"))
                ? "현실형 · 다음 봉 시가" : "기존형 · 신호 봉 종가";
        String retestModel = "next_open".equals(comparison.optString("retest_execution_model"))
                ? "현실형 · 다음 봉 시가" : "기존형 · 신호 봉 종가";
        String capital = comparison.has("same_initial_capital")
                ? (comparison.optBoolean("same_initial_capital") ? "동일" : "다름") : "확인 불가";
        String compound = comparison.has("same_compounding")
                ? (comparison.optBoolean("same_compounding") ? "동일" : "다름") : "확인 불가";
        String dataRange = comparison.optBoolean("same_data_range", false) ? "동일" : "다름";
        String engine = comparison.optBoolean("same_engine", false) ? "동일" : "다름";
        String parameters = comparison.optBoolean("same_strategy_parameters", false) ? "동일" : "다름";
        String candidate = comparison.optBoolean("source_candidate_verified", false) ? "정상" : "검증 실패";
        boolean exact = comparison.optBoolean("exact_reproduction", false);
        JSONArray reasons = comparison.optJSONArray("mismatch_reasons");
        StringBuilder reasonText = new StringBuilder();
        if (reasons != null) {
            for (int i = 0; i < reasons.length(); i++) {
                if (i > 0) reasonText.append(", ");
                reasonText.append(reasons.optString(i));
            }
        }
        if (reasonText.length() == 0) reasonText.append("없음");
        String message = String.format(
                Locale.KOREA,
                "재현 판정: %s\n불일치 항목: %s\n\n원래 TOP10 수익률: %.2f%%\n재백테스트 수익률: %.2f%%\n차이: %+.2f%%p\n\n원래 MDD: %.2f%%\n재백테스트 MDD: %.2f%%\n차이: %+.2f%%p\n\n요청 기간: %s\n실제 데이터 범위·봉 수: %s\n캐시 데이터: %s\n엔진 코드: %s\n전체 전략 수치: %s\nTOP10 후보 서명: %s\n체결 모델: %s\n  원본: %s\n  재검증: %s\n초기자산: %s\n복리 설정: %s\n\n모든 항목이 동일한데 결과가 다르면 엔진 무결성 실패로 표시됩니다. 이전 엔진 결과는 새 최적화 후 다시 선택해야 합니다.",
                exact ? "PASS · 완전 일치" : "FAIL · 조건 또는 결과 불일치",
                reasonText.toString(),
                comparison.optDouble("original_return_percent", 0.0),
                comparison.optDouble("retest_return_percent", 0.0),
                comparison.optDouble("return_difference_percent_points", 0.0),
                comparison.optDouble("original_mdd_percent", 0.0),
                comparison.optDouble("retest_mdd_percent", 0.0),
                comparison.optDouble("mdd_difference_percent_points", 0.0),
                period,
                dataRange,
                cache,
                engine,
                parameters,
                candidate,
                model,
                originalModel,
                retestModel,
                capital,
                compound
        );
        showTextDialog("TOP10 원본 ↔ 재백테스트 비교", message);
    }

    private void appendSettingGroup(StringBuilder sb, String title, JSONObject values, String[][] fields) {
        sb.append("【").append(title).append("】\n");
        for (String[] field : fields) {
            if (!values.has(field[1]) || values.isNull(field[1])) continue;
            Object value = values.opt(field[1]);
            if (value instanceof Boolean) value = (Boolean) value ? "사용" : "미사용";
            sb.append(field[0]).append(": ").append(value).append('\n');
        }
        sb.append('\n');
    }



    private void showMarketRegimePerformance() {
        if (lastSummary == null) {
            toast("백테스트를 먼저 실행하세요.");
            return;
        }
        JSONObject suite = lastSummary.optJSONObject("validation_suite");
        JSONObject report = suite == null ? null : suite.optJSONObject("market_regimes");
        JSONArray rows = report == null ? null : report.optJSONArray("regimes");
        if (rows == null) {
            showTextDialog("시장 국면별 성과", "시장 국면 분석 자료가 없습니다.");
            return;
        }
        StringBuilder sb = new StringBuilder();
        sb.append("자동 전환  ").append(report.optBoolean("adaptive_regime_enabled") ? "사용됨" : "사용 안 됨")
                .append("\n판정 기준  과거 ").append(report.optInt("lookback_bars", 288)).append("개 마감봉")
                .append("\n\n");
        for (int i = 0; i < rows.length(); i++) {
            JSONObject row = rows.optJSONObject(i);
            if (row == null) continue;
            sb.append("【").append(row.optString("regime")).append("】  ")
                    .append(row.optInt("trades")).append("회 · 승률 ")
                    .append(String.format(Locale.KOREA, "%.1f%%", row.optDouble("win_rate")))
                    .append(" · 손익 ").append(String.format(Locale.KOREA, "%+.2f USDT", row.optDouble("pnl")))
                    .append('\n');
        }
        sb.append("\n전환 규칙\n")
                .append("상승장 → 롱만\n")
                .append("하락장 → 숏만\n")
                .append("횡보장 → 롱·숏\n")
                .append("고변동성 → 진입 50%, 추가진입 제한\n")
                .append("저변동성 → 정상 진입\n\n")
                .append("현재 봉까지 마감된 데이터만 사용하고 다음 신호부터 적용합니다.");
        showTextDialog("🌦 시장 국면별 성과", sb.toString());
    }

    private void showValidationSuite() {
        if (lastSummary == null) {
            toast("백테스트를 먼저 실행하세요.");
            return;
        }
        JSONObject suite = lastSummary.optJSONObject("validation_suite");
        if (suite == null) {
            showTextDialog("다중 검증", "이 결과는 다중 검증 기능 추가 전 결과입니다.");
            return;
        }
        JSONObject gate = suite.optJSONObject("safety_gate");
        StringBuilder sb = new StringBuilder();
        sb.append("【실전 안전게이트】\n")
                .append(gate == null ? "UNKNOWN" : gate.optString("status", "UNKNOWN"))
                .append("\n실전 적용  ").append(gate != null && gate.optBoolean("paper_live_allowed") ? "허용" : "차단")
                .append("\n차단 원인  ").append(gate == null ? "—" : gate.optJSONArray("blocking_reasons"))
                .append("\n경고  ").append(gate == null ? "—" : gate.optJSONArray("warnings"))
                .append("\n\n【검증별 상태】\n");
        String[][] tests = {
                {"data_quality", "데이터 품질"}, {"lookahead_audit", "미래 데이터 방지"},
                {"train_test_split", "학습 70 / 검증 30"}, {"walk_forward", "워크포워드"},
                {"cost_stress", "비용 스트레스"}, {"monte_carlo", "몬테카를로"},
                {"market_regimes", "시장 국면"}
        };
        for (String[] test : tests) {
            JSONObject result = suite.optJSONObject(test[0]);
            sb.append(result == null ? "—" : result.optString("status", "—"))
                    .append("  ").append(test[1]).append('\n');
        }
        JSONObject data = suite.optJSONObject("data_quality");
        if (data != null) sb.append("\n4개 거래소 공통 봉 비율  ")
                .append(String.format(Locale.KOREA, "%.3f%%", data.optDouble("common_bar_ratio_percent")));
        JSONObject mc = suite.optJSONObject("monte_carlo");
        if (mc != null) sb.append("\n몬테카를로 MDD 95%  ")
                .append(String.format(Locale.KOREA, "%.2f%%", mc.optDouble("mdd_p95_percent")))
                .append("\n파산 확률  ").append(String.format(Locale.KOREA, "%.3f%%", mc.optDouble("ruin_probability_percent")));
        JSONObject wf = suite.optJSONObject("walk_forward");
        if (wf != null) sb.append("\n워크포워드 수익 구간  ")
                .append(wf.optInt("profitable_windows")).append("/").append(wf.optInt("total_windows"));
        showTextDialog("🛡 다중 검증 결과", sb.toString());
    }

    private void showRecentResultComparison() {
        String[] modes = {
                "수익률 높은 순", "최신 결과 순", "MDD 낮은 순",
                "신뢰도 높은 순", "현재 종목만 · 수익률 순"
        };
        new AlertDialog.Builder(this)
                .setTitle("저장 결과 찾기")
                .setItems(modes, (dialog, which) -> {
                    String mode = which == 1 ? "recent" : (which == 2 ? "mdd" : (which == 3 ? "quality" : "return"));
                    String symbolFilter = which == 4 ? symbolInput.getText().toString().trim() : "";
                    loadResultFinder(mode, symbolFilter, modes[which]);
                })
                .setNegativeButton("닫기", null)
                .show();
    }

    private void loadResultFinder(String sortMode, String symbolFilter, String title) {
        statusText.setText("저장 결과 검색 중");
        executor.execute(() -> {
            try {
                File output = new File(getFilesDir(), "UniversalTradingBotCache");
                PyObject bridge = Python.getInstance().getModule("mobile_bridge");
                JSONObject response = new JSONObject(
                        bridge.callAttr("find_saved_results", output.getAbsolutePath(), sortMode, symbolFilter, 50).toString()
                );
                JSONArray items = response.optJSONArray("items");
                if (items == null || items.length() == 0) {
                    main.post(() -> toast("조건에 맞는 저장 결과가 없습니다."));
                    return;
                }
                String[] labels = new String[items.length()];
                for (int i = 0; i < items.length(); i++) {
                    JSONObject row = items.optJSONObject(i);
                    labels[i] = String.format(
                            Locale.KOREA,
                            "%d. %s · %s~%s\n수익률 %.2f%% · MDD %.2f%% · PF %.2f · 거래 %d\n신뢰도 %s · 안전 %s%s",
                            i + 1,
                            row.optJSONObject("summary") == null ? row.optString("label")
                                    : row.optJSONObject("summary").optString("symbol", row.optString("label")),
                            row.optJSONObject("summary") == null ? "—" : row.optJSONObject("summary").optString("requested_start", "—"),
                            row.optJSONObject("summary") == null ? "—" : row.optJSONObject("summary").optString("requested_end", "—"),
                            row.optDouble("return_percent"), row.optDouble("max_drawdown_percent"),
                            row.optDouble("profit_factor"), row.optInt("trades"),
                            row.optString("quality_grade", "—"), row.optString("safety_status", "—"),
                            row.optBoolean("parameters_available") ? " · 재검증 가능" : ""
                    );
                }
                main.post(() -> {
                    statusText.setText("저장 결과 " + items.length() + "개");
                    new AlertDialog.Builder(this)
                            .setTitle(title + " · " + items.length() + "개")
                            .setItems(labels, (dialog, which) -> {
                                JSONObject selected = items.optJSONObject(which);
                                if (selected != null) {
                                    pinSavedResult(selected);
                                    showSavedResultActions(selected);
                                }
                            })
                            .setNegativeButton("닫기", null)
                            .show();
                });
            } catch (Exception e) {
                main.post(() -> {
                    appendFullLog("\nRESULT FINDER ERROR\n" + stackMessage(e) + "\n");
                    statusText.setText("결과 검색 오류");
                });
            }
        });
    }

    private void showSavedResultActions(JSONObject item) {
        JSONObject summary = item.optJSONObject("summary");
        String title = summary == null ? item.optString("label", "저장 결과")
                : String.format(Locale.KOREA, "%.2f%% · MDD %.2f%%",
                summary.optDouble("return_percent"), summary.optDouble("max_drawdown_percent"));
        String[] actions = {
                "📌 이 결과 불러오기",
                "📊 성과·검증 조건 전체 보기",
                "⚙ 저장된 전략 수치 전체 보기",
                "▶ 전략 수치 + 현재 자산설정으로 재검증",
                "🏆 이 결과의 TOP10 후보 보기",
                "📤 원본 JSON 공유"
        };
        new AlertDialog.Builder(this)
                .setTitle(title)
                .setItems(actions, (dialog, which) -> {
                    if (which == 0) {
                        applySavedResult(item, false);
                    } else if (which == 1) {
                        applySavedResult(item, true);
                        showResultSummary();
                    } else if (which == 2) {
                        prepareSavedResultReplay(item, false);
                    } else if (which == 3) {
                        prepareSavedResultReplay(item, true);
                    } else if (which == 4) {
                        applySavedResult(item, true);
                        showTopStrategies(false);
                    } else {
                        shareBacktestFile(item.optString("path"), "application/json", "저장 백테스트 원본 공유");
                    }
                })
                .setNeutralButton("실행 지문 복사", (dialog, which) -> {
                    String signature = item.optString("run_signature", "");
                    if (signature.isEmpty() && summary != null) {
                        JSONObject repro = summary.optJSONObject("reproducibility");
                        signature = repro == null ? "" : repro.optString("run_signature", "");
                    }
                    ClipboardManager clipboard = (ClipboardManager) getSystemService(CLIPBOARD_SERVICE);
                    clipboard.setPrimaryClip(ClipData.newPlainText("백테스트 실행 지문", signature));
                    toast(signature.isEmpty() ? "이전 결과라 실행 지문이 없습니다." : "실행 지문을 복사했습니다.");
                })
                .setNegativeButton("닫기", null)
                .show();
    }

    private void prepareSavedResultReplay(JSONObject item, boolean runNow) {
        String path = item.optString("path", "");
        statusText.setText(runNow ? "재검증 수치 준비 중" : "전략 수치 불러오는 중");
        executor.execute(() -> {
            try {
                PyObject bridge = Python.getInstance().getModule("mobile_bridge");
                JSONObject replay = new JSONObject(
                        bridge.callAttr("saved_result_replay_payload", path).toString()
                );
                JSONObject parameters = replay.getJSONObject("parameters");
                JSONObject row = new JSONObject();
                row.put("parameters", parameters);
                row.put("effective_parameters", parameters);
                row.put("original_result", replay.optJSONObject("original_result"));
                row.put("source_context", replay.optJSONObject("source_context"));
                main.post(() -> {
                    applySavedResult(item, true);
                    selectedStrategyParameters = parameters;
                    selectedStrategyRow = row;
                    syncMainControlsFromStrategy(parameters);
                    selectedStrategyText.setText(
                            "저장 결과 수치 선택됨 · " + replay.optString("parameter_source", "대표 결과")
                                    + "\n" + item.optString("label", path)
                    );
                    selectedStrategyText.setTextColor(ACCENT);
                    pinSavedResult(item);
                    persistSelectedStrategy();
                    statusText.setText("동일 수치 재검증 준비 완료");
                    if (runNow) {
                        String period = startInput.getText().toString().trim() + " ~ "
                                + endInput.getText().toString().trim();
                        String moneyMode = sizingModeInput.getText().toString().trim();
                        String capital = initialCapitalInput.getText().toString().trim();
                        new AlertDialog.Builder(this)
                                .setTitle("현재 자산설정으로 재검증")
                                .setMessage("저장된 전략 수치·기간·체결 모델은 원본 그대로 사용하고, 현재 화면의 초기자산과 복리 설정만 적용합니다.\n\n기간: "
                                        + period + "\n초기자산: " + capital + " USDT\n계산 방식: " + moneyMode
                                        + "\n\n복리식이면 매 진입마다 현재 순자산으로 주문 규모를 다시 계산합니다."
                                        + "\n장시간 걸릴 수 있으며 실행 중에도 앱을 닫지 마세요.")
                                .setPositiveButton("재검증 시작", (dialog, which) -> startBacktest(parameters))
                                .setNegativeButton("취소", null)
                                .show();
                    } else {
                        showSelectedStrategyDetails();
                    }
                });
            } catch (Exception e) {
                main.post(() -> {
                    appendFullLog("\nSAVED REPLAY ERROR\n" + stackMessage(e) + "\n");
                    statusText.setText("재검증 수치 복원 오류");
                    showTextDialog("재검증 수치 복원 오류", stackMessage(e));
                });
            }
        });
    }

    private void persistSelectedStrategy() {
        if (selectedStrategyParameters == null || selectedStrategyRow == null) return;
        getSharedPreferences("universal_bot", MODE_PRIVATE).edit()
                .putString("pinned_strategy_parameters", selectedStrategyParameters.toString())
                .putString("pinned_strategy_row", selectedStrategyRow.toString())
                .putString("pinned_strategy_label", selectedStrategyText.getText().toString())
                .apply();
    }

    private void pinSavedResult(JSONObject item) {
        if (item == null) return;
        String label = item.optString("label", "저장 결과");
        JSONObject summary = item.optJSONObject("summary");
        String display = label;
        if (summary != null) {
            display = String.format(
                    Locale.KOREA,
                    "📌 고정됨 · %s\n수익률 %.2f%% · MDD %.2f%% · PF %.2f",
                    label,
                    summary.optDouble("return_percent"),
                    summary.optDouble("max_drawdown_percent"),
                    summary.optDouble("profit_factor")
            );
        }
        getSharedPreferences("universal_bot", MODE_PRIVATE).edit()
                .putString("pinned_result_item", item.toString())
                .putString("pinned_result_label", display)
                .apply();
        if (pinnedResultText != null) {
            pinnedResultText.setText(display);
            pinnedResultText.setTextColor(ACCENT);
        }
    }

    private void reopenPinnedResult() {
        String raw = getSharedPreferences("universal_bot", MODE_PRIVATE)
                .getString("pinned_result_item", "");
        if (raw == null || raw.isEmpty()) {
            toast("먼저 저장 결과 찾기에서 결과를 선택하세요.");
            return;
        }
        try {
            showSavedResultActions(new JSONObject(raw));
        } catch (Exception e) {
            toast("고정된 결과를 읽지 못했습니다. 다시 선택하세요.");
        }
    }

    private void restorePinnedSelections() {
        SharedPreferences prefs = getSharedPreferences("universal_bot", MODE_PRIVATE);
        String parameters = prefs.getString("pinned_strategy_parameters", "");
        String row = prefs.getString("pinned_strategy_row", "");
        String strategyLabel = prefs.getString("pinned_strategy_label", "");
        try {
            if (parameters != null && !parameters.isEmpty() && row != null && !row.isEmpty()) {
                JSONObject restoredRow = new JSONObject(row);
                JSONObject sourceContext = restoredRow.optJSONObject("source_context");
                JSONObject sourceEngine = sourceContext == null ? null : sourceContext.optJSONObject("engine");
                boolean importedJson = restoredRow.optBoolean("imported_json", false);
                boolean manuallyEdited = restoredRow.optBoolean("manually_edited", false);
                if (!importedJson && !manuallyEdited
                        && (sourceEngine == null || !ENGINE_SCHEMA.equals(sourceEngine.optString("schema", "")))) {
                    selectedStrategyParameters = null;
                    selectedStrategyRow = null;
                    selectedStrategyText.setText(
                            "이전 엔진의 저장 전략은 안전을 위해 해제되었습니다. 현재 엔진으로 최적화 후 TOP10을 다시 선택하세요."
                    );
                    selectedStrategyText.setTextColor(Color.rgb(251, 191, 36));
                } else {
                    selectedStrategyParameters = new JSONObject(parameters);
                    selectedStrategyRow = restoredRow;
                    selectedStrategyText.setText(
                            strategyLabel == null || strategyLabel.isEmpty()
                                    ? "저장된 전략 수치 복원 완료" : strategyLabel
                    );
                    selectedStrategyText.setTextColor(ACCENT);
                }
            }
        } catch (Exception ignored) {
            prefs.edit().remove("pinned_strategy_parameters")
                    .remove("pinned_strategy_row").remove("pinned_strategy_label").apply();
        }
        String pinnedLabel = prefs.getString("pinned_result_label", "");
        if (pinnedResultText != null && pinnedLabel != null && !pinnedLabel.isEmpty()) {
            pinnedResultText.setText(pinnedLabel);
            pinnedResultText.setTextColor(ACCENT);
        }
    }

    private void showMonthlyPerformance() {
        if (lastSummary == null) {
            toast("백테스트를 먼저 실행하세요.");
            return;
        }
        JSONArray months = lastSummary.optJSONArray("monthly_performance");
        if (months == null || months.length() == 0) {
            showTextDialog("월별 성과", "월별 거래 자료가 없습니다.");
            return;
        }
        StringBuilder sb = new StringBuilder();
        double best = -Double.MAX_VALUE;
        double worst = Double.MAX_VALUE;
        String bestMonth = "—";
        String worstMonth = "—";
        for (int i = 0; i < months.length(); i++) {
            JSONObject row = months.optJSONObject(i);
            if (row == null) continue;
            double pnl = row.optDouble("pnl", 0.0);
            if (pnl > best) { best = pnl; bestMonth = row.optString("month"); }
            if (pnl < worst) { worst = pnl; worstMonth = row.optString("month"); }
            sb.append(row.optString("month")).append("  ")
                    .append(String.format(Locale.KOREA, "%+.2f USDT", pnl))
                    .append(" · ").append(row.optInt("trades")).append("회")
                    .append(" · 승률 ").append(String.format(Locale.KOREA, "%.1f%%", row.optDouble("win_rate")))
                    .append('\n');
        }
        sb.insert(0, "최고 " + bestMonth + "  " + String.format(Locale.KOREA, "%+.2f USDT", best)
                + "\n최저 " + worstMonth + "  " + String.format(Locale.KOREA, "%+.2f USDT", worst) + "\n\n");
        showTextDialog("월별 성과·손실 구간", sb.toString());
    }

    private void showEngineStatus() {
        executor.execute(() -> {
            try {
                PyObject bridge = Python.getInstance().getModule("mobile_bridge");
                JSONObject response = new JSONObject(bridge.callAttr("engine_status").toString());
                JSONObject engine = response.optJSONObject("engine");
                JSONObject cache = response.optJSONObject("feature_cache");
                String code = engine == null ? "—" : engine.optString("code_sha256", "—");
                if (code.length() > 16) code = code.substring(0, 16) + "…";
                String message = String.format(
                        Locale.KOREA,
                        "엔진  %s %s\n방식  %s\n스키마  %s\n코드 지문  %s\n의존성  NumPy + Pandas만 사용\n\n재현 잠금\n• 엔진 코드\n• 캐시 SHA256\n• 요청 기간·실제 봉 수\n• 전체 전략 수치\n• TOP10 후보 서명\n\n가속 상태\n• 재사용 지표 %d개\n• 캐시 적중 %d회 / 계산 %d회\n• 상세 거래·차트는 최종 결과에서만 생성",
                        engine == null ? "Universal Vector Engine" : engine.optString("name", "Universal Vector Engine"),
                        engine == null ? "5" : engine.optString("version", "5"),
                        engine == null ? "벡터 지표 + 이벤트 체결" : engine.optString("execution", "벡터 지표 + 이벤트 체결"),
                        engine == null ? "—" : engine.optString("schema", "—"),
                        code,
                        cache == null ? 0 : cache.optInt("features", 0),
                        cache == null ? 0 : cache.optInt("hits", 0),
                        cache == null ? 0 : cache.optInt("misses", 0)
                );
                main.post(() -> showTextDialog("⚡ 백테스트 엔진 상태", message));
            } catch (Exception e) {
                main.post(() -> showTextDialog("엔진 상태 오류", stackMessage(e)));
            }
        });
    }

    private void showReproducibility() {
        if (lastSummary == null) {
            toast("백테스트를 먼저 실행하세요.");
            return;
        }
        JSONObject repro = lastSummary.optJSONObject("reproducibility");
        if (repro == null) {
            showTextDialog("결과 재현 정보", "이 결과는 이전 버전에서 생성되어 실행 지문이 없습니다.");
            return;
        }
        String signature = repro.optString("run_signature", "—");
        JSONObject engine = repro.optJSONObject("engine");
        StringBuilder sb = new StringBuilder();
        sb.append("실행 지문\n").append(signature).append("\n\n")
                .append("엔진  ").append(engine == null ? "이전 엔진" : engine.optString("name", "—"))
                .append(" ").append(engine == null ? "" : engine.optString("version", "")).append('\n')
                .append("엔진 코드  ").append(engine == null ? "—" : engine.optString("code_sha256", "—")).append('\n')
                .append("종목  ").append(repro.optString("symbol")).append('\n')
                .append("타임프레임  ").append(repro.optString("timeframe")).append('\n')
                .append("요청 기간  ").append(repro.optString("requested_start")).append(" ~ ")
                .append(repro.optString("requested_end")).append('\n')
                .append("실제 데이터  ").append(repro.optString("data_start")).append(" ~ ")
                .append(repro.optString("data_end")).append('\n')
                .append("체결 모델  ").append(repro.optString("execution_model")).append('\n')
                .append("수수료/슬리피지  ").append(repro.opt("fee_percent_per_side")).append("% / ")
                .append(repro.opt("slippage_percent_per_side")).append("%\n")
                .append("캐시 SHA256  ").append(repro.optString("cache_sha256")).append('\n')
                .append("전체 설정 SHA256  ").append(repro.optString("effective_parameters_sha256", "—")).append("\n\n")
                .append("엔진·캐시·기간·전체 설정 지문이 모두 같아야 동일 조건 비교입니다.");
        showTextDialog("🔒 결과 재현 잠금", sb.toString());
    }

    private void exportAndShareAnalysisBundle() {
        if (lastResultPath == null || lastResultPath.isEmpty()) {
            toast("먼저 완료된 결과를 불러오세요.");
            return;
        }
        statusText.setText("전체 분석 ZIP 생성 중");
        executor.execute(() -> {
            try {
                PyObject bridge = Python.getInstance().getModule("mobile_bridge");
                JSONObject exported = new JSONObject(bridge.callAttr("export_analysis_bundle", lastResultPath).toString());
                String path = exported.getString("path");
                main.post(() -> {
                    statusText.setText("전체 분석 ZIP 준비 완료");
                    shareBacktestFile(path, "application/zip", "백테스트 전체 분석 ZIP 공유");
                });
            } catch (Exception e) {
                main.post(() -> {
                    appendFullLog("\nANALYSIS BUNDLE ERROR\n" + stackMessage(e) + "\n");
                    statusText.setText("전체 분석 ZIP 오류");
                });
            }
        });
    }

    private void showResultSummary() {
        if (lastSummary == null) {
            toast("백테스트를 먼저 실행하세요.");
            return;
        }
        String execution = lastSummary.optString("execution_model", "next_open");
        String executionLabel = "next_open".equals(execution)
                ? "현실형 · 다음 봉 시가"
                : "기존형 · 신호 봉 종가";
        String[] sizingKeys = {"sizing_mode", "compounding_enabled"};
        boolean compounding = lastSummary.optBoolean(sizingKeys[1],
                "compound_current_equity".equals(lastSummary.optString(sizingKeys[0], "")));
        String sizing = lastSummary.optString(sizingKeys[0],
                compounding ? "compound_current_equity" : "fixed_initial_equity");
        String sizingLabel = compounding ? "복리식 · 현재 순자산 기준" : "고정식 · 초기자산 기준";
        double initialCapital = lastSummary.optDouble("initial_capital", 1000.0);
        double finalEquity = lastSummary.optDouble("final_equity",
                initialCapital + lastSummary.optDouble("pnl", 0.0));
        JSONObject engineInfo = lastSummary.optJSONObject("engine");
        String engineLabel = engineInfo == null
                ? "이전 엔진"
                : engineInfo.optString("name", "Universal Vector Engine") + " "
                + engineInfo.optString("version", "");
        StringBuilder sb = new StringBuilder();
        sb.append("【성과】\n")
                .append("총 수익률  ").append(formatMetric(lastSummary, "return_percent", "%")).append('\n')
                .append("순손익  ").append(formatMetric(lastSummary, "pnl", " USDT")).append('\n')
                .append("총손익  ").append(formatMetric(lastSummary, "gross_pnl", " USDT")).append('\n')
                .append("예상 비용  ").append(formatMetric(lastSummary, "estimated_costs", " USDT")).append("\n\n")
                .append("【위험과 품질】\n")
                .append("최대 낙폭  ").append(formatMetric(lastSummary, "max_drawdown_percent", "%")).append('\n')
                .append("Profit Factor  ").append(formatMetric(lastSummary, "profit_factor", "")).append('\n')
                .append("승률  ").append(formatMetric(lastSummary, "win_rate", "%")).append('\n')
                .append("거래  ").append(lastSummary.optInt("trades", 0))
                .append("회 · 승리 ").append(lastSummary.optInt("wins", 0)).append("회\n\n")
                .append("【검증 조건】\n")
                .append("종목  ").append(lastSummary.optString("symbol", "—")).append('\n')
                .append("데이터  ").append(lastSummary.optString("data_start", "—"))
                .append(" ~ ").append(lastSummary.optString("data_end", "—")).append('\n')
                .append("봉 수  ").append(lastSummary.optInt("bars", 0)).append('\n')
                .append("엔진  ").append(engineLabel).append('\n')
                .append("체결 모델  ").append(executionLabel).append('\n')
                .append("초기자산  ").append(String.format(Locale.KOREA, "%,.2f USDT", initialCapital)).append('\n')
                .append("자산 계산  ").append(sizingLabel)
                .append(" · 복리 ").append(compounding ? "사용" : "미사용").append('\n')
                .append("최종자산  ").append(String.format(Locale.KOREA, "%,.2f USDT", finalEquity)).append('\n')
                .append("데이터 지문  ").append(lastSummary.optString("cache_sha256", "—"));
        JSONObject quality = lastSummary.optJSONObject("quality");
        if (quality != null) {
            sb.append("\n\n【결과 신뢰도】\n")
                    .append("등급 ").append(quality.optString("grade", "—"))
                    .append(" · ").append(quality.optInt("score", 0)).append("/100");
            JSONArray warnings = quality.optJSONArray("warnings");
            if (warnings != null) for (int i = 0; i < warnings.length(); i++) {
                sb.append("\n• ").append(warnings.optString(i));
            }
        }
        if (lastSummary.has("reproduction_comparison")) {
            sb.append("\n\n【TOP10 재검증 일치 확인】\n")
                    .append(lastSummary.opt("reproduction_comparison"));
        }
        showTextDialog("성과 요약 · 재현 조건", sb.toString());
    }

    private TextView tradeTableCell(String value, boolean header) {
        TextView cell = text(value, header ? 11 : 10, header ? TEXT : MUTED, header);
        cell.setGravity(Gravity.CENTER_VERTICAL);
        cell.setPadding(dp(9), dp(8), dp(9), dp(8));
        cell.setSingleLine(true);
        return cell;
    }

    private void showTradeHistory() {
        if (lastSummary == null) {
            toast("백테스트를 먼저 실행하세요.");
            return;
        }
        JSONArray trades = lastSummary.optJSONArray("trades_log");
        if (trades == null || trades.length() == 0) {
            showTextDialog("전체 거래내역", "거래 기록이 없습니다.");
            return;
        }

        TableLayout table = new TableLayout(this);
        table.setStretchAllColumns(false);
        String[] headers = {"#", "방향", "진입 시각", "진입가", "청산 시각", "청산가", "수량", "순손익", "수익률", "사유"};
        TableRow header = new TableRow(this);
        header.setBackgroundColor(Color.rgb(30, 41, 59));
        for (String label : headers) header.addView(tradeTableCell(label, true));
        table.addView(header);

        for (int i = 0; i < trades.length(); i++) {
            JSONObject t = trades.optJSONObject(i);
            if (t == null) continue;
            TableRow row = new TableRow(this);
            if (i % 2 == 1) row.setBackgroundColor(Color.rgb(14, 23, 39));
            String[] values = {
                    String.valueOf(t.optInt("trade", i + 1)),
                    t.optString("side", "-"),
                    t.optString("entry_time", "-"),
                    String.format(Locale.US, "%.2f", t.optDouble("avg_entry_price", t.optDouble("entry_price"))),
                    t.optString("exit_time", "-"),
                    String.format(Locale.US, "%.2f", t.optDouble("exit_price")),
                    String.format(Locale.US, "%.6f", t.optDouble("qty")),
                    String.format(Locale.US, "%+.4f", t.optDouble("pnl")),
                    String.format(Locale.US, "%+.3f%%", t.optDouble("pnl_percent")),
                    t.optString("reason", "-")
            };
            for (String value : values) row.addView(tradeTableCell(value, false));
            table.addView(row);
        }

        HorizontalScrollView horizontal = new HorizontalScrollView(this);
        horizontal.addView(table);
        ScrollView vertical = new ScrollView(this);
        vertical.setFillViewport(true);
        vertical.addView(horizontal);
        new AlertDialog.Builder(this)
                .setTitle("거래 기록 표 · " + trades.length() + "건")
                .setMessage("좌우로 밀어 모든 열을 확인할 수 있습니다.")
                .setView(vertical)
                .setNegativeButton("닫기", null)
                .show();
    }

    private void openServerTradingChart() {
        String host = hostInput == null ? "" : hostInput.getText().toString().trim();
        if (host.isEmpty()) host = "34.132.172.40";
        if (!host.startsWith("http://") && !host.startsWith("https://")) host = "http://" + host;
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(host)));
        } catch (Exception e) {
            showTextDialog(
                    "서버 캔들 차트 확인",
                    "브라우저에서 " + host + " 을 열고 BTC/USDT:USDT · 15m · BACKTEST를 선택하세요. "
                            + "캔들과 LONG/SHORT 진입, TP/SL/청산 표식을 함께 확인할 수 있습니다."
            );
        }
    }

    private void showBacktestChart() {
        if (lastSummary == null) {
            toast("백테스트를 먼저 실행하세요.");
            return;
        }
        BacktestChartView chart = new BacktestChartView(this);
        chart.setData(
                lastSummary.optJSONArray("equity_curve"),
                lastSummary.optJSONArray("trades_log")
        );
        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.addView(chart, new ScrollView.LayoutParams(
                ScrollView.LayoutParams.MATCH_PARENT,
                dp(420)
        ));
        new AlertDialog.Builder(this)
                .setTitle("순자산 차트 · 진입/청산 표시")
                .setView(scroll)
                .setNegativeButton("닫기", null)
                .show();
    }

    private void showTextDialog(String title, String value) {
        TextView body = text(value, 11, TEXT, false);
        body.setTypeface(Typeface.MONOSPACE);
        body.setTextIsSelectable(true);
        body.setPadding(dp(14), dp(12), dp(14), dp(12));
        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setMinimumHeight(dp(420));
        scroll.addView(body);
        new AlertDialog.Builder(this)
                .setTitle(title)
                .setView(scroll)
                .setPositiveButton("전체 복사", (dialog, which) -> {
                    ClipboardManager clipboard = (ClipboardManager) getSystemService(CLIPBOARD_SERVICE);
                    clipboard.setPrimaryClip(ClipData.newPlainText(title, value));
                    toast("전체 로그를 복사했습니다.");
                })
                .setNegativeButton("닫기", null)
                .show();
    }

    private void showDeepBacktestReport() {
        if (lastSummary == null) {
            toast("백테스트를 먼저 실행하세요.");
            return;
        }
        Intent intent = new Intent(this, DeepBacktestReportActivity.class);
        intent.putExtra("summary_json", lastSummary.toString());
        startActivity(intent);
    }

    private void enableResultActions(boolean enabled) {
        Button[] buttons = {resultSummaryButton, tradeHistoryButton, chartButton, deepBacktestButton};
        for (Button button : buttons) {
            if (button == null) continue;
            button.setEnabled(enabled);
            button.setAlpha(enabled ? 1f : 0.45f);
        }
    }

    private void updateMetrics(JSONObject summary) {
        tradesValue.setText(String.valueOf(summary.optInt("trades", 0)));
        JSONObject quality = summary.optJSONObject("quality");
        JSONObject gate = summary.optJSONObject("validation_suite") == null ? null
                : summary.optJSONObject("validation_suite").optJSONObject("safety_gate");
        qualityValue.setText(quality == null ? "—" : quality.optString("grade", "—") + " · " + quality.optInt("score", 0)
                + (gate == null ? "" : "\n" + gate.optString("status", "")));
        if (quality != null) {
            int score = quality.optInt("score", 0);
            qualityValue.setTextColor(score >= 85 ? Color.rgb(34, 197, 94)
                    : (score >= 70 ? Color.rgb(250, 204, 21) : Color.rgb(239, 68, 68)));
        }
        winRateValue.setText(formatMetric(summary, "win_rate", "%"));
        pfValue.setText(formatMetric(summary, "profit_factor", ""));
        returnValue.setText(formatMetric(summary, "return_percent", "%"));
        mddValue.setText(formatMetric(summary, "max_drawdown_percent", "%"));
        double result = summary.optDouble("return_percent", 0.0);
        double drawdown = summary.optDouble("max_drawdown_percent", 0.0);
        returnValue.setTextColor(result >= 0 ? Color.rgb(34, 197, 94) : Color.rgb(239, 68, 68));
        mddValue.setTextColor(drawdown <= 40.0 ? Color.rgb(250, 204, 21) : Color.rgb(239, 68, 68));
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

    private View binaryChoiceRow(
            String title,
            AutoCompleteTextView target,
            String[] labels,
            String[] values
    ) {
        LinearLayout wrap = new LinearLayout(this);
        wrap.setOrientation(LinearLayout.VERTICAL);
        wrap.addView(text(title, 12, TEXT, true));

        TextView current = text("현재 선택: " + target.getText(), 11, ACCENT, true);
        wrap.addView(current, marginTop(5));

        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        Button[] buttons = new Button[Math.min(labels.length, values.length)];
        Runnable refresh = () -> {
            String selected = target.getText().toString();
            current.setText("현재 선택: " + selected);
            for (int i = 0; i < buttons.length; i++) {
                boolean active = values[i].equals(selected);
                buttons[i].setBackground(rounded(
                        active ? PRIMARY : Color.rgb(30, 41, 59),
                        10,
                        active ? ACCENT : BORDER
                ));
                buttons[i].setTextColor(Color.WHITE);
            }
        };
        for (int i = 0; i < buttons.length; i++) {
            final String value = values[i];
            Button button = smallButton(labels[i], v -> {
                target.setText(value, false);
                refresh.run();
            });
            buttons[i] = button;
            LinearLayout.LayoutParams params =
                    new LinearLayout.LayoutParams(0, dp(46), 1f);
            params.setMargins(i == 0 ? 0 : dp(6), 0, 0, 0);
            row.addView(button, params);
        }
        wrap.addView(row, marginTop(6));
        target.addTextChangedListener(new TextWatcher() {
            @Override public void beforeTextChanged(CharSequence s, int start, int count, int after) {}
            @Override public void onTextChanged(CharSequence s, int start, int before, int count) {
                refresh.run();
            }
            @Override public void afterTextChanged(Editable s) {}
        });
        refresh.run();
        return wrap;
    }

    private View quickChoiceRow(
            String title,
            AutoCompleteTextView target,
            String[] labels,
            String[] values
    ) {
        LinearLayout wrap = new LinearLayout(this);
        wrap.setOrientation(LinearLayout.VERTICAL);
        wrap.addView(text(title + " · 버튼으로 바로 선택", 11, MUTED, true));

        HorizontalScrollView scroll = new HorizontalScrollView(this);
        scroll.setHorizontalScrollBarEnabled(false);
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        for (int i = 0; i < labels.length && i < values.length; i++) {
            final String value = values[i];
            Button button = smallButton(labels[i], v -> target.setText(value, false));
            LinearLayout.LayoutParams params =
                    new LinearLayout.LayoutParams(dp(76), dp(42));
            params.setMargins(i == 0 ? 0 : dp(6), 0, 0, 0);
            row.addView(button, params);
        }
        scroll.addView(row);
        wrap.addView(scroll, marginTop(4));
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
        StringBuilder details = new StringBuilder();
        Throwable current = e;
        int depth = 0;
        while (current != null && depth < 10) {
            if (depth > 0) details.append("\n원인 ").append(depth).append(": ");
            details.append(current.getClass().getName());
            String message = current.getMessage();
            if (message != null && !message.trim().isEmpty()) {
                details.append(": ").append(message.trim());
            }
            current = current.getCause();
            depth++;
        }
        StringWriter trace = new StringWriter();
        e.printStackTrace(new PrintWriter(trace));
        details.append("\n\n전체 스택:\n").append(trace);
        return details.toString();
    }

    private void toast(String message) {
        Toast.makeText(this, message, Toast.LENGTH_LONG).show();
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
