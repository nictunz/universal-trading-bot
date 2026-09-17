from pathlib import Path

# 1.1.332 hardening patch for the integrated LIVE Priority backtest.
# Safe to run repeatedly: every replacement is guarded by the new text.
# Trigger: apply guarded patch to current main and then build Android 1.1.332.

main = Path('android/app/src/main/java/com/nictunz/universalbacktester/MainActivity.java')
text = main.read_text(encoding='utf-8')

old = '        if (selectedDbPath == null || selectedDbPath.trim().isEmpty()) { toast("먼저 5분·15분 및 4거래소 데이터가 들어있는 저장 DB를 선택하세요."); return; }\n'
new = '''        if (selectedDbPath == null || selectedDbPath.trim().isEmpty()) { toast("먼저 4거래소 5분 저장 DB를 선택하세요."); return; }\n        File priorityDb = new File(selectedDbPath);\n        String priorityDbName = priorityDb.getName().toLowerCase(Locale.US);\n        if (!priorityDb.isFile() || !priorityDbName.endsWith("-5m.db")) {\n            toast("LIVE 통합 백테스트는 5분 DB를 선택해야 합니다. 15분봉은 같은 5분 DB에서 자동 생성됩니다.");\n            return;\n        }\n'''
if old in text:
    text = text.replace(old, new, 1)

old = '                .setMessage("5분 9.55배 + 15분 5배를 한 계좌/한 포지션으로 시간순 재생합니다.\\n\\n• 5분 신호 우선\\n• 5분 보유 중 신규 신호 차단\\n• 15분 보유 중 5분 신호 → 15분 정리 후 5분 진입\\n• 고정 TP/SL · 동봉 SL 우선\\n• 수수료 0.02% + 슬리피지 0.01% / side")\n'
new = '                .setMessage("선택한 5분 DB의 Binance/Bitget/OKX/Bybit 원본을 함께 읽고, 각 거래소의 완전한 5분봉 3개로 15분봉을 자동 생성합니다.\\n\\n5분 9.55배 + 15분 5배를 한 계좌/한 포지션으로 시간순 재생합니다.\\n\\n• 5분 신호 우선\\n• 5분 보유 중 신규 신호 차단\\n• 15분 보유 중 5분 신호 → 15분 정리 후 5분 진입\\n• 고정 TP/SL · 동봉 SL 우선\\n• 수수료 0.02% + 슬리피지 0.01% / side")\n'
if old in text:
    text = text.replace(old, new, 1)

old = '''                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) startForegroundService(intent); else startService(intent);\n                    lastDbPath = ""; lastResultPath = ""; lastUploadEligible = false; lastSummary = null;\n'''
new = '''                    getSharedPreferences("universal_bot", MODE_PRIVATE).edit()\n                            .putBoolean("backtest_requested", true)\n                            .putBoolean("backtest_paused", false)\n                            .putString("backtest_status", "RUNNING")\n                            .putString("backtest_log", "")\n                            .putString("backtest_result", "")\n                            .putString("backtest_error", "")\n                            .apply();\n                    appliedServiceResultPath = "";\n                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) startForegroundService(intent); else startService(intent);\n                    lastDbPath = ""; lastResultPath = ""; lastUploadEligible = false; lastSummary = null;\n'''
if old in text:
    text = text.replace(old, new, 1)

old = '                    setFullLog("LIVE 통합 Priority 백테스트 시작\\n5분 9.55배 + 15분 5배 · 단일 포지션 · 5분 우선\\n");\n'
new = '                    setFullLog("LIVE 통합 Priority 백테스트 시작\\n선택 5분 DB: " + priorityDb.getName() + "\\n4거래소 5분 원본 확인 → 15분 자동 생성 → 5분+15분 단일 포지션 재생\\n5분 9.55배 + 15분 5배 · 5분 우선\\n");\n'
if old in text:
    text = text.replace(old, new, 1)

main.write_text(text, encoding='utf-8')

service = Path('android/app/src/main/java/com/nictunz/universalbacktester/BacktestForegroundService.java')
text = service.read_text(encoding='utf-8')
old = '''                        .putString("backtest_status", "RUNNING")\n                        .putString("backtest_error", "")\n                        .apply();\n'''
new = '''                        .putString("backtest_status", "RUNNING")\n                        .putString("backtest_log", "")\n                        .putString("backtest_result", "")\n                        .putString("backtest_error", "")\n                        .apply();\n'''
if old in text:
    text = text.replace(old, new, 1)
service.write_text(text, encoding='utf-8')

print('Priority 1.1.332 UI/service hardening applied')
