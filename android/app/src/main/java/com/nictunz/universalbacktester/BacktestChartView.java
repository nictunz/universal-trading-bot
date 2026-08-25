package com.nictunz.universalbacktester;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Path;
import android.view.View;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class BacktestChartView extends View {
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final List<Point> points = new ArrayList<>();
    private final List<TradeMarker> markers = new ArrayList<>();

    private static final class Point {
        final int bar;
        final String timestamp;
        final double equity;

        Point(int bar, String timestamp, double equity) {
            this.bar = bar;
            this.timestamp = timestamp;
            this.equity = equity;
        }
    }

    private static final class TradeMarker {
        final int trade;
        final String entryTime;
        final String exitTime;
        final String side;
        final String reason;
        final double pnl;

        TradeMarker(int trade, String entryTime, String exitTime, String side, String reason, double pnl) {
            this.trade = trade;
            this.entryTime = entryTime;
            this.exitTime = exitTime;
            this.side = side;
            this.reason = reason;
            this.pnl = pnl;
        }
    }

    public BacktestChartView(Context context) {
        super(context);
        setBackgroundColor(Color.rgb(7, 16, 29));
        setMinimumHeight(dp(360));
    }

    public void setData(JSONArray equity, JSONArray trades) {
        points.clear();
        markers.clear();
        if (equity != null) {
            for (int i = 0; i < equity.length(); i++) {
                JSONObject p = equity.optJSONObject(i);
                if (p == null) continue;
                points.add(new Point(
                        p.optInt("bar", i),
                        p.optString("timestamp", ""),
                        p.optDouble("equity", Double.NaN)
                ));
            }
        }
        if (trades != null) {
            for (int i = 0; i < trades.length(); i++) {
                JSONObject t = trades.optJSONObject(i);
                if (t == null) continue;
                markers.add(new TradeMarker(
                        t.optInt("trade", i + 1),
                        t.optString("entry_time", ""),
                        t.optString("exit_time", ""),
                        t.optString("side", ""),
                        t.optString("reason", "EXIT"),
                        t.optDouble("pnl", 0.0)
                ));
            }
        }
        invalidate();
    }

    @Override
    protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        float left = dp(54);
        float right = getWidth() - dp(14);
        float top = dp(24);
        float bottom = getHeight() - dp(42);
        float width = Math.max(1f, right - left);
        float height = Math.max(1f, bottom - top);

        paint.setStyle(Paint.Style.STROKE);
        paint.setStrokeWidth(dp(1));
        paint.setColor(Color.rgb(51, 65, 85));
        for (int i = 0; i <= 4; i++) {
            float y = top + height * i / 4f;
            canvas.drawLine(left, y, right, y, paint);
        }

        if (points.size() < 2) {
            paint.setStyle(Paint.Style.FILL);
            paint.setColor(Color.rgb(148, 163, 184));
            paint.setTextSize(dp(13));
            canvas.drawText("표시할 손익 곡선이 없습니다.", left, top + dp(30), paint);
            return;
        }

        double min = Double.POSITIVE_INFINITY;
        double max = Double.NEGATIVE_INFINITY;
        for (Point p : points) {
            if (!Double.isFinite(p.equity)) continue;
            min = Math.min(min, p.equity);
            max = Math.max(max, p.equity);
        }
        if (!Double.isFinite(min) || !Double.isFinite(max)) return;
        if (Math.abs(max - min) < 1e-9) max = min + 1.0;

        paint.setStyle(Paint.Style.FILL);
        paint.setTextSize(dp(10));
        paint.setColor(Color.rgb(148, 163, 184));
        canvas.drawText(String.format(Locale.US, "%.2f", max), dp(4), top + dp(4), paint);
        canvas.drawText(String.format(Locale.US, "%.2f", min), dp(4), bottom, paint);

        Path line = new Path();
        boolean started = false;
        for (int i = 0; i < points.size(); i++) {
            Point p = points.get(i);
            if (!Double.isFinite(p.equity)) continue;
            float x = left + width * i / (points.size() - 1f);
            float y = bottom - (float) ((p.equity - min) / (max - min)) * height;
            if (!started) {
                line.moveTo(x, y);
                started = true;
            } else {
                line.lineTo(x, y);
            }
        }
        paint.setStyle(Paint.Style.STROKE);
        paint.setStrokeWidth(dp(2));
        paint.setColor(Color.rgb(56, 189, 248));
        canvas.drawPath(line, paint);

        for (TradeMarker marker : markers) {
            drawMarker(canvas, marker, marker.entryTime, true, left, top, width, height, min, max);
            drawMarker(canvas, marker, marker.exitTime, false, left, top, width, height, min, max);
        }

        paint.setStyle(Paint.Style.FILL);
        paint.setTextSize(dp(10));
        paint.setColor(Color.rgb(34, 197, 94));
        canvas.drawText("▲ 진입", left, getHeight() - dp(14), paint);
        paint.setColor(Color.rgb(239, 68, 68));
        canvas.drawText("● 청산", left + dp(58), getHeight() - dp(14), paint);
        paint.setColor(Color.rgb(148, 163, 184));
        canvas.drawText("파랑: 순자산 곡선", left + dp(120), getHeight() - dp(14), paint);
    }

    private void drawMarker(
            Canvas canvas,
            TradeMarker marker,
            String timestamp,
            boolean entry,
            float left,
            float top,
            float width,
            float height,
            double min,
            double max
    ) {
        int index = nearestTimestampIndex(timestamp);
        if (index < 0) return;
        Point point = points.get(index);
        float x = left + width * index / (points.size() - 1f);
        float y = top + height - (float) ((point.equity - min) / (max - min)) * height;

        paint.setStyle(Paint.Style.FILL);
        if (entry) {
            paint.setColor("LONG".equalsIgnoreCase(marker.side)
                    ? Color.rgb(34, 197, 94)
                    : Color.rgb(245, 158, 11));
            Path triangle = new Path();
            triangle.moveTo(x, y - dp(7));
            triangle.lineTo(x - dp(6), y + dp(5));
            triangle.lineTo(x + dp(6), y + dp(5));
            triangle.close();
            canvas.drawPath(triangle, paint);
        } else {
            paint.setColor(marker.pnl >= 0
                    ? Color.rgb(34, 197, 94)
                    : Color.rgb(239, 68, 68));
            canvas.drawCircle(x, y, dp(4), paint);
            if (markers.size() <= 80 || marker.trade % 5 == 0) {
                paint.setTextSize(dp(8));
                canvas.drawText(
                        "#" + marker.trade + " " + marker.reason,
                        x + dp(4),
                        y - dp(5),
                        paint
                );
            }
        }
    }

    private int nearestTimestampIndex(String timestamp) {
        if (timestamp == null || timestamp.isEmpty() || points.isEmpty()) return -1;
        int low = 0;
        int high = points.size() - 1;
        while (low < high) {
            int mid = (low + high) >>> 1;
            String value = points.get(mid).timestamp;
            if (value.compareTo(timestamp) < 0) low = mid + 1;
            else high = mid;
        }
        if (low > 0) {
            String before = points.get(low - 1).timestamp;
            String after = points.get(low).timestamp;
            if (before.equals(timestamp)) return low - 1;
            if (after.isEmpty()) return low - 1;
        }
        return low;
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
