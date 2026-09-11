from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN_ACTIVITY = ROOT / "android/app/src/main/java/com/nictunz/universalbacktester/MainActivity.java"
CHART_ACTIVITY = ROOT / "android/app/src/main/java/com/nictunz/universalbacktester/LocalMarketChartActivity.java"


def test_main_chart_action_opens_an_explicit_database_picker():
    source = MAIN_ACTIVITY.read_text(encoding="utf-8")
    assert "showDatabaseChartPicker()" in source
    assert 'setTitle("차트로 열 DB 선택")' in source
    assert "openLocalMarketChart(files.get(which))" in source
    assert 'putString("chart_db_path", databasePath)' in source


def test_local_chart_filters_markets_by_the_selected_database():
    source = CHART_ACTIVITY.read_text(encoding="utf-8")
    assert "databaseSelector" in source
    assert 'setTitle("차트 DB 선택")' in source
    assert "setSingleChoiceItems" in source
    assert "allMarkets" in source
    assert "selectDatabase(choices.get(which))" in source
    assert "samePath(row[0],selectedDatabasePath)" in source
