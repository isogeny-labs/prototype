// Adapter wrapper for Java (OpenJDK). It only translates: the adapter's JSON in, the JDK's own calls
// (java.security: KeyPairGenerator, Signature "SHA256withECDSA", KeyFactory), JSON out. All crypto is the JDK's.
// There is no crypto of our own here. See docs/ADAPTER.md.
//
//     java EcdsaAdapter [--slow] keygen|sign|verify|info|bench      (JSON on stdin, JSON on stdout)
//
// How a "no" is reported: any error the JDK raises while checking a signature means "not accepted":
// {"valid": false}. A SignatureException is the JDK's own "bad signature"; any other error adds a note
// "general error: <ClassName>". --slow is the speed test's control: it adds 6 ms to each timed step of bench.
// bench uses the test key it is given when both halves come with it (private_key and public_key), so two versions are
// timed on the same key; the JDK cannot work out a public key from a private one without maths of our own. Otherwise
// it makes its own test key.
import java.math.BigInteger;
import java.security.*;
import java.security.interfaces.ECPrivateKey;
import java.security.interfaces.ECPublicKey;
import java.security.spec.*;
import java.util.*;

public class EcdsaAdapter {
    static final String USAGE = "usage: EcdsaAdapter [--slow] keygen|sign|verify|info|bench  (JSON on stdin, JSON on stdout)";
    // The standard DER wrapper that turns a raw P-256 point (04 || X || Y) into a public key the JDK reads.
    static final String PUBLIC_PREFIX = "3059301306072a8648ce3d020106082a8648ce3d030107034200";
    static boolean slow = false;

    // ---- a tiny reader for a flat JSON object of string and number fields
    static Map<String, String> readJson(String text) {
        Map<String, String> map = new HashMap<>();
        text = text.trim();
        if (text.isEmpty()) return map;
        if (text.charAt(0) != '{' || text.charAt(text.length() - 1) != '}') throw new IllegalArgumentException("not an object");
        int i = 1, n = text.length() - 1;
        while (true) {
            while (i < n && " \t\r\n,".indexOf(text.charAt(i)) >= 0) i++;
            if (i >= n) return map;
            String key = readString(text, i);
            i += key.length() + 2;
            i = skipTo(text, i, ':') + 1;
            while (" \t\r\n".indexOf(text.charAt(i)) >= 0) i++;
            if (text.charAt(i) == '"') {
                String value = readString(text, i);
                map.put(key, value);
                i += value.length() + 2;
            } else {
                int j = i;
                while (j < n && ",}".indexOf(text.charAt(j)) < 0) j++;
                map.put(key, text.substring(i, j).trim());
                i = j;
            }
        }
    }
    static int skipTo(String s, int i, char c) {
        while (i < s.length() && s.charAt(i) != c) {
            if (" \t\r\n".indexOf(s.charAt(i)) < 0) throw new IllegalArgumentException("bad json");
            i++;
        }
        if (i >= s.length()) throw new IllegalArgumentException("bad json");
        return i;
    }
    // The text of the string that starts with a quote at position i (hex and names only: no escapes).
    static String readString(String s, int i) {
        if (s.charAt(i) != '"') throw new IllegalArgumentException("bad json");
        int end = s.indexOf('"', i + 1);
        if (end < 0 || s.substring(i + 1, end).indexOf('\\') >= 0) throw new IllegalArgumentException("bad json");
        return s.substring(i + 1, end);
    }

