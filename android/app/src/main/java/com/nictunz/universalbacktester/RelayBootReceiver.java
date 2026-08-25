package com.nictunz.universalbacktester;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;

/** Restarts the user-enabled foreground market relay after device/app updates. */
public final class RelayBootReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        String action = intent == null ? "" : String.valueOf(intent.getAction());
        if (!Intent.ACTION_BOOT_COMPLETED.equals(action)
                && !Intent.ACTION_LOCKED_BOOT_COMPLETED.equals(action)
                && !Intent.ACTION_MY_PACKAGE_REPLACED.equals(action)) {
            return;
        }
        SharedPreferences prefs =
                context.getSharedPreferences("universal_bot", Context.MODE_PRIVATE);
        if (!prefs.getBoolean("relay_requested", false)) return;

        Intent service = new Intent(context, MobileMarketRelayService.class);
        service.setAction(MobileMarketRelayService.ACTION_START);
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(service);
            } else {
                context.startService(service);
            }
        } catch (Exception e) {
            prefs.edit()
                    .putBoolean("relay_running", false)
                    .putString("relay_status", "자동 재시작 대기 · 앱을 한 번 열어주세요")
                    .putString("relay_last_error", e.getClass().getSimpleName() + ": " + e.getMessage())
                    .apply();
        }
    }
}
