//! `ctcheck <case> [iterations]`
//!
//! Runs one operation with its secret inputs marked "undefined" for valgrind
//! memcheck. Memcheck then reports every conditional jump and every memory
//! address that depends on a secret. `run.sh` runs each case under valgrind
//! and requires: clean cases report nothing, leaky controls are reported.
//!
//! What this does not see: instructions whose *duration* depends on operand
//! values without a branch (hardware division, some multipliers). `run.sh`
//! covers division with a disassembly scan.

use core::hint::black_box;
use ctcrypto::sha3::Sponge;

extern "C" {
    fn ctcheck_poison(p: *mut u8, n: usize);
    fn ctcheck_on_valgrind() -> i32;
}

fn poison(buf: &mut [u8]) {
    // SAFETY: valid exclusive region.
    unsafe { ctcheck_poison(buf.as_mut_ptr(), buf.len()) }
}

/// Public, deterministic input bytes (drawn before anything is poisoned).
struct Gen(Sponge);
impl Gen {
    fn new(case: &str, iter: u32) -> Self {
        let mut s = Sponge::shake256();
        s.absorb(b"ctcheck-v1/");
        s.absorb(case.as_bytes());
        s.absorb(&iter.to_le_bytes());
        Gen(s)
    }
    fn fill(&mut self, out: &mut [u8]) {
        self.0.squeeze(out);
    }
    fn arr<const N: usize>(&mut self) -> [u8; N] {
        let mut a = [0u8; N];
        self.fill(&mut a);
        a
    }
}

// ---- positive controls: each MUST be reported by valgrind -----------------

#[inline(never)]
fn control_branch(secret: &[u8]) -> u32 {
    // A secret loop bound: the optimizer cannot make this branch-free.
    let mut n = 0u32;
    for &b in secret {
        for _ in 0..(black_box(b) & 7) {
            n = black_box(n).wrapping_mul(31).wrapping_add(7);
        }
    }
    n
}

static TABLE: [u8; 256] = {
    let mut t = [0u8; 256];
    let mut i = 0;
    while i < 256 {
        t[i] = (i as u8).wrapping_mul(167).wrapping_add(13);
        i += 1;
    }
    t
};

#[inline(never)]
fn control_index(secret: &[u8]) -> u8 {
    let mut acc = 0u8;
    for &b in secret {
        acc ^= black_box(&TABLE)[black_box(b) as usize];
    }
    acc
}

#[inline(never)]
fn control_memcmp(a: &[u8], b: &[u8]) -> bool {
    black_box(a) == black_box(b)
}

