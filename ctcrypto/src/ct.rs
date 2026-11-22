//! Constant-time primitives. Everything secret-dependent in the crate is built
//! from these. `core::hint::black_box` is used as a value barrier so the
//! optimizer cannot turn a mask back into a branch; the compiled result is
//! checked under valgrind by `ctcheck` rather than trusted.

use core::hint::black_box;

/// All-ones if `x != 0`, else zero.
#[inline]
pub fn mask_nonzero_u32(x: u32) -> u32 {
    let x = black_box(x);
    ((x | x.wrapping_neg()) >> 31).wrapping_neg()
}

/// All-ones if `x != 0`, else zero.
#[inline]
pub fn mask_nonzero_u64(x: u64) -> u64 {
    let x = black_box(x);
    ((x | x.wrapping_neg()) >> 63).wrapping_neg()
}

/// All-ones if `a == b`, else zero.
#[inline]
pub fn mask_eq_u32(a: u32, b: u32) -> u32 {
    !mask_nonzero_u32(a ^ b)
}

/// All-ones if `a < b` (unsigned), else zero.
#[inline]
pub fn mask_lt_u32(a: u32, b: u32) -> u32 {
    let d = (black_box(a) as u64).wrapping_sub(black_box(b) as u64);
    ((d >> 63) as u32).wrapping_neg()
}

/// All-ones if `a < b` (signed), else zero.
#[inline]
pub fn mask_lt_i32(a: i32, b: i32) -> u32 {
    let d = (black_box(a) as i64).wrapping_sub(black_box(b) as i64);
    (((d as u64) >> 63) as u32).wrapping_neg()
}

/// All-ones if `x < 0`, else zero.
#[inline]
pub fn mask_neg_i32(x: i32) -> u32 {
    ((black_box(x) as u32) >> 31).wrapping_neg()
}

/// `a` if `mask` is all-ones, `b` if `mask` is zero.
#[inline]
pub fn select_u32(mask: u32, a: u32, b: u32) -> u32 {
    b ^ (black_box(mask) & (a ^ b))
}

/// `a` if `mask` is all-ones, `b` if `mask` is zero.
#[inline]
pub fn select_i32(mask: u32, a: i32, b: i32) -> i32 {
    select_u32(mask, a as u32, b as u32) as i32
}

/// `a` if `mask` is all-ones, `b` if `mask` is zero.
#[inline]
pub fn select_u64(mask: u64, a: u64, b: u64) -> u64 {
    b ^ (black_box(mask) & (a ^ b))
}

/// `0xff` if the slices are equal, else `0x00`. Lengths are public; unequal
/// lengths return `0x00`.
#[must_use]
pub fn eq(a: &[u8], b: &[u8]) -> u8 {
    if a.len() != b.len() {
        return 0;
    }
    let mut acc = 0u8;
    for (x, y) in a.iter().zip(b.iter()) {
        acc |= x ^ y;
    }
    !(mask_nonzero_u32(acc as u32) as u8)
}

/// Copies `src` into `dst` if `mask == 0xff`; leaves `dst` unchanged if
/// `mask == 0x00`. Lengths are public and must match.
pub fn cmov(dst: &mut [u8], src: &[u8], mask: u8) {
    assert_eq!(dst.len(), src.len());
    let m = black_box(mask);
    for (d, s) in dst.iter_mut().zip(src.iter()) {
        *d ^= m & (*d ^ *s);
    }
}

/// Overwrites a secret byte buffer with zeros in a way the optimizer keeps.
pub fn zeroize(buf: &mut [u8]) {
    for b in buf.iter_mut() {
        *b = 0;
    }
    black_box(buf);
}

/// Overwrites a secret `u64` buffer with zeros.
pub fn zeroize_u64(buf: &mut [u64]) {
    for b in buf.iter_mut() {
        *b = 0;
    }
    black_box(buf);
}

/// Overwrites a secret `u32` buffer with zeros.
pub fn zeroize_u32(buf: &mut [u32]) {
    for b in buf.iter_mut() {
        *b = 0;
    }
    black_box(buf);
}

