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
import android.os.Build;
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

import java.io.BufferedReader;
import java.io.File;
import java.io.FileReader;
import java.io.PrintWriter;
import java.io.StringWriter;
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
    private JSONObject lastSummary;
    private JSONObject selectedStrategyParameters;
    private JSONObject selectedStrategyRow;
    private TextView selectedStrategyText;
    private TextView pinnedResultText;

    private String lastDbPath = "";
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

        TextView title = text("Universal Trading Backtester", 24, TEXT, true);
        root.addView(title);
        TextView subtitle = text("Android 폰에서 4개 거래소 캐시 생성 · 로컬 백테스트 · 서버 업로드", 13, MUTED, false);
        root.addView(subtitle, marginTop(4));

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
        backtestCard.addView(labeled("자산 계산 방식", sizingModeInput), marginTop(12));
        backtestCard.addView(quickChoiceRow(
                "계산 방식 선택",
                sizingModeInput,
                new String[]{"복리식", "고정식"},
                new String[]{"복리식", "고정식"}
        ), marginTop(8));
        backtestCard.addView(text(
                "복리식=현재 순자산 기준으로 다음 진입 규모를 재계산 · 고정식=입력한 초기자산 기준을 계속 사용",
                11, MUTED, false
        ), marginTop(7));

        executionModelInput = autocomplete(
                new String[]{"현실형 · 다음 봉 시가 체결", "기존형 · 신호 봉 종가 체결"},
                "현실형 · 다음 봉 시가 체결"
        );
        backtestCard.addView(labeled("백테스트 체결 모델", executionModelInput), marginTop(12));
        backtestCard.addView(quickChoiceRow(
                "체결 방식",
                executionModelInput,
                new String[]{"현실형(추천)", "기존형(비교)"},
                new String[]{"현실형 · 다음 봉 시가 체결", "기존형 · 신호 봉 종가 체결"}
        ), marginTop(8));
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
                new String[]{"자동 전환 사용 · 추천", "고정 전략 사용"},
                "자동 전환 사용 · 추천"
        );
        backtestCard.addView(labeled("시장 국면별 전략 자동 전환", adaptiveRegimeInput), marginTop(12));
        backtestCard.addView(quickChoiceRow(
                "국면 전략", adaptiveRegimeInput,
                new String[]{"자동 전환(추천)", "고정 전략"},
                new String[]{"자동 전환 사용 · 추천", "고정 전략 사용"}
        ), marginTop(8));
        backtestCard.addView(text(
                "과거 288개 마감봉으로 자동 판단: 상승장=롱 · 하락장=숏 · 횡보장=양방향 · 고변동성=진입 50%/추가진입 제한 · 저변동성=정상 진입",
                11, MUTED, false
        ), marginTop(7));

        precheckInput = autocomplete(
                new String[]{"사용 · 추천", "사용 안 함"},
                "사용 · 추천"
        );
        backtestCard.addView(labeled("최근 30일 빠른 사전검사", precheckInput), marginTop(12));
        backtestCard.addView(quickChoiceRow(
                "사전검사", precheckInput,
                new String[]{"사용(추천)", "사용 안 함"},
                new String[]{"사용 · 추천", "사용 안 함"}
        ), marginTop(8));
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
        backtestCard.addView(labeled("3틱룰 적용 범위", threeTickModeInput), marginTop(12));
        backtestCard.addView(quickChoiceRow(
                "3틱룰", threeTickModeInput,
                new String[]{"첫 진입만", "모든 진입"},
                new String[]{"첫 진입만 3틱룰", "모든 진입 3틱룰"}
        ), marginTop(8));

        TextView storageInfo = text("저장 위치: 앱 내부 저장소 / UniversalTradingBotCache", 12, MUTED, false);
        backtestCard.addView(storageInfo, marginTop(10));

        runButton = actionButton("▶ 백그라운드 캐시 생성 + 백테스트", PRIMARY);
        runButton.setOnClickListener(v -> runBacktest());
        backtestCard.addView(runButton, marginTop(12));

        Button topStrategiesButton = actionButton("🏆 수익률 TOP10 전략 선택", Color.rgb(30, 41, 59));
        topStrategiesButton.setOnClickListener(v -> showTopStrategies(false));
        backtestCard.addView(topStrategiesButton, marginTop(8));
        selectedStrategyText = text(
                "선택된 전략 없음 · 최적화 완료 후 TOP10에서 선택하면 모든 전략 수치가 자동 입력됩니다.",
                11, MUTED, false
        );
        backtestCard.addView(selectedStrategyText, marginTop(6));
        Button selectedDetailsButton = actionButton("📋 선택된 전략 전체 수치 보기", Color.rgb(30, 41, 59));
        selectedDetailsButton.setOnClickListener(v -> showSelectedStrategyDetails());
        backtestCard.addView(selectedDetailsButton, marginTop(8));
        Button selectedBacktestButton = actionButton("▶ 선택한 수치로 기간 재백테스트", SUCCESS);
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

        root.addView(buildMetrics(), 2, marginTop(14));

