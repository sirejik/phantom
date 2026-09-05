package dev.phantom.nsd;

import android.content.Context;
import android.net.nsd.NsdManager;
import android.net.nsd.NsdServiceInfo;
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

    private final NsdManager manager;
    private final Listener listener;
    private final ArrayDeque<NsdServiceInfo> resolveQueue = new ArrayDeque<>();
    private NsdManager.DiscoveryListener discovery;
    private boolean resolving;

    public PhantomNsdBridge(Context context, Listener listener) {
        if (context == null || listener == null) throw new IllegalArgumentException("context/listener");
        this.manager = (NsdManager)context.getApplicationContext().getSystemService(Context.NSD_SERVICE);
        this.listener = listener;
    }

    public synchronized void start(final String serviceType) {
        if (discovery != null) return;
        discovery = new NsdManager.DiscoveryListener() {
            @Override public void onDiscoveryStarted(String type) { }
            @Override public void onDiscoveryStopped(String type) { }
            @Override public void onStartDiscoveryFailed(String type, int code) { listener.onError("start_" + code); stop(); }
            @Override public void onStopDiscoveryFailed(String type, int code) { listener.onError("stop_" + code); }
            @Override public void onServiceFound(final NsdServiceInfo service) {
                if (!sameType(serviceType, service.getServiceType())) return;
                enqueueResolve(service);
            }
            @Override public void onServiceLost(NsdServiceInfo service) {
                listener.onLost(service.getServiceName(), normalize(service.getServiceType()));
            }
        };
        manager.discoverServices(serviceType, NsdManager.PROTOCOL_DNS_SD, discovery);
    }

    public synchronized void stop() {
        if (discovery == null) return;
        NsdManager.DiscoveryListener value = discovery;
        discovery = null;
        resolveQueue.clear(); resolving = false;
        try { manager.stopServiceDiscovery(value); } catch (IllegalArgumentException ignored) { }
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
    private static boolean sameType(String left, String right) { return normalize(left).equals(normalize(right)); }
    private static String normalize(String value) {
        if (value == null) return ""; return value.endsWith(".") ? value.substring(0,value.length()-1) : value;
    }
}