    // ---- hex
    static byte[] fromHex(String hex) {
        if (hex == null || hex.length() % 2 != 0) throw new IllegalArgumentException("bad hex");
        byte[] out = new byte[hex.length() / 2];
        for (int i = 0; i < out.length; i++) {
            int hi = Character.digit(hex.charAt(2 * i), 16), lo = Character.digit(hex.charAt(2 * i + 1), 16);
            if (hi < 0 || lo < 0) throw new IllegalArgumentException("bad hex");
            out[i] = (byte) (hi * 16 + lo);
        }
        return out;
    }
    static String toHex(byte[] bytes) {
        StringBuilder sb = new StringBuilder();
        for (byte b : bytes) sb.append(String.format("%02x", b & 0xff));
        return sb.toString();
    }
    static String padded(BigInteger value) {
        String hex = value.toString(16);
        return "0".repeat(64 - hex.length()) + hex;
    }
    static byte[] need(Map<String, String> req, String field) {
        return fromHex(Objects.requireNonNull(req.get(field), "missing field").toString());
    }

    // ---- keys
    static ECParameterSpec p256() throws GeneralSecurityException {
        AlgorithmParameters parameters = AlgorithmParameters.getInstance("EC");
        parameters.init(new ECGenParameterSpec("secp256r1"));
        return parameters.getParameterSpec(ECParameterSpec.class);
    }
    static KeyPair generate() throws GeneralSecurityException {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("EC");
        generator.initialize(new ECGenParameterSpec("secp256r1"));
        return generator.generateKeyPair();
    }
    static String publicHex(KeyPair pair) {
        java.security.spec.ECPoint w = ((ECPublicKey) pair.getPublic()).getW();
        return "04" + padded(w.getAffineX()) + padded(w.getAffineY());
    }
    static PublicKey publicKey(byte[] point) throws GeneralSecurityException {
        return KeyFactory.getInstance("EC").generatePublic(new X509EncodedKeySpec(fromHex(PUBLIC_PREFIX + toHex(point))));
    }
    static PrivateKey privateKey(byte[] scalar) throws GeneralSecurityException {
        return KeyFactory.getInstance("EC").generatePrivate(new ECPrivateKeySpec(new BigInteger(1, scalar), p256()));
    }
    static byte[] sign(PrivateKey key, byte[] message) throws GeneralSecurityException {
        Signature signature = Signature.getInstance("SHA256withECDSA");
        signature.initSign(key);
        signature.update(message);
        return signature.sign();
    }
    static boolean verify(PublicKey key, byte[] message, byte[] sig) throws GeneralSecurityException {
        Signature signature = Signature.getInstance("SHA256withECDSA");
        signature.initVerify(key);
        signature.update(message);
        return signature.verify(sig);
    }
    static void busyWait(double ms) {
        long end = System.nanoTime() + (long) (ms * 1e6);
        while (System.nanoTime() < end) { }
    }

