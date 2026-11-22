//! Constant-time CNSA 2.0 algorithm suite.
//!
//! Rules every module in this crate follows (see `docs/CTCRYPTO.md`):
//!
//! 1. No branch, array index, loop bound, division or remainder may depend on
//!    secret data. Selection is done with masks from [`ct`].
//! 2. Secret-dependent `/` and `%` are forbidden even by constants: use
//!    Barrett/Montgomery multiplication and shifts.
//! 3. No lookup tables indexed by secrets (AES uses an algebraic S-box).
//! 4. Every place a secret-derived value becomes public goes through
//!    [`ct::declassify`] with a comment saying why it is public.
//! 5. Secret temporaries are wiped with [`ct::zeroize`] before return.
//! 6. No `unsafe`, no allocation, no dependencies, `no_std`.
//!
//! The crate takes all randomness from the caller (the `*_internal`
//! derandomized interfaces of FIPS 203/204); it contains no RNG.
#![no_std]
#![cfg_attr(not(feature = "ctgrind"), forbid(unsafe_code))]
#![deny(missing_docs)]

pub mod ct;
pub mod sha2;
pub mod sha3;

#[cfg(feature = "aes")]
pub mod aes;
#[cfg(feature = "lms")]
pub mod lms;
#[cfg(feature = "mldsa")]
pub mod mldsa;
#[cfg(feature = "mlkem")]
pub mod mlkem;
#[cfg(feature = "xmss")]
pub mod xmss;

/// Errors returned by this crate. Variants carry no secret-dependent detail.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Error {
    /// An input had the wrong length or failed a public validity check.
    InvalidInput,
    /// Authentication (AEAD tag) or signature verification failed.
    VerificationFailed,
    /// A parameter set or type code is not supported.
    Unsupported,
}
