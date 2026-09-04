from pathlib import Path

path = Path('android/app/src/main/java/com/nictunz/universalbacktester/MainActivity.java')
text = path.read_text(encoding='utf-8')

old = '''        Button selectedBacktestButton = actionButton("▶ 선택한 수치로 기간 재백테스트", SUCCESS);
        selectedBacktestButton.setOnClickListener(v -> runSelectedStrategyBacktest());
        backtestCard.addView(selectedBacktestButton, marginTop(8));
'''
new = '''        Button editSelectedStrategyButton = actionButton("✏️ 선택/JSON 전략 수치 직접 수정", PRIMARY);
        editSelectedStrategyButton.setOnClickListener(v -> showSelectedStrategyEditor());
        backtestCard.addView(editSelectedStrategyButton, marginTop(8));
        backtestCard.addView(text(
                "JSON을 붙여넣거나 불러온 뒤 각 전략 수치를 직접 바꾸고 재백테스트할 수 있습니다.",
                11, MUTED, false
        ), marginTop(5));

        Button selectedBacktestButton = actionButton("▶ 수정된 수치로 기간 재백테스트", SUCCESS);
        selectedBacktestButton.setOnClickListener(v -> runSelectedStrategyBacktest());
        backtestCard.addView(selectedBacktestButton, marginTop(8));
'''
if old not in text:
    raise SystemExit('selected strategy button marker not found')
text = text.replace(old, new, 1)

text = text.replace(
    '            toast("먼저 수익률 TOP10에서 전략을 선택하세요.");',
    '            toast("먼저 TOP10 전략을 선택하거나 JSON 전략을 불러오세요.");',
    1,
)

old_dialog = '''                .setPositiveButton("이 기간 실행", (confirmDialog, which) ->
                        startBacktest(selectedStrategyParameters))
                .setNeutralButton("불러오기만", null)
                .setNegativeButton("취소", null)
                .show();
'''
new_dialog = '''                .setPositiveButton("이 기간 실행", (confirmDialog, which) ->
                        startBacktest(selectedStrategyParameters))
                .setNeutralButton("수치 수정", (confirmDialog, which) ->
                        showSelectedStrategyEditor())
                .setNegativeButton("불러오기만", null)
                .show();
'''
if old_dialog not in text:
    raise SystemExit('import completion dialog marker not found')
text = text.replace(old_dialog, new_dialog, 1)

marker = '    private void startBacktest(JSONObject fixedParameters) {\n'
if marker not in text:
    raise SystemExit('startBacktest marker not found')