LinearLayout resultActions = panel();
root.addView(resultActions, 3, marginTop(12));
resultActions.addView(sectionTitle("성과 분석 대시보드"));

resultActions.addView(resultGroupTitle("① 핵심 분석", "요약 · 차트 · 모든 거래를 한곳에서 확인"));
resultSummaryButton = actionButton("📊 성과 요약 보기", PRIMARY);
resultSummaryButton.setOnClickListener(v -> showResultSummary());
resultActions.addView(resultSummaryButton, marginTop(6));
tradeHistoryButton = actionButton("📋 전체 거래내역 보기", Color.rgb(30, 41, 59));
tradeHistoryButton.setOnClickListener(v -> showTradeHistory());
resultActions.addView(tradeHistoryButton, marginTop(6));
chartButton = actionButton("📈 순자산·낙폭 차트 + 거래 표시", Color.rgb(30, 41, 59));
chartButton.setOnClickListener(v -> showBacktestChart());
resultActions.addView(chartButton, marginTop(6));
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

        if (fixedParameters != null && selectedStrategyRow != null) {
            JSONObject sourceContext = selectedStrategyRow.optJSONObject("source_context");
            String originalExecutionModel = sourceContext == null ? ""
                    : sourceContext.optString("execution_model", "");
            if ("next_open".equals(originalExecutionModel) || "signal_close".equals(originalExecutionModel)) {
                executionModel = originalExecutionModel;
                executionModelInput.setText(
                        "next_open".equals(executionModel)
                                ? "현실형 · 다음 봉 시가 체결"
                                : "기존형 · 신호 봉 종가 체결",
                        false
                );
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
                replayPayload.put("parameters", fixedParameters);
                replayPayload.put("execution_model_override", executionModel);
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
                + (fixedParameters == null ? "" : "TOP10에서 고른 전략 수치를 그대로 사용하며 재최적화하지 않습니다.\n")
                + "앱을 내리거나 화면을 꺼도 알림 서비스에서 계속 실행됩니다.\n");
        setBusy(true, "백그라운드 실행 중");
        setBacktestControlState("RUNNING");
        toast(fixedParameters == null ? "백그라운드 백테스트를 시작했습니다." : "선택한 수치로 기간 재백테스트를 시작했습니다.");
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
                    toast("백그라운드 백테스트가 완료됐습니다.");
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
                            "%d위 · 수익률 %.2f%% · MDD %.2f%% · 승률 %.1f%% · PF %.2f · 종합 %.1f",
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
                    toast("TOP10 후보 불러오기 실패");
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
        appendSettingGroup(sb, "시간·계산", p,
                new String[][]{{"체결 모델","backtest_execution_model"},{"주말 차단","block_weekend"},{"제외 시간","excluded_hours"},{"복리 계산","backtest_compounding_enabled"},{"레버리지","leverage"},{"수수료 편도(%)","backtest_fee_percent"},{"슬리피지 편도(%)","backtest_slippage_percent"},{"최대 총노출 배수","backtest_max_total_multiplier"}});
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
        String message = String.format(
                Locale.KOREA,
                "원래 TOP10 수익률: %.2f%%\n재백테스트 수익률: %.2f%%\n차이: %+.2f%%p\n\n원래 MDD: %.2f%%\n재백테스트 MDD: %.2f%%\n차이: %+.2f%%p\n\n요청 기간: %s\n캐시 데이터: %s\n체결 모델: %s\n  원본: %s\n  재검증: %s\n초기자산: %s\n복리 설정: %s\n\n전략 재현은 기간·캐시·체결 모델이 같아야 합니다. 초기자산이나 복리 설정을 바꾸면 수익 금액과 수익률 경로가 달라질 수 있습니다.",
                comparison.optDouble("original_return_percent", 0.0),
                comparison.optDouble("retest_return_percent", 0.0),
                comparison.optDouble("return_difference_percent_points", 0.0),
                comparison.optDouble("original_mdd_percent", 0.0),
                comparison.optDouble("retest_mdd_percent", 0.0),
                comparison.optDouble("mdd_difference_percent_points", 0.0),
                period,
                cache,
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
                    toast("이 결과에서 전략 수치를 복원하지 못했습니다.");
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
                selectedStrategyParameters = new JSONObject(parameters);
                selectedStrategyRow = new JSONObject(row);
                selectedStrategyText.setText(
                        strategyLabel == null || strategyLabel.isEmpty()
                                ? "저장된 전략 수치 복원 완료" : strategyLabel
                );
                selectedStrategyText.setTextColor(ACCENT);
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
        StringBuilder sb = new StringBuilder();
        sb.append("실행 지문\n").append(signature).append("\n\n")
                .append("종목  ").append(repro.optString("symbol")).append('\n')
                .append("타임프레임  ").append(repro.optString("timeframe")).append('\n')
                .append("요청 기간  ").append(repro.optString("requested_start")).append(" ~ ")
                .append(repro.optString("requested_end")).append('\n')
                .append("실제 데이터  ").append(repro.optString("data_start")).append(" ~ ")
                .append(repro.optString("data_end")).append('\n')
                .append("체결 모델  ").append(repro.optString("execution_model")).append('\n')
                .append("수수료/슬리피지  ").append(repro.opt("fee_percent_per_side")).append("% / ")
                .append(repro.opt("slippage_percent_per_side")).append("%\n")
                .append("캐시 SHA256  ").append(repro.optString("cache_sha256")).append("\n\n")
                .append("같은 실행 지문이어야 동일 조건 비교입니다.");
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
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < trades.length(); i++) {
            JSONObject t = trades.optJSONObject(i);
            if (t == null) continue;
            sb.append("#").append(t.optInt("trade", i + 1))
                    .append(" · ").append(t.optString("side"))
                    .append(" · ").append(t.optString("reason"))
                    .append("\n진입 ").append(t.optString("entry_time"))
                    .append(" @ ").append(t.optDouble("avg_entry_price", t.optDouble("entry_price")))
                    .append("\n청산 ").append(t.optString("exit_time"))
                    .append(" @ ").append(t.optDouble("exit_price"))
                    .append("\n수량 ").append(t.optDouble("qty"))
                    .append(" · 손익 ").append(String.format(Locale.US, "%+.4f", t.optDouble("pnl")))
                    .append(" (").append(String.format(Locale.US, "%+.3f%%", t.optDouble("pnl_percent")))
                    .append(") · 비용 ").append(String.format(Locale.US, "%.4f", t.optDouble("estimated_cost")))
                    .append("\n\n");
        }
        showTextDialog("전체 거래내역 · " + trades.length() + "건", sb.toString());
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

    private void enableResultActions(boolean enabled) {
        Button[] buttons = {resultSummaryButton, tradeHistoryButton, chartButton};
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
