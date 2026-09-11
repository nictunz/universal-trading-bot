package com.nictunz.universalbacktester;

import android.app.Activity;
import android.graphics.Color;
import android.graphics.Typeface;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.HorizontalScrollView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;

/** TradingView Deep Backtest inspired read-only report for a completed local backtest. */
public class DeepBacktestReportActivity extends Activity {
    private static final int BG = Color.rgb(11, 18, 32);
    private static final int CARD = Color.rgb(23, 32, 51);
    private static final int TEXT = Color.rgb(248, 250, 252);
    private static final int MUTED = Color.rgb(148, 163, 184);
    private static final int ACCENT = Color.rgb(56, 189, 248);
    private static final int GOOD = Color.rgb(34, 197, 94);
    private static final int BAD = Color.rgb(239, 68, 68);

    private JSONObject summary;
    private LinearLayout content;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        try {
            summary = new JSONObject(getIntent().getStringExtra("summary_json"));
        } catch (Exception e) {
            summary = new JSONObject();
        }
        setContentView(buildUi());
        showOverview();
    }

    private View buildUi() {
        LinearLayout page = new LinearLayout(this);
        page.setOrientation(LinearLayout.VERTICAL);
        page.setPadding(dp(14), dp(14), dp(14), dp(24));
        page.setBackgroundColor(BG);

        TextView title = text("딥백테스트 리포트", 23, TEXT, true);
        page.addView(title);
        page.addView(text("TradingView 스타일 · 결과/낙폭/기간/거래/재현성 통합 확인", 12, MUTED, false), mt(4));

        HorizontalScrollView tabsScroll = new HorizontalScrollView(this);
        tabsScroll.setHorizontalScrollBarEnabled(false);
        LinearLayout tabs = new LinearLayout(this);
        tabs.setOrientation(LinearLayout.HORIZONTAL);
        tabs.setGravity(Gravity.CENTER_VERTICAL);
        tabsScroll.addView(tabs);
        addTab(tabs, "요약", v -> showOverview());
        addTab(tabs, "차트", v -> showChart());
        addTab(tabs, "기간분석", v -> showPeriods());
        addTab(tabs, "거래목록", v -> showTrades());
        addTab(tabs, "재현성", v -> showReproducibility());
        page.addView(tabsScroll, mt(12));

        ScrollView scroll = new ScrollView(this);
        content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(0, dp(8), 0, dp(28));
        scroll.addView(content, new ScrollView.LayoutParams(ScrollView.LayoutParams.MATCH_PARENT, ScrollView.LayoutParams.WRAP_CONTENT));
        page.addView(scroll, new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f));
        return page;
    }

    private void showOverview() {
        clear();
        JSONObject metrics = summary.optJSONObject("metrics");
        if (metrics == null) metrics = summary;
        addSection("핵심 성과");
        addMetric("순수익률", pct(first(metrics, "return_percent", "return_pct", "total_return_pct", "return")), true);
        addMetric("최대 낙폭 MDD", pct(first(metrics, "max_drawdown_percent", "mdd_pct", "max_drawdown_pct", "mdd")), false);
        addMetric("Profit Factor", num(first(metrics, "profit_factor", "pf"), 2), true);
        addMetric("승률", pct(first(metrics, "win_rate_pct", "win_rate")), true);
        addMetric("총 거래", integer(first(metrics, "trades", "trade_count", "total_trades")), true);
        addMetric("최대 연속 손실", integer(first(metrics, "max_loss_streak", "max_consecutive_losses")), false);
        addMetric("청산 횟수", integer(first(metrics, "liquidations", "liquidation_count")), false);

        addSection("실행 조건");
        addLine("체결 모델", firstString(summary, "execution_model", "fill_model", "execution"));
        addLine("초기자산", firstString(summary, "initial_capital", "initial_equity", "starting_balance"));
        addLine("계산 방식", firstString(summary, "sizing_mode", "compounding", "equity_mode"));
        addLine("요청 기간", joinRange(firstString(summary, "requested_start", "start_date", "start"), firstString(summary, "requested_end", "end_date", "end")));
        addLine("실제 기간", joinRange(firstString(summary, "actual_start", "data_start"), firstString(summary, "actual_end", "data_end")));
        addLine("실제 봉 수", firstString(summary, "bars", "bar_count", "actual_bars"));
        addLine("수수료", firstString(summary, "fee", "fee_rate", "commission"));
        addLine("슬리피지", firstString(summary, "slippage", "slippage_rate"));
    }

    private void showChart() {
        clear();
        addSection("순자산 + Underwater Drawdown");
        BacktestChartView chart = new BacktestChartView(this);
        chart.setData(summary.optJSONArray("equity_curve"), summary.optJSONArray("trades_log"));
        content.addView(chart, new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(440)));
        content.addView(text("▲ 진입 · ● 청산 · 아래쪽 붉은 영역은 고점 대비 낙폭입니다.", 11, MUTED, false), mt(8));
    }

    private void showPeriods() {
        clear();
        addSection("월별 거래 성과");
        JSONArray trades = summary.optJSONArray("trades_log");
        if (trades == null || trades.length() == 0) {
            content.addView(text("월별 분석에 사용할 거래내역이 없습니다.", 13, MUTED, false));
            return;
        }
        Map<String, PeriodStats> months = new LinkedHashMap<>();
        for (int i = 0; i < trades.length(); i++) {
            JSONObject t = trades.optJSONObject(i);
            if (t == null) continue;
            String ts = t.optString("exit_time", t.optString("entry_time", ""));
            String month = ts.length() >= 7 ? ts.substring(0, 7) : "기타";
            PeriodStats s = months.get(month);
            if (s == null) { s = new PeriodStats(); months.put(month, s); }
            double pnl = t.optDouble("pnl", 0.0);
            s.pnl += pnl; s.trades++; if (pnl >= 0) s.wins++;
        }
        for (Map.Entry<String, PeriodStats> e : months.entrySet()) {
            PeriodStats s = e.getValue();
            addLine(e.getKey(), String.format(Locale.US, "손익 %.2f · %d회 · 승률 %.1f%%", s.pnl, s.trades, s.trades == 0 ? 0 : 100.0 * s.wins / s.trades));
        }

        addSection("LONG / SHORT");
        PeriodStats longs = new PeriodStats();
        PeriodStats shorts = new PeriodStats();
        for (int i = 0; i < trades.length(); i++) {
            JSONObject t = trades.optJSONObject(i); if (t == null) continue;
            PeriodStats s = "SHORT".equalsIgnoreCase(t.optString("side")) ? shorts : longs;
            double pnl = t.optDouble("pnl", 0.0); s.pnl += pnl; s.trades++; if (pnl >= 0) s.wins++;
        }
        addPeriodLine("LONG", longs);
        addPeriodLine("SHORT", shorts);
    }

    private void showTrades() {
        clear();
        JSONArray trades = summary.optJSONArray("trades_log");
        addSection("전체 거래내역" + (trades == null ? "" : " · " + trades.length() + "건"));
        if (trades == null || trades.length() == 0) {
            content.addView(text("표시할 거래내역이 없습니다.", 13, MUTED, false));
            return;
        }
        for (int i = 0; i < trades.length(); i++) {
            JSONObject t = trades.optJSONObject(i); if (t == null) continue;
            LinearLayout card = card();
            double pnl = t.optDouble("pnl", 0.0);
            card.addView(text("#" + t.optInt("trade", i + 1) + "  " + t.optString("side", "-"), 14, pnl >= 0 ? GOOD : BAD, true));
            card.addView(text("진입 " + t.optString("entry_time", "-") + "  @ " + formatMaybe(t, "entry_price"), 11, MUTED, false), mt(4));
            card.addView(text("청산 " + t.optString("exit_time", "-") + "  @ " + formatMaybe(t, "exit_price"), 11, MUTED, false), mt(2));
            card.addView(text(String.format(Locale.US, "손익 %.2f · %s", pnl, t.optString("reason", "EXIT")), 12, TEXT, true), mt(4));
            content.addView(card, mt(7));
        }
    }

    private void showReproducibility() {
        clear();
        addSection("재현성 판정");
        String status = firstString(summary, "reproducibility_status", "reproduction_status", "repro_status");
        if (status.isEmpty()) status = "미판정 · 결과 메타데이터 확인 필요";
        TextView badge = text(status, 15, status.toUpperCase(Locale.US).contains("PASS") ? GOOD : BAD, true);
        content.addView(badge, mt(4));

        addSection("엔진 / 데이터 지문");
        addLine("엔진 schema", firstString(summary, "engine_schema"));
        addLine("엔진 이름", firstString(summary, "engine_name"));
        addLine("엔진 버전", firstString(summary, "engine_version"));
        addLine("엔진 SHA256", firstString(summary, "engine_code_sha256", "engine_sha256"));
        addLine("캐시 SHA256", firstString(summary, "cache_sha256", "data_sha256"));
        addLine("Run signature", firstString(summary, "run_signature"));
        addLine("Candidate signature", firstString(summary, "candidate_signature"));
        addLine("체결 모델", firstString(summary, "execution_model", "fill_model"));
        addLine("계산 방식", firstString(summary, "sizing_mode", "compounding"));
        addLine("봉 수", firstString(summary, "bars", "bar_count", "actual_bars"));
        content.addView(text("기간·데이터 SHA·엔진 코드·체결 모델·복리 설정·후보 서명이 모두 같을 때만 동일 결과로 취급하는 것을 권장합니다.", 11, MUTED, false), mt(10));
    }

    private void addPeriodLine(String name, PeriodStats s) {
        addLine(name, String.format(Locale.US, "손익 %.2f · %d회 · 승률 %.1f%%", s.pnl, s.trades, s.trades == 0 ? 0 : 100.0 * s.wins / s.trades));
    }

    private void clear() { content.removeAllViews(); }
    private void addSection(String s) { content.addView(text(s, 17, TEXT, true), mt(12)); }

    private void addMetric(String label, String value, boolean higherIsBetter) {
        LinearLayout row = card();
        row.setOrientation(LinearLayout.HORIZONTAL);
        TextView l = text(label, 12, MUTED, true);
        TextView v = text(value.isEmpty() ? "-" : value, 18, TEXT, true);
        row.addView(l, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));
        row.addView(v);
        content.addView(row, mt(7));
    }

    private void addLine(String label, String value) {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setPadding(dp(10), dp(8), dp(10), dp(8));
        row.addView(text(label, 12, MUTED, false), new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 0.42f));
        TextView v = text(value == null || value.isEmpty() ? "-" : value, 12, TEXT, true);
        v.setGravity(Gravity.END);
        row.addView(v, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 0.58f));
        content.addView(row);
    }

    private LinearLayout card() {
        LinearLayout v = new LinearLayout(this);
        v.setOrientation(LinearLayout.VERTICAL);
        v.setPadding(dp(12), dp(10), dp(12), dp(10));
        android.graphics.drawable.GradientDrawable bg = new android.graphics.drawable.GradientDrawable();
        bg.setColor(CARD); bg.setCornerRadius(dp(10)); bg.setStroke(dp(1), Color.rgb(38, 50, 71));
        v.setBackground(bg); return v;
    }

    private void addTab(LinearLayout tabs, String label, View.OnClickListener l) {
        Button b = new Button(this); b.setText(label); b.setTextColor(TEXT); b.setTextSize(12); b.setAllCaps(false);
        b.setBackgroundColor(Color.rgb(30, 41, 59)); b.setOnClickListener(l);
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, dp(44)); p.setMargins(0,0,dp(6),0); tabs.addView(b,p);
    }

    private TextView text(String s, int sp, int color, boolean bold) {
        TextView t = new TextView(this); t.setText(s); t.setTextSize(sp); t.setTextColor(color); if (bold) t.setTypeface(Typeface.DEFAULT, Typeface.BOLD); return t;
    }
    private LinearLayout.LayoutParams mt(int top) { LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT); p.topMargin = dp(top); return p; }
    private int dp(int v) { return Math.round(v * getResources().getDisplayMetrics().density); }
    private static String pct(double v) { return Double.isFinite(v) ? String.format(Locale.US, "%.2f%%", v) : "-"; }
    private static String num(double v, int n) { return Double.isFinite(v) ? String.format(Locale.US, "%." + n + "f", v) : "-"; }
    private static String integer(double v) { return Double.isFinite(v) ? String.format(Locale.US, "%.0f", v) : "-"; }
    private static String joinRange(String a, String b) { return (a.isEmpty() && b.isEmpty()) ? "" : a + " ~ " + b; }
    private static double first(JSONObject o, String... keys) { for (String k:keys) if (o.has(k) && !o.isNull(k)) return o.optDouble(k, Double.NaN); return Double.NaN; }
    private static String firstString(JSONObject o, String... keys) { for (String k:keys) if (o.has(k) && !o.isNull(k)) return String.valueOf(o.opt(k)); return ""; }
    private static String formatMaybe(JSONObject o, String key) { return o.has(key) ? String.format(Locale.US, "%.4f", o.optDouble(key)) : "-"; }

    private static final class PeriodStats { double pnl; int trades; int wins; }
}

