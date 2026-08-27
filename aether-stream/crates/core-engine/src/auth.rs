//! Launch authentication for the local vault.
//!
//! The verifier is an Argon2id PHC string. The plaintext password exists only
//! for the duration of a call and is held in `Zeroizing`; it is never written
//! to SQLite, logs, events, or sync operations. The SQLCipher database stores
//! the verifier only after the database itself has been opened with a key from
//! the platform keychain.

use std::time::{Duration, Instant};

use argon2::{
    password_hash::{rand_core::OsRng, PasswordHash, PasswordHasher, PasswordVerifier, SaltString},
    Algorithm, Argon2, Params, Version,
};
use serde::Serialize;
use thiserror::Error;
use zeroize::Zeroizing;

const MIN_PASSWORD_LEN: usize = 10;
const MAX_FAILURES: u32 = 5;
const LOCKOUT_DURATION: Duration = Duration::from_secs(30);

#[derive(Debug, Clone, Serialize)]
pub struct AuthStatus {
    pub configured: bool,
    pub unlocked: bool,
    pub biometric_available: bool,
    pub failed_attempts: u32,
    pub retry_after_seconds: u64,
}

#[derive(Debug, Error)]
pub enum AuthError {
    #[error("password must contain at least {MIN_PASSWORD_LEN} characters")]
    WeakPassword,
    #[error("vault authentication is not configured")]
    NotConfigured,
    #[error("vault is already configured")]
    AlreadyConfigured,
    #[error("invalid password")]
    InvalidCredentials,
    #[error("too many failed attempts; retry in {seconds} seconds")]
    LockedOut { seconds: u64 },
    #[error("stored Argon2id verifier is malformed")]
    InvalidVerifier,
    #[error("biometric authentication is not available on this build")]
    BiometricUnavailable,
    #[error("biometric authentication failed")]
    BiometricFailed,
}

/// Platform adapter implemented by the Tauri shell for Windows Hello, Touch
/// ID, or a Linux PAM/desktop portal. The core never handles biometric data.
pub trait BiometricAuthenticator: Send + Sync {
    fn authenticate(&self, reason: &str) -> Result<(), AuthError>;
}

#[derive(Debug)]
pub struct AuthController {
    password_hash: Option<String>,
    unlocked: bool,
    failed_attempts: u32,
    lockout_until: Option<Instant>,
    biometric_available: bool,
}

impl AuthController {
    pub fn unconfigured() -> Self {
        Self {
            password_hash: None,
            unlocked: false,
            failed_attempts: 0,
            lockout_until: None,
            biometric_available: false,
        }
    }

    pub fn from_hash(password_hash: Option<String>) -> Result<Self, AuthError> {
        if let Some(hash) = &password_hash {
            PasswordHash::new(hash).map_err(|_| AuthError::InvalidVerifier)?;
        }
        Ok(Self {
            password_hash,
            unlocked: false,
            failed_attempts: 0,
            lockout_until: None,
            biometric_available: false,
        })
    }

    pub fn password_hash(&self) -> Option<&str> {
        self.password_hash.as_deref()
    }

    pub fn set_biometric_available(&mut self, available: bool) {
        self.biometric_available = available;
    }

    pub fn status(&mut self) -> AuthStatus {
        self.clear_expired_lockout();
        AuthStatus {
            configured: self.password_hash.is_some(),
            unlocked: self.unlocked,
            biometric_available: self.biometric_available,
            failed_attempts: self.failed_attempts,
            retry_after_seconds: self.retry_after_seconds(),
        }
    }

    pub fn enroll_password(&mut self, password: &str) -> Result<String, AuthError> {
        if self.password_hash.is_some() {
            return Err(AuthError::AlreadyConfigured);
        }
        let hash = hash_password(password)?;
        self.password_hash = Some(hash.clone());
        self.failed_attempts = 0;
        self.lockout_until = None;
        self.unlocked = true;
        Ok(hash)
    }