fn run(case: &str, it: u32) {
    let mut g = Gen::new(case, it);
    match case {
        // ---- controls ----
        "control-branch" => {
            let mut s: [u8; 32] = g.arr();
            poison(&mut s);
            black_box(control_branch(&s));
        }
        "control-index" => {
            let mut s: [u8; 32] = g.arr();
            poison(&mut s);
            black_box(control_index(&s));
        }
        "control-memcmp" => {
            let mut a: [u8; 32] = g.arr();
            let b = a;
            poison(&mut a);
            black_box(control_memcmp(&a, &b));
        }
        // ---- clean: shared core ----
        "ct-eq-cmov" => {
            let mut a: [u8; 64] = g.arr();
            let mut b: [u8; 64] = if it % 2 == 0 { a } else { g.arr() };
            poison(&mut a);
            poison(&mut b);
            let m = ctcrypto::ct::eq(&a, &b);
            let mut d = [0u8; 64];
            ctcrypto::ct::cmov(&mut d, &a, m);
            black_box(d);
        }
        "sha384" => {
            let mut m = [0u8; 300];
            g.fill(&mut m);
            poison(&mut m);
            black_box(ctcrypto::sha2::Sha384::digest(&m[..(it as usize * 37) % 300]));
        }
        "sha512" => {
            let mut m = [0u8; 300];
            g.fill(&mut m);
            poison(&mut m);
            black_box(ctcrypto::sha2::Sha512::digest(&m[..(it as usize * 53) % 300]));
        }
        "sha256" => {
            let mut m = [0u8; 300];
            g.fill(&mut m);
            poison(&mut m);
            black_box(ctcrypto::sha2::Sha256::digest(&m[..(it as usize * 41) % 300]));
        }
        "shake256" => {
            let mut m = [0u8; 300];
            g.fill(&mut m);
            poison(&mut m);
            let mut out = [0u8; 200];
            ctcrypto::sha3::shake256(&m[..(it as usize * 59) % 300], &mut out);
            black_box(out);
        }
        // ---- AES ----
        #[cfg(feature = "aes")]
        "aes256-block" => {
            let mut key: [u8; 32] = g.arr();
            let mut blk: [u8; 16] = g.arr();
            poison(&mut key);
            poison(&mut blk);
            let aes = ctcrypto::aes::Aes256::new(&key);
            aes.encrypt_block(&mut blk);
            aes.decrypt_block(&mut blk);
            black_box(blk);
        }
        #[cfg(feature = "aes")]
        "gcm-seal" => {
            let mut key: [u8; 32] = g.arr();
            let nonce: [u8; 12] = g.arr();
            let aad: [u8; 40] = g.arr();
            let mut data = [0u8; 257];
            g.fill(&mut data);
            let n = (it as usize * 67) % 258;
            poison(&mut key);
            poison(&mut data);
            let tag = ctcrypto::aes::gcm::seal(&key, &nonce, &aad[..n % 41], &mut data[..n]);
            black_box((tag, data));
        }
        #[cfg(feature = "aes")]
        "gcm-open" => {
            // Sealed with a public copy of the key; opened with the key secret.
            let key_pub: [u8; 32] = g.arr();
            let nonce: [u8; 12] = g.arr();
            let aad: [u8; 40] = g.arr();
            let mut data = [0u8; 257];
            g.fill(&mut data);
            let n = (it as usize * 67) % 258;
            let mut tag = ctcrypto::aes::gcm::seal(&key_pub, &nonce, &aad[..n % 41], &mut data[..n]);
            if it % 2 == 1 {
                tag[3] ^= 0x10; // forged: the reject path must also be clean
            }
            let mut key = key_pub;
            poison(&mut key);
            let r = ctcrypto::aes::gcm::open(&key, &nonce, &aad[..n % 41], &mut data[..n], &tag);
            assert_eq!(r.is_ok(), it % 2 == 0);
            black_box(data);
        }
        // ---- ML-KEM-1024 ----
        #[cfg(feature = "mlkem")]
        "mlkem-keygen" => {
            let mut d: [u8; 32] = g.arr();
            let mut z: [u8; 32] = g.arr();
            poison(&mut d);
            poison(&mut z);
            black_box(ctcrypto::mlkem::keygen_internal(&d, &z));
        }
        #[cfg(feature = "mlkem")]
        "mlkem-encaps" => {
            let (ek, _dk) = ctcrypto::mlkem::keygen_internal(&g.arr(), &g.arr());
            let mut m: [u8; 32] = g.arr();
            poison(&mut m);
            black_box(ctcrypto::mlkem::encaps_internal(&ek, &m).unwrap());
        }
        #[cfg(feature = "mlkem")]
        "mlkem-decaps" => {
            use ctcrypto::mlkem::*;
            let (ek, mut dk) = keygen_internal(&g.arr(), &g.arr());
            let (mut c, _ss) = encaps_internal(&ek, &g.arr()).unwrap();
            if it % 2 == 1 {
                c[(it as usize * 131) % CT_LEN] ^= 0x04; // implicit-rejection path
            }
            // dk = dk_pke (secret) || ek (public) || H(ek) (public) || z (secret)
            poison(&mut dk[..1536]);
            poison(&mut dk[DK_LEN - 32..]);
            black_box(decaps(&dk, &c).unwrap());
        }
        // ---- ML-DSA-87 ----
        #[cfg(feature = "mldsa")]
        "mldsa-keygen" => {
            let mut xi: [u8; 32] = g.arr();
            poison(&mut xi);
            black_box(ctcrypto::mldsa::keygen_internal(&xi));
        }
        #[cfg(feature = "mldsa")]
        "mldsa-sign" => {
            use ctcrypto::mldsa::*;
            let (_pk, mut sk) = keygen_internal(&g.arr());
            let msg: [u8; 100] = g.arr();
            let mut rnd: [u8; 32] = if it % 2 == 0 { [0u8; 32] } else { g.arr() };
            // sk = rho (public) || K (secret) || tr (public) || s1 || s2 || t0 (secret)
            poison(&mut sk[32..64]);
            poison(&mut sk[128..]);
            poison(&mut rnd);
            black_box(sign_internal(&sk, &msg[..(it as usize * 13) % 101], &rnd));
        }
        _ => {
            eprintln!("unknown case {case}");
            std::process::exit(2);
        }
    }
}

const CASES: &[&str] = &[
    "control-branch",
    "control-index",
    "control-memcmp",
    "ct-eq-cmov",
    "sha256",
    "sha384",
    "sha512",
    "shake256",
    #[cfg(feature = "aes")]
    "aes256-block",
    #[cfg(feature = "aes")]
    "gcm-seal",
    #[cfg(feature = "aes")]
    "gcm-open",
    #[cfg(feature = "mlkem")]
    "mlkem-keygen",
    #[cfg(feature = "mlkem")]
    "mlkem-encaps",
    #[cfg(feature = "mlkem")]
    "mlkem-decaps",
    #[cfg(feature = "mldsa")]
    "mldsa-keygen",
    #[cfg(feature = "mldsa")]
    "mldsa-sign",
];

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 2 || args[1] == "list" {
        for c in CASES {
            println!("{c}");
        }
        return;
    }
    let iters: u32 = args.get(2).and_then(|s| s.parse().ok()).unwrap_or(4);
    // SAFETY: no arguments.
    let on_vg = unsafe { ctcheck_on_valgrind() } != 0;
    println!("case={} iterations={} valgrind={}", args[1], iters, on_vg);
    for it in 0..iters {
        run(&args[1], it);
    }
}
