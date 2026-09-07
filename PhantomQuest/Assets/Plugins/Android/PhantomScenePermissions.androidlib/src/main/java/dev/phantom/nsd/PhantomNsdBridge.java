package dev.phantom.nsd;

import android.content.Context;
import android.net.nsd.NsdManager;
import android.net.nsd.NsdServiceInfo;
import android.net.wifi.WifiManager;
import java.nio.charset.StandardCharsets;
import java.util.ArrayDeque;
import java.util.Map;

/** Lifecycle-owned Android NSD adapter. It emits normalized metadata only. */
public final class PhantomNsdBridge {
    public interface Listener {
        void onResolved(String instance, String serviceType, String host, int port,
                        String robotId, String protocolMajor, String bootHex, String buildId);
        void onLost(String instance, String serviceType);
        void onError(String category);
    }

    private static final String MULTICAST_LOCK_TAG = "phantom-dns-sd";

    private final NsdManager manager;
    private final WifiManager wifi;
    private final Listener listener;
    private final ArrayDeque<NsdServiceInfo> resolveQueue = new ArrayDeque<>();
    private NsdManager.DiscoveryListener discovery;
    private WifiManager.MulticastLock multicastLock;
    private boolean resolving;

    public PhantomNsdBridge(Context context, Listener listener) {
        if (context == null || listener == null) throw new IllegalArgumentException("context/listener");
        Context application = context.getApplicationContext();
        this.manager = (NsdManager) application.getSystemService(Context.NSD_SERVICE);
        this.wifi = (WifiManager) application.getSystemService(Context.WIFI_SERVICE);
        this.listener = listener;
    }

    public synchronized void start(final String serviceType) {
        if (discovery != null) return;
        // Some Android/SDK-extension combinations drop foreground multicast without
        // an explicit lock. It is held only for the bounded discovery window and is
        // released on every exit path below, including start failure.
        acquireMulticastLock();
        discovery = new NsdManager.DiscoveryListener() {
            @Override public void onDiscoveryStarted(String type) { }
            @Override public void onDiscoveryStopped(String type) { releaseMulticastLock(); }
            @Override public void onStartDiscoveryFailed(String type, int code) { listener.onError("start_" + code); stop(); }
            @Override public void onStopDiscoveryFailed(String type, int code) { listener.onError("stop_" + code); releaseMulticastLock(); }
            @Override public void onServiceFound(final NsdServiceInfo service) {
                if (!sameType(serviceType, service.getServiceType())) return;
                enqueueResolve(service);
            }
            @Override public void onServiceLost(NsdServiceInfo service) {
                listener.onLost(service.getServiceName(), normalize(service.getServiceType()));
            }
        };
        try {
            manager.discoverServices(serviceType, NsdManager.PROTOCOL_DNS_SD, discovery);
        } catch (RuntimeException error) {
            discovery = null;
            releaseMulticastLock();
            listener.onError("discover_" + error.getClass().getSimpleName());
        }
    }

    public synchronized void stop() {
        if (discovery == null) { releaseMulticastLock(); return; }
        NsdManager.DiscoveryListener value = discovery;
        discovery = null;
        resolveQueue.clear(); resolving = false;
        try { manager.stopServiceDiscovery(value); } catch (IllegalArgumentException ignored) { }
        releaseMulticastLock();
    }

    private synchronized void acquireMulticastLock() {
        if (wifi == null || multicastLock != null) return;
        try {
            WifiManager.MulticastLock lock = wifi.createMulticastLock(MULTICAST_LOCK_TAG);
            lock.setReferenceCounted(false);
            lock.acquire();
            multicastLock = lock;
        } catch (RuntimeException error) {  // SecurityException is one of these.
            // Discovery may still work without the lock on newer platforms; the
            // absence is reported, never silently assumed to be fine.
            listener.onError("multicast_lock_unavailable");
        }
    }

    private synchronized void releaseMulticastLock() {
        if (multicastLock == null) return;
        try {
            if (multicastLock.isHeld()) multicastLock.release();
        } catch (RuntimeException ignored) {
        } finally {
            multicastLock = null;
        }
    }

    public synchronized boolean isMulticastLockHeld() {
        return multicastLock != null && multicastLock.isHeld();
    }

    private synchronized void enqueueResolve(NsdServiceInfo service) {
        if (resolveQueue.size() >= 64) { listener.onError("resolve_queue_full"); return; }
        resolveQueue.addLast(service); resolveNext();
    }

    private synchronized void resolveNext() {
        if (resolving || discovery == null || resolveQueue.isEmpty()) return;
        resolving = true;
        manager.resolveService(resolveQueue.removeFirst(), new NsdManager.ResolveListener() {
            @Override public void onResolveFailed(NsdServiceInfo value, int code) {
                listener.onError("resolve_" + code); synchronized (PhantomNsdBridge.this) { resolving=false; resolveNext(); }
            }
            @Override public void onServiceResolved(NsdServiceInfo value) {
                Map<String, byte[]> txt = value.getAttributes();
                listener.onResolved(value.getServiceName(), normalize(value.getServiceType()),
                    value.getHost().getHostAddress(), value.getPort(), text(txt,"robot_id"),
                    text(txt,"protocol_major"), text(txt,"controller_boot_id"), text(txt,"build_id"));
                synchronized (PhantomNsdBridge.this) { resolving=false; resolveNext(); }
            }
        });
    }

    private static String text(Map<String,byte[]> values, String key) {
        byte[] value = values.get(key); return value == null ? "" : new String(value, StandardCharsets.UTF_8);
    }

    static boolean sameType(String left, String right) { return normalize(left).equals(normalize(right)); }

    /**
     * Reduce any platform spelling of a DNS-SD type to `_service._proto`.
     *
     * Android reports the type inconsistently across versions and callbacks:
     * `_phantom-ev3._udp`, `_phantom-ev3._udp.`, `_phantom-ev3._udp.local` and
     * `_phantom-ev3._udp.local.` all occur. Comparing anything less than this
     * would silently discard a robot that is actually being advertised.
     */
    static String normalize(String value) {
        if (value == null) return "";
        String trimmed = value.trim();
        while (trimmed.endsWith(".")) trimmed = trimmed.substring(0, trimmed.length() - 1);
        int protocol = -1;
        String lowered = trimmed.toLowerCase();
        int udp = lowered.indexOf("._udp");
        int tcp = lowered.indexOf("._tcp");
        if (udp >= 0) protocol = udp + "._udp".length();
        else if (tcp >= 0) protocol = tcp + "._tcp".length();
        if (protocol > 0) trimmed = trimmed.substring(0, protocol);
        return trimmed;
    }
}
