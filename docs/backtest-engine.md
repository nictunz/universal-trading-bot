## Android 백테스트 엔진 선택 기록

조사일: 2026-09-04

### 후보 검토

| 프로젝트 | 당시 GitHub 인기 | 라이선스/구조 | Android 앱 직접 탑재 판단 |
|---|---:|---|---|
| [Freqtrade](https://github.com/freqtrade/freqtrade) ([대표 백테스트 엔진 파일](https://github.com/freqtrade/freqtrade/blob/develop/freqtrade/optimize/backtesting.py)) | 약 54k stars | GPL-3.0, Python 3.11+, CCXT·SciPy·TA-Lib·SQLAlchemy 등 | 암호화폐 분야 기준 프로젝트로 채택하되 원본 코드는 탑재하지 않음 |
| [Backtrader](https://github.com/mementum/backtrader) | 약 22k stars | GPL-3.0, 순수 Python | 라이선스와 봉 단위 반복 성능 때문에 제외 |
| [LEAN](https://github.com/QuantConnect/Lean) | 약 19k stars | Apache-2.0, C# 중심 대형 엔진 | Android/Chaquopy에 직접 탑재하기 어려워 제외 |
| [VectorBT](https://github.com/polakowo/vectorbt) | 약 8k stars | Apache-2.0 + Commons Clause, Numba 중심 | Android용 Numba/LLVM 의존성 때문에 제외 |
| [Backtesting.py](https://github.com/kernc/backtesting.py) | 약 9k stars | AGPL-3.0, Bokeh 포함 | 라이선스와 시각화 의존성 때문에 제외 |

### 적용 방식

외부 GPL/AGPL 코드는 복사하지 않았다. Freqtrade의 공개 문서에서 확인되는
백테스트 수명주기, 미래참조 검사, 재귀 지표 검사, 명시적 체결 가정과 같은
검증 원칙을 참고해 기존 앱 엔진을 독립적으로 `Universal Vector Engine 5`로
재구성했다.

- 현재 전략, 4개 거래소 거래량, 교차마진, 복리/고정식, 두 체결 모델을 보존한다.
- Android 의존성은 NumPy와 Pandas만 추가 사용한다.
- OHLCV와 지표는 한 번 준비하고 제한된 LRU 캐시에서 재사용한다.
- 최적화 후보에서는 전체 순자산 곡선을 만들지 않고 최종 결과에서만 만든다.
- 엔진 파일 SHA256, 데이터 SHA256, 기간, 전체 설정을 체크포인트 지문에 넣는다.
- 각 TOP10 후보에 결과 서명을 저장하고 재백테스트 시 모든 조건을 비교한다.
- 저장 결과를 열 때 원본 당시의 캐시 SHA256을 유지하며 현재 DB 지문으로 덮어쓰지 않는다.

### 로컬 성능 확인

20,000개 5분봉 합성 데이터에서 최종 상세 모드는 0.9193초, 지표 캐시가
준비된 최적화 모드는 0.4025초로 측정되어 2.28배 빨랐다. 거래 수, 손익,
수익률, MDD를 포함한 핵심 수치는 두 모드에서 일치했다. 실제 휴대폰 속도는
기기와 기간, 전략 설정에 따라 달라질 수 있다.

외부 프로젝트의 소스 코드는 포함하지 않았으므로 각 프로젝트의 copyleft
코드가 앱 바이너리에 결합되지 않는다.