/// Overwrites a secret `i32` buffer with zeros.
pub fn zeroize_i32(buf: &mut [i32]) {
    for b in buf.iter_mut() {
        *b = 0;
    }
    black_box(buf);
}

/// Overwrites a secret `i16` buffer with zeros.
pub fn zeroize_i16(buf: &mut [i16]) {
    for b in buf.iter_mut() {
        *b = 0;
    }
    black_box(buf);
}

#[cfg(feature = "ctgrind")]
extern "C" {
    fn ctcrypto_declassify(ptr: *mut u8, len: usize);
}

/// Marks bytes as public. A no-op in normal builds. Under the `ctgrind`
/// feature it tells valgrind the bytes are defined, so that later branches on
/// them are not reported. Call it only where the specification makes the value
/// public, and say why at the call site.
#[inline]
pub fn declassify(buf: &mut [u8]) {
    #[cfg(feature = "ctgrind")]
    // SAFETY: `buf` is a valid, exclusively borrowed region of `buf.len()` bytes.
    unsafe {
        ctcrypto_declassify(buf.as_mut_ptr(), buf.len());
    }
    #[cfg(not(feature = "ctgrind"))]
    let _ = buf;
}

/// Declassifies one `u8` value (for example an accept/reject flag).
#[inline]
pub fn declassify_u8(x: u8) -> u8 {
    let mut b = [x];
    declassify(&mut b);
    b[0]
}

/// Declassifies one `u32` value.
#[inline]
pub fn declassify_u32(x: u32) -> u32 {
    let mut b = x.to_ne_bytes();
    declassify(&mut b);
    u32::from_ne_bytes(b)
}

/// Declassifies a slice of `i32` values in place.
pub fn declassify_i32s(xs: &mut [i32]) {
    for x in xs.iter_mut() {
        *x = declassify_u32(*x as u32) as i32;
    }
}

/// Declassifies a slice of `i16` values in place.
pub fn declassify_i16s(xs: &mut [i16]) {
    for x in xs.iter_mut() {
        *x = declassify_u32(*x as u16 as u32) as u16 as i16;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn masks() {
        assert_eq!(mask_nonzero_u32(0), 0);
        assert_eq!(mask_nonzero_u32(1), u32::MAX);
        assert_eq!(mask_nonzero_u32(0x8000_0000), u32::MAX);
        assert_eq!(mask_nonzero_u64(0), 0);
        assert_eq!(mask_nonzero_u64(1 << 63), u64::MAX);
        assert_eq!(mask_eq_u32(7, 7), u32::MAX);
        assert_eq!(mask_eq_u32(7, 8), 0);
        assert_eq!(mask_lt_u32(1, 2), u32::MAX);
        assert_eq!(mask_lt_u32(2, 1), 0);
        assert_eq!(mask_lt_u32(2, 2), 0);
        assert_eq!(mask_lt_u32(0, u32::MAX), u32::MAX);
        assert_eq!(mask_lt_i32(-5, 3), u32::MAX);
        assert_eq!(mask_lt_i32(3, -5), 0);
        assert_eq!(mask_lt_i32(i32::MIN, i32::MAX), u32::MAX);
        assert_eq!(mask_neg_i32(-1), u32::MAX);
        assert_eq!(mask_neg_i32(0), 0);
        assert_eq!(select_u32(u32::MAX, 1, 2), 1);
        assert_eq!(select_u32(0, 1, 2), 2);
        assert_eq!(select_i32(u32::MAX, -1, 2), -1);
    }

    #[test]
    fn bytes() {
        assert_eq!(eq(b"abc", b"abc"), 0xff);
        assert_eq!(eq(b"abc", b"abd"), 0);
        assert_eq!(eq(b"abc", b"ab"), 0);
        let mut d = [1u8, 2, 3];
        cmov(&mut d, &[9, 9, 9], 0);
        assert_eq!(d, [1, 2, 3]);
        cmov(&mut d, &[9, 8, 7], 0xff);
        assert_eq!(d, [9, 8, 7]);
        zeroize(&mut d);
        assert_eq!(d, [0, 0, 0]);
    }
}
