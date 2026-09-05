package dev.phantom.security;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;

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
