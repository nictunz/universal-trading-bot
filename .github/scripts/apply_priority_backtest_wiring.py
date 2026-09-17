from pathlib import Path

# 1.1.333 hardening patch for the integrated LIVE Priority backtest.
# The integrated request now has an explicit request type and the service
# refuses to route it through the DB-only download path.

main = Path('android/app/src/main/java/com/nictunz/universalbacktester/MainActivity.java')
text = main.read_text(encoding='utf-8')

needle = '                    intent.putExtra("priority_live_parity", true);\n'
replacement = '''                    intent.putExtra("priority_live_parity", true);\n                    intent.putExtra("request_type", "PRIORITY_5M_15M");\n'''
if 'intent.putExtra("request_type", "PRIORITY_5M_15M")' not in text:
    if needle not in text:
        raise SystemExit('MainActivity priority intent wiring not found')
    text = text.replace(needle, replacement, 1)

old_log = '                    setFullLog("LIVE 통합 Priority 백테스트 시작\\n선택 5분 DB: " + priorityDb.getName() + "\\n4거래소 5분 원본 확인 → 15분 자동 생성 → 5분+15분 단일 포지션 재생\\n5분 9.55배 + 15분 5배 · 5분 우선\\n");\n'
new_log = '                    setFullLog("LIVE 통합 Priority 백테스트 시작\\n요청타입: PRIORITY_5M_15M · ACTION_START\\n선택 5분 DB: " + priorityDb.getName() + "\\ntimeframe: 5m+15m · Python: run_priority_live_backtest\\n4거래소 5분 원본 확인 → 15분 자동 생성 → 5분+15분 단일 포지션 재생\\n5분 9.55배 + 15분 5배 · 5분 우선\\n");\n'
if '요청타입: PRIORITY_5M_15M' not in text:
    if old_log not in text:
        raise SystemExit('MainActivity priority log wiring not found')
    text = text.replace(old_log, new_log, 1)
main.write_text(text, encoding='utf-8')

service = Path('android/app/src/main/java/com/nictunz/universalbacktester/BacktestForegroundService.java')
text = service.read_text(encoding='utf-8')

needle = '    public static final String ACTION_DOWNLOAD_DB = "com.nictunz.universalbacktester.DB_DOWNLOAD";\n'
replacement = needle + '    private static final String REQUEST_PRIORITY_5M_15M = "PRIORITY_5M_15M";\n'
if 'REQUEST_PRIORITY_5M_15M' not in text:
    if needle not in text:
        raise SystemExit('Service action constants not found')
    text = text.replace(needle, replacement, 1)

old = '''                request = requestFromIntent(intent);\n                request.put("db_only", ACTION_DOWNLOAD_DB.equals(action));\n                prefs().edit().putString("backtest_request", request.toString())\n'''
new = '''                request = requestFromIntent(intent);\n                boolean priorityRequest = REQUEST_PRIORITY_5M_15M.equals(request.optString("request_type", ""));\n                if (priorityRequest && !ACTION_START.equals(action)) {\n                    throw new IllegalArgumentException("PRIORITY_5M_15M must use ACTION_START");\n                }\n                request.put("db_only", priorityRequest ? false : ACTION_DOWNLOAD_DB.equals(action));\n                prefs().edit().putString("backtest_request", request.toString())\n'''
if 'priorityRequest && !ACTION_START.equals(action)' not in text:
    if old not in text:
        raise SystemExit('Service request routing block not found')
    text = text.replace(old, new, 1)

old = '''            String response;\n            if (request.optBoolean("db_only", false)) {\n'''
new = '''            String response;\n            boolean priorityRequest = REQUEST_PRIORITY_5M_15M.equals(request.optString("request_type", ""));\n            if (priorityRequest) {\n                String databasePath = request.optString("database_path", "");\n                File priorityDb = new File(databasePath);\n                if (!request.optBoolean("priority_live_parity", false)) {\n                    throw new IllegalArgumentException("PRIORITY_5M_15M missing priority_live_parity=true");\n                }\n                if (request.optBoolean("db_only", false)) {\n                    throw new IllegalArgumentException("PRIORITY_5M_15M cannot run as DB download");\n                }\n                if (!"5m+15m".equals(request.optString("timeframe", ""))) {\n                    throw new IllegalArgumentException("PRIORITY_5M_15M requires timeframe=5m+15m");\n                }\n                if (!priorityDb.isFile() || !priorityDb.getName().toLowerCase(java.util.Locale.US).endsWith("-5m.db")) {\n                    throw new IllegalArgumentException("PRIORITY_5M_15M requires an existing -5m.db source");\n                }\n                updateNotification("LIVE 5분+15분 통합 백테스트 실행 중");\n                response = bridge.callAttr(\n                    "run_priority_live_backtest",\n                    request.getString("symbol"), request.getString("start"), request.getString("end"),\n                    request.getString("output_dir"), databasePath,\n                    request.optDouble("initial_capital", 1000.0), request.optBoolean("compounding_enabled", true)\n                ).toString();\n            } else if (request.optBoolean("db_only", false)) {\n'''
if 'PRIORITY_5M_15M requires timeframe=5m+15m' not in text:
    if old not in text:
        raise SystemExit('Service execution dispatch block not found')
    text = text.replace(old, new, 1)

# Remove the legacy boolean-only priority branch so only the explicit request type
# can enter the integrated engine.
legacy = '''            } else if (request.optBoolean("priority_live_parity", false)) {\n                updateNotification("LIVE 5분+15분 통합 백테스트 실행 중");\n                response = bridge.callAttr(\n                    "run_priority_live_backtest",\n                    request.getString("symbol"), request.getString("start"), request.getString("end"),\n                    request.getString("output_dir"), request.optString("database_path", ""),\n                    request.optDouble("initial_capital", 1000.0), request.optBoolean("compounding_enabled", true)\n                ).toString();\n'''
if legacy in text:
    text = text.replace(legacy, '', 1)

needle = '        request.put("priority_live_parity", intent.getBooleanExtra("priority_live_parity", false));\n'
replacement = needle + '        request.put("request_type", intent.getStringExtra("request_type"));\n'
if 'request.put("request_type", intent.getStringExtra("request_type"))' not in text:
    if needle not in text:
        raise SystemExit('Service requestFromIntent priority field not found')
    text = text.replace(needle, replacement, 1)

service.write_text(text, encoding='utf-8')
print('Priority 1.1.333 explicit request routing hardening applied')