    pub fn verify_password(&mut self, password: &str) -> Result<AuthStatus, AuthError> {
        self.clear_expired_lockout();
        if let Some(seconds) = self.lockout_seconds() {
            return Err(AuthError::LockedOut { seconds });
        }

        let stored = self
            .password_hash
            .as_deref()
            .ok_or(AuthError::NotConfigured)?;
        let password = Zeroizing::new(password.to_owned());
        let parsed = PasswordHash::new(stored).map_err(|_| AuthError::InvalidVerifier)?;

        match argon2id().verify_password(password.as_bytes(), &parsed) {
            Ok(()) => {
                self.failed_attempts = 0;
                self.unlocked = true;
                Ok(self.status())
            }
            Err(_) => {
                self.failed_attempts = self.failed_attempts.saturating_add(1);
                if self.failed_attempts >= MAX_FAILURES {
                    self.lockout_until = Some(Instant::now() + LOCKOUT_DURATION);
                }
                Err(if let Some(seconds) = self.lockout_seconds() {
                    AuthError::LockedOut { seconds }
                } else {
                    AuthError::InvalidCredentials
                })
            }
        }
    }

    pub fn verify_biometric(
        &mut self,
        authenticator: &dyn BiometricAuthenticator,
    ) -> Result<AuthStatus, AuthError> {
        if self.password_hash.is_none() {
            return Err(AuthError::NotConfigured);
        }
        if !self.biometric_available {
            return Err(AuthError::BiometricUnavailable);
        }
        authenticator.authenticate("Unlock the AETHER-STREAM vault")?;
        self.mark_biometric_authenticated()
    }

    /// Complete the core side of a platform biometric flow after the native
    /// adapter has returned success. The Tauri shell invokes the platform
    /// prompt first, then calls this method; biometric material never enters
    /// the core.
    pub fn mark_biometric_authenticated(&mut self) -> Result<AuthStatus, AuthError> {
        if self.password_hash.is_none() {
            return Err(AuthError::NotConfigured);
        }
        if !self.biometric_available {
            return Err(AuthError::BiometricUnavailable);
        }
        self.unlocked = true;
        self.failed_attempts = 0;
        Ok(self.status())
    }

    pub fn lock(&mut self) {
        self.unlocked = false;
    }

    pub fn is_unlocked(&mut self) -> bool {
        self.status().unlocked
    }

    fn clear_expired_lockout(&mut self) {
        if self
            .lockout_until
            .map(|deadline| Instant::now() >= deadline)
            .unwrap_or(false)
        {
            self.lockout_until = None;
            self.failed_attempts = 0;
        }
    }

    fn lockout_seconds(&self) -> Option<u64> {
        self.lockout_until.map(|deadline| {
            deadline
                .saturating_duration_since(Instant::now())
                .as_secs()
                .max(1)
        })
    }

    fn retry_after_seconds(&self) -> u64 {
        self.lockout_seconds().unwrap_or(0)
    }
}

fn argon2id() -> Argon2<'static> {
    Argon2::new(Algorithm::Argon2id, Version::V0x13, Params::default())
}

fn hash_password(password: &str) -> Result<String, AuthError> {
    if password.chars().count() < MIN_PASSWORD_LEN {
        return Err(AuthError::WeakPassword);
    }
    let password = Zeroizing::new(password.to_owned());
    let salt = SaltString::generate(&mut OsRng);
    argon2id()
        .hash_password(password.as_bytes(), &salt)
        .map(|hash| hash.to_string())
        .map_err(|_| AuthError::InvalidVerifier)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn password_enrollment_and_verification_are_argon2id_backed() {
        let mut auth = AuthController::unconfigured();
        let hash = auth.enroll_password("correct horse battery staple").unwrap();
        assert!(hash.starts_with("$argon2id$"));
        assert!(auth.is_unlocked());

        auth.lock();
        assert!(!auth.is_unlocked());
        assert!(auth.verify_password("incorrect password").is_err());
        assert!(auth.verify_password("correct horse battery staple").is_ok());
    }

    #[test]
    fn weak_passwords_are_rejected_before_hashing() {
        let mut auth = AuthController::unconfigured();
        assert!(matches!(
            auth.enroll_password("short"),
            Err(AuthError::WeakPassword)
        ));
    }
}
