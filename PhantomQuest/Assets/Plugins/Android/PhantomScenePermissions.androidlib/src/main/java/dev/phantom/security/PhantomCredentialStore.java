package dev.phantom.security;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.RandomAccessFile;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import java.util.Arrays;

import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/** App-private PSK storage encrypted by a non-exportable Android Keystore key. */
public final class PhantomCredentialStore {
    private static final String KEYSTORE = "AndroidKeyStore";
    private static final String MASTER_ALIAS = "dev.phantom.control-credential.v1";
    private static final String PREFS = "phantom.credentials.v1";
    private static final byte FORMAT = 1;

    /** Engineering provisioning drop directory, relative to app-specific external files. */
    public static final String PROVISIONING_DIRECTORY = "phantom-provisioning";

    private PhantomCredentialStore() {}

    public static synchronized boolean provision(Context context, String keyId, byte[] key) {
        if (!validKeyId(keyId) || key == null || key.length < 32) return false;
        byte[] encoded = null;
        try {
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE, masterKey());
            cipher.updateAAD(keyId.getBytes(StandardCharsets.US_ASCII));
            byte[] ciphertext = cipher.doFinal(key);
            byte[] iv = cipher.getIV();
            if (iv == null || iv.length < 12 || iv.length > 32) return false;
            encoded = new byte[2 + iv.length + ciphertext.length];
            encoded[0] = FORMAT;
            encoded[1] = (byte) iv.length;
            System.arraycopy(iv, 0, encoded, 2, iv.length);
            System.arraycopy(ciphertext, 0, encoded, 2 + iv.length, ciphertext.length);
            return preferences(context).edit().putString(keyId, Base64.encodeToString(encoded, Base64.NO_WRAP)).commit();
        } catch (Exception ignored) {
            return false;
        } finally {
            if (encoded != null) Arrays.fill(encoded, (byte) 0);
        }
    }

    public static synchronized boolean isProvisioned(Context context, String keyId) {
        if (!validKeyId(keyId)) return false;
        try {
            return preferences(context).getString(keyId, null) != null;
        } catch (Exception ignored) {
            return false;
        }
    }

    /**
     * One-shot engineering import of a CONTROL PSK delivered outside the runtime
     * protocol.
     *
     * The host writes the key into the app-specific provisioning directory; this
     * method imports it into the Keystore-wrapped store and then overwrites and
     * deletes the plaintext drop so it does not survive the import. The key never
     * appears in the APK, in Resources, in a build manifest, in a command line or
     * in any log: only the outcome is reported.
     *
     * @return 1 imported, 0 nothing to import, -1 a drop existed but was rejected.
     */
    public static synchronized int importProvisioningDrop(Context context, String keyId) {
        if (!validKeyId(keyId)) return -1;
        File drop = provisioningFile(context, keyId);
        if (drop == null || !drop.isFile()) return 0;
        byte[] raw = null;
        byte[] key = null;
        try {
            long length = drop.length();
            if (length <= 0 || length > 4096) return -1;
            raw = new byte[(int) length];
            RandomAccessFile handle = new RandomAccessFile(drop, "r");
            try {
                handle.readFully(raw);
            } finally {
                handle.close();
            }
            key = decodeKeyMaterial(raw);
            if (key == null || key.length < 32) return -1;
            return provision(context, keyId, key) ? 1 : -1;
        } catch (IOException ignored) {
            return -1;
        } finally {
            if (raw != null) Arrays.fill(raw, (byte) 0);
            if (key != null) Arrays.fill(key, (byte) 0);
            shred(drop);
        }
    }

    public static File provisioningFile(Context context, String keyId) {
        if (context == null || !validKeyId(keyId)) return null;
        File base = context.getApplicationContext().getExternalFilesDir(null);
        if (base == null) return null;
        return new File(new File(base, PROVISIONING_DIRECTORY), keyId + ".psk");
    }

    /** Accepts 32+ raw bytes or exactly 64 ASCII hex characters. */
    static byte[] decodeKeyMaterial(byte[] raw) {
        int end = raw.length;
        while (end > 0 && (raw[end - 1] == '\n' || raw[end - 1] == '\r' || raw[end - 1] == ' ' || raw[end - 1] == '\t')) end--;
        if (end == 64 && isHex(raw, end)) {
            byte[] decoded = new byte[32];
            for (int i = 0; i < 32; i++) {
                decoded[i] = (byte) ((nibble(raw[2 * i]) << 4) | nibble(raw[2 * i + 1]));
            }
            return decoded;
        }
        if (end >= 32) return Arrays.copyOf(raw, end);
        return null;
    }

    private static boolean isHex(byte[] raw, int end) {
        for (int i = 0; i < end; i++) if (nibble(raw[i]) < 0) return false;
        return true;
    }

    private static int nibble(byte value) {
        if (value >= '0' && value <= '9') return value - '0';
        if (value >= 'a' && value <= 'f') return value - 'a' + 10;
        if (value >= 'A' && value <= 'F') return value - 'A' + 10;
        return -1;
    }

    private static void shred(File file) {
        try {
            long length = file.length();
            if (length > 0 && length <= 4096) {
                FileOutputStream stream = new FileOutputStream(file, false);
                try {
                    byte[] zeros = new byte[(int) length];
                    stream.write(zeros);
                    stream.flush();
                    stream.getFD().sync();
                } finally {
                    stream.close();
                }
            }
        } catch (IOException ignored) {
            // Deletion below is still attempted.
        }
        if (!file.delete()) file.deleteOnExit();
    }

    public static synchronized byte[] load(Context context, String keyId) {
        if (!validKeyId(keyId)) return null;
        byte[] encoded = null;
        try {
            String value = preferences(context).getString(keyId, null);
            if (value == null) return null;
            encoded = Base64.decode(value, Base64.NO_WRAP);
            if (encoded.length < 2 + 12 + 16 || encoded[0] != FORMAT) return null;
            int ivLength = encoded[1] & 0xff;
            if (ivLength < 12 || ivLength > 32 || encoded.length <= 2 + ivLength + 16) return null;
            byte[] iv = Arrays.copyOfRange(encoded, 2, 2 + ivLength);
            byte[] ciphertext = Arrays.copyOfRange(encoded, 2 + ivLength, encoded.length);
            try {
                Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
                cipher.init(Cipher.DECRYPT_MODE, masterKey(), new GCMParameterSpec(128, iv));
                cipher.updateAAD(keyId.getBytes(StandardCharsets.US_ASCII));
                byte[] clear = cipher.doFinal(ciphertext);
                if (clear.length < 32) { Arrays.fill(clear, (byte) 0); return null; }
                return clear;
            } finally {
                Arrays.fill(iv, (byte) 0);
                Arrays.fill(ciphertext, (byte) 0);
            }
        } catch (Exception ignored) {
            return null;
        } finally {
            if (encoded != null) Arrays.fill(encoded, (byte) 0);
        }
    }

    private static SecretKey masterKey() throws Exception {
        KeyStore store = KeyStore.getInstance(KEYSTORE);
        store.load(null);
        java.security.Key existing = store.getKey(MASTER_ALIAS, null);
        if (existing instanceof SecretKey) return (SecretKey) existing;
        KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, KEYSTORE);
        generator.init(new KeyGenParameterSpec.Builder(MASTER_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setRandomizedEncryptionRequired(true)
                .build());
        return generator.generateKey();
    }

    private static SharedPreferences preferences(Context supplied) {
        if (supplied == null) throw new IllegalArgumentException("context");
        Context context = supplied.getApplicationContext();
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    private static boolean validKeyId(String value) {
        if (value == null || value.length() == 0 || value.length() > 64) return false;
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            if (!(c >= 'a' && c <= 'z') && !(c >= 'A' && c <= 'Z') &&
                    !(c >= '0' && c <= '9') && c != '-' && c != '_' && c != '.') return false;
        }
        return true;
    }
}
