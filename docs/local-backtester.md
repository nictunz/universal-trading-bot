# Universal Trading Backtester - Local Desktop / Android

## Windows EXE

GitHub Actions workflow: `Build Windows Backtester EXE`

Artifact: `UniversalTradingBacktester-Windows`

The desktop app provides:

- editable symbol selector with common crypto symbols
- editable timeframe selector
- calendar-backed start/end date inputs
- quick 30/90/180/365 day ranges
- dashboard-style trade/win-rate/PF/return/MDD cards
- local four-exchange cache generation and cache-only backtest
- SSH connection test
- protected SFTP upload to the server

Only 360-370 day caches can overwrite the server's `*-1y-*.db` files. Short test ranges use date-specific filenames and cannot be uploaded.

## Android APK

GitHub Actions workflow: `Build Android Backtester APK`

Artifact: `UniversalTradingBacktester-Android`

The Android app runs the same shared Python cache/backtest engine locally through Chaquopy. It stores databases under the app's private files directory, so no storage permission is required.

The app provides:

- common symbol suggestions plus direct symbol entry
- common timeframe suggestions plus direct entry
- start/end date text input and Android calendar picker
- quick 30/90/180/365 day ranges
- result metric cards
- phone-local cache and backtest execution
- phone-specific SSH key generation
- SSH connection test and protected server upload

### First Android SSH setup

1. Tap `휴대폰 전용 SSH 키 생성 / 확인`.
2. Copy the displayed public key.
3. Add that public key as one line in `/home/kpj3669/.ssh/authorized_keys` on the server.
4. Tap `SSH 연결 테스트`.
5. After a 360-370 day backtest completes, the upload button becomes available.

Never copy the phone private key out of the app. Only the public key belongs in `authorized_keys`.

## Mobile execution note

A one-year, four-exchange, five-minute backtest is CPU, network and storage intensive. The Android build keeps the screen awake while a backtest is running. For the most reliable long run, keep the app in the foreground and connect the phone to power. Desktop remains the preferred environment for very large multi-symbol cache generation.