    // ---- commands (each returns the JSON text of its answer)
    static String info() {
        return "{\"name\": \"openjdk\", \"version\": \"" + System.getProperty("java.version") + "\", \"algorithm\": \"ECDSA P-256\", "
            + "\"hash\": \"SHA-256\", \"signature_format\": \"DER\", \"public_key_format\": \"uncompressed point, hex (04 || X || Y)\", "
            + "\"commands\": [\"keygen\", \"sign\", \"verify\", \"info\", \"bench\"], \"library\": \"OpenJDK "
            + System.getProperty("java.runtime.version") + " (" + System.getProperty("java.vendor") + ")\"}";
    }
    static String keygen(Map<String, String> req) throws GeneralSecurityException {
        String algorithm = req.getOrDefault("algorithm", "ECDSA P-256");
        if (!algorithm.equals("ECDSA P-256")) {
            // Phase 4d: asked for another algorithm, ask the JDK itself whether it has it.
            try {
                KeyPairGenerator.getInstance(algorithm);
            } catch (NoSuchAlgorithmException refused) {
                String note = String.valueOf(refused.getMessage()).replaceAll("[^A-Za-z0-9 ._:()-]", "?");
                return "{\"refused\": true, \"note\": \"" + note + "\"}";
            }
            return "{\"error\": \"bad input: this wrapper only makes ECDSA P-256 keys\"}";
        }
        KeyPair pair = generate();
        return "{\"private_key\": \"" + padded(((ECPrivateKey) pair.getPrivate()).getS()) + "\", \"public_key\": \"" + publicHex(pair) + "\"}";
    }
    static String sign(Map<String, String> req) throws GeneralSecurityException {
        return "{\"signature\": \"" + toHex(sign(privateKey(need(req, "private_key")), need(req, "message"))) + "\"}";
    }
    static String verify(Map<String, String> req) {
        byte[] point = need(req, "public_key"), message = need(req, "message"), sig = need(req, "signature");
        try {
            PublicKey key;
            try {
                key = publicKey(point);
            } catch (GeneralSecurityException | RuntimeException refused) {
                return "{\"valid\": false, \"note\": \"the library refused the public key\"}";
            }
            return "{\"valid\": " + verify(key, message, sig) + "}";
        } catch (SignatureException bad) {
            return "{\"valid\": false}";
        } catch (Exception other) {
            return "{\"valid\": false, \"note\": \"general error: " + other.getClass().getSimpleName() + "\"}";
        }
    }
    static String bench(Map<String, String> req) throws GeneralSecurityException {
        int repeats = req.containsKey("repeats") ? Integer.parseInt(req.get("repeats")) : 100;
        if (repeats < 1 || repeats > 1000) throw new IllegalArgumentException("repeats");
        byte[] message = req.containsKey("message") ? fromHex(req.get("message")) : new byte[0];
        PrivateKey signer;
        PublicKey checker;
        if (req.containsKey("private_key") && req.containsKey("public_key")) {
            signer = privateKey(need(req, "private_key"));
            checker = publicKey(need(req, "public_key"));
        } else {
            KeyPair pair = generate();
            signer = pair.getPrivate();
            checker = pair.getPublic();
        }
        for (int i = 0; i < 2; i++) verify(checker, message, sign(signer, message));
        StringBuilder signMs = new StringBuilder(), verifyMs = new StringBuilder();
        boolean all = true;
        int size = 0;
        for (int i = 0; i < repeats; i++) {
            long t0 = System.nanoTime();
            if (slow) busyWait(6);
            byte[] sig = sign(signer, message);
            long t1 = System.nanoTime();
            if (slow) busyWait(6);
            boolean ok = verify(checker, message, sig);
            long t2 = System.nanoTime();
            all &= ok;
            size = sig.length;
            signMs.append(i > 0 ? ", " : "").append(Math.round((t1 - t0) / 100.0) / 10000.0);
            verifyMs.append(i > 0 ? ", " : "").append(Math.round((t2 - t1) / 100.0) / 10000.0);
        }
        return "{\"repeats\": " + repeats + ", \"warmups\": 2, \"clock\": \"System.nanoTime\", \"sign_ms\": [" + signMs + "], \"verify_ms\": ["
            + verifyMs + "], \"signature_bytes\": " + size + ", \"public_key_bytes\": 65, \"all_verified\": " + all + "}";
    }

    public static void main(String[] args) throws Exception {
        List<String> words = new ArrayList<>(Arrays.asList(args));
        if (!words.isEmpty() && words.get(0).equals("--slow")) { slow = true; words.remove(0); }
        if (words.size() != 1 || !List.of("keygen", "sign", "verify", "info", "bench").contains(words.get(0))) {
            System.out.println("{\"error\": \"" + USAGE + "\"}");
            System.exit(2);
        }
        String out;
        try {
            Map<String, String> req = readJson(new String(System.in.readAllBytes(), "UTF-8"));
            switch (words.get(0)) {
                case "keygen": out = keygen(req); break;
                case "sign": out = sign(req); break;
                case "verify": out = verify(req); break;
                case "bench": out = bench(req); break;
                default: out = info();
            }
        } catch (Exception exc) {
            // Never repeat the input here: it may hold a test private key.
            System.out.println("{\"error\": \"bad input: " + exc.getClass().getSimpleName() + "\"}");
            System.exit(1);
            return;
        }
        System.out.println(out);
    }
}