method = r'''    private void showSelectedStrategyEditor() {
        if (selectedStrategyParameters == null) {
            toast("먼저 TOP10 전략을 선택하거나 JSON 전략을 불러오세요.");
            return;
        }

        LinearLayout outer = new LinearLayout(this);
        outer.setOrientation(LinearLayout.VERTICAL);
        outer.setPadding(dp(18), dp(4), dp(18), 0);
        outer.addView(text(
                "불러온 전략 수치를 직접 수정할 수 있습니다. 저장한 값이 다음 재백테스트에 그대로 사용됩니다.",
                12, MUTED, false
        ));

        ScrollView scroll = new ScrollView(this);
        LinearLayout fields = new LinearLayout(this);
        fields.setOrientation(LinearLayout.VERTICAL);
        scroll.addView(fields, new ScrollView.LayoutParams(
                ScrollView.LayoutParams.MATCH_PARENT,
                ScrollView.LayoutParams.WRAP_CONTENT
        ));
        LinearLayout.LayoutParams scrollParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(430)
        );
        scrollParams.topMargin = dp(10);
        outer.addView(scroll, scrollParams);

        java.util.ArrayList<String> keys = new java.util.ArrayList<>();
        java.util.Iterator<String> iterator = selectedStrategyParameters.keys();
        while (iterator.hasNext()) keys.add(iterator.next());
        java.util.Collections.sort(keys);

        java.util.LinkedHashMap<String, EditText> editors = new java.util.LinkedHashMap<>();
        for (String key : keys) {
            Object value = selectedStrategyParameters.opt(key);
            if (value instanceof JSONObject || value instanceof JSONArray) continue;

            String displayValue = value == null || value == JSONObject.NULL ? "" : String.valueOf(value);
            EditText input = edit(displayValue);
            input.setSingleLine(true);
            if (value instanceof Number) {
                input.setInputType(
                        android.text.InputType.TYPE_CLASS_NUMBER
                                | android.text.InputType.TYPE_NUMBER_FLAG_DECIMAL
                                | android.text.InputType.TYPE_NUMBER_FLAG_SIGNED
                );
            }
            fields.addView(labeled(key, input), marginTop(8));
            editors.put(key, input);
        }

        outer.addView(text(
                "숫자는 소수점 입력 가능 · true/false 값은 그대로 입력 · 빈 값은 허용하지 않습니다.",
                11, MUTED, false
        ), marginTop(8));

        AlertDialog dialog = new AlertDialog.Builder(this)
                .setTitle("전략 수치 직접 수정")
                .setView(outer)
                .setPositiveButton("저장 후 재백테스트", null)
                .setNeutralButton("저장만", null)
                .setNegativeButton("취소", null)
                .create();

        dialog.setOnShowListener(ignored -> {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
                if (saveSelectedStrategyEdits(editors)) {
                    dialog.dismiss();
                    startBacktest(selectedStrategyParameters);
                }
            });
            dialog.getButton(AlertDialog.BUTTON_NEUTRAL).setOnClickListener(v -> {
                if (saveSelectedStrategyEdits(editors)) {
                    dialog.dismiss();
                }
            });
        });
        dialog.show();
    }

    private boolean saveSelectedStrategyEdits(java.util.LinkedHashMap<String, EditText> editors) {
        if (selectedStrategyParameters == null) return false;
        try {
            for (java.util.Map.Entry<String, EditText> entry : editors.entrySet()) {
                String key = entry.getKey();
                String raw = entry.getValue().getText().toString().trim();
                if (raw.isEmpty()) {
                    toast(key + " 값을 입력하세요.");
                    return false;
                }

                Object oldValue = selectedStrategyParameters.opt(key);
                if (oldValue instanceof Boolean) {
                    if (!"true".equalsIgnoreCase(raw) && !"false".equalsIgnoreCase(raw)) {
                        toast(key + " 값은 true 또는 false로 입력하세요.");
                        return false;
                    }
                    selectedStrategyParameters.put(key, Boolean.parseBoolean(raw));
                } else if (oldValue instanceof Integer) {
                    selectedStrategyParameters.put(key, Integer.parseInt(raw));
                } else if (oldValue instanceof Long) {
                    selectedStrategyParameters.put(key, Long.parseLong(raw));
                } else if (oldValue instanceof Number) {
                    selectedStrategyParameters.put(key, Double.parseDouble(raw));
                } else {
                    selectedStrategyParameters.put(key, raw);
                }
            }

            if (selectedStrategyRow != null) {
                selectedStrategyRow.put("manually_edited", true);
                if (selectedStrategyRow.has("effective_parameters")) {
                    selectedStrategyRow.put("effective_parameters", selectedStrategyParameters);
                }
                if (selectedStrategyRow.has("parameters")) {
                    selectedStrategyRow.put("parameters", selectedStrategyParameters);
                }
            }
            persistSelectedStrategy();

            String current = selectedStrategyText == null ? "" : selectedStrategyText.getText().toString();
            if (selectedStrategyText != null && !current.contains("수동 수정됨")) {
                selectedStrategyText.setText(current + "\n✏️ 수동 수정됨 · 수정값으로 재백테스트 가능");
                selectedStrategyText.setTextColor(ACCENT);
            }
            toast("수정한 전략 수치를 저장했습니다.");
            return true;
        } catch (NumberFormatException e) {
            toast("숫자 형식을 확인하세요. 예: 2.4 또는 35");
            return false;
        } catch (Exception e) {
            showTextDialog("전략 수치 저장 실패", stackMessage(e));
            return false;
        }
    }

'''
text = text.replace(marker, method + marker, 1)
path.write_text(text, encoding='utf-8')
print('patched', path)
