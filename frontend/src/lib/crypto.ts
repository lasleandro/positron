/**
 * Client-side cryptography. The server never sees a PDF in clear text or a usable key.
 *
 * - Password -> PBKDF2-SHA-256 (600k) -> HKDF -> {authentication credential, password key}.
 * - Vault key: random 256-bit, sealed twice in the browser: by the password key and by a key
 *   derived from a random recovery code shown once at sign-up. Reset = re-seal, never re-encrypt.
 * - Each PDF: random 256-bit data key, AES-GCM, sealed again with the vault key.
 * - Consultation: ECDH P-256 between the office browser and the owner's phone,
 *   HKDF(salt = pairing code) -> AES-GCM key that re-wraps only the chosen data keys.
 *
 * Envelope format (must match exams/crypto_format.py): 0x01 | iv(12) | ciphertext+tag.
 * Every seal binds `purpose:id` as AES-GCM additional data.
 */

const PREFIX = "meus-exames:v1:";
const PBKDF2_ITERATIONS = 600_000;
const ENVELOPE_VERSION = 1;

export type Purpose = "pdf" | "owner" | "recipient" | "link" | "vault-password" | "vault-recovery" | "meta-title" | "meta-issuer";

const text = (value: string) => new TextEncoder().encode(value);
const random = (length: number) => crypto.getRandomValues(new Uint8Array(length));

export function encode(bytes: ArrayBuffer | Uint8Array): string {
  const view = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  let binary = "";
  for (const byte of view) binary += String.fromCharCode(byte);
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
}

export function decode(value: string): Uint8Array<ArrayBuffer> {
  return Uint8Array.from(atob(value.replaceAll("-", "+").replaceAll("_", "/")), (char) => char.charCodeAt(0));
}

export const aesKey = (raw: Uint8Array<ArrayBuffer>) =>
  crypto.subtle.importKey("raw", raw, "AES-GCM", false, ["encrypt", "decrypt"]);

export async function deriveCredentials(namespace: string, username: string, password: string) {
  const input = await crypto.subtle.importKey("raw", text(password), "PBKDF2", false, ["deriveBits"]);
  const salt = text(PREFIX + namespace + ":" + username);
  const stretched = await crypto.subtle.deriveBits(
    { name: "PBKDF2", hash: "SHA-256", salt, iterations: PBKDF2_ITERATIONS }, input, 256,
  );
  const root = await crypto.subtle.importKey("raw", stretched, "HKDF", false, ["deriveBits"]);
  const derive = (purpose: string) => crypto.subtle.deriveBits(
    { name: "HKDF", hash: "SHA-256", salt, info: text(PREFIX + purpose) }, root, 256,
  );
  // The "vault" label is kept from v1 so existing vectors hold; it now keys the sealed vault copy.
  const [authentication, passwordKey] = await Promise.all([derive("authentication"), derive("vault")]);
  return { authentication: encode(authentication), passwordKey: encode(passwordKey) };
}

const gcm = (iv: Uint8Array<ArrayBuffer>, purpose: Purpose, id: string): AesGcmParams => ({
  name: "AES-GCM", iv, additionalData: text(PREFIX + purpose + ":" + id),
});

export async function seal(key: CryptoKey, clear: BufferSource, purpose: Purpose, id: string) {
  const iv = random(12);
  const encrypted = await crypto.subtle.encrypt(gcm(iv, purpose, id), key, clear);
  const envelope = new Uint8Array(encrypted.byteLength + 13);
  envelope[0] = ENVELOPE_VERSION;
  envelope.set(iv, 1);
  envelope.set(new Uint8Array(encrypted), 13);
  return envelope;
}

export async function unseal(key: CryptoKey, envelope: Uint8Array<ArrayBuffer>, purpose: Purpose, id: string) {
  if (envelope.length < 29 || envelope[0] !== ENVELOPE_VERSION) throw new Error("Formato criptográfico inválido.");
  const iv = envelope.slice(1, 13);
  return new Uint8Array(await crypto.subtle.decrypt(gcm(iv, purpose, id), key, envelope.subarray(13)));
}

export const newKeyPair = () =>
  crypto.subtle.generateKey({ name: "ECDH", namedCurve: "P-256" }, true, ["deriveBits"]);

export async function exportPublic(publicKey: CryptoKey) {
  return encode(await crypto.subtle.exportKey("raw", publicKey));
}

/** First 8 bytes of SHA-256(public key), hex. Must match crypto_format.fingerprint. */
export async function publicFingerprint(publicKey: string) {
  const hash = new Uint8Array(await crypto.subtle.digest("SHA-256", decode(publicKey)));
  return Array.from(hash.subarray(0, 8), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export async function consultationKey(privateKey: CryptoKey, peerPublicKey: string, code: string) {
  const peer = await crypto.subtle.importKey(
    "raw", decode(peerPublicKey), { name: "ECDH", namedCurve: "P-256" }, false, [],
  );
  const secret = await crypto.subtle.deriveBits({ name: "ECDH", public: peer }, privateKey, 256);
  const material = await crypto.subtle.importKey("raw", secret, "HKDF", false, ["deriveKey"]);
  return crypto.subtle.deriveKey(
    { name: "HKDF", hash: "SHA-256", salt: text(code), info: text(PREFIX + "consultation") },
    material, { name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"],
  );
}

/** Encrypt a PDF for upload: returns the sealed file and its data key wrapped by the vault. */
export async function sealPdf(vault: CryptoKey, pdf: ArrayBuffer, id: string) {
  const rawKey = random(32);
  const ciphertext = await seal(await aesKey(rawKey), pdf, "pdf", id);
  const wrappedKey = encode(await seal(vault, rawKey, "owner", id));
  return { ciphertext, wrappedKey, rawKey };
}

/** Title / issuer are sealed with the document's own data key, so any grantee can read them. */
export async function sealText(rawKey: Uint8Array<ArrayBuffer>, value: string, purpose: "meta-title" | "meta-issuer", id: string) {
  return encode(await seal(await aesKey(rawKey), text(value), purpose, id));
}

export async function openText(rawKey: Uint8Array<ArrayBuffer>, sealed: string, purpose: "meta-title" | "meta-issuer", id: string) {
  if (!sealed) return "";
  return new TextDecoder().decode(await unseal(await aesKey(rawKey), decode(sealed), purpose, id));
}

/** Random key for a remote link; it travels only in the URL fragment. */
export function newLinkKey(): string {
  return encode(random(32));
}

/** 6 digits shown on both screens for a @nome request (must match exams/crypto_format.py). */
export async function comparisonCode(recipientKey: string, nonce: string): Promise<string> {
  const material = new Uint8Array([...decode(recipientKey), ...text(nonce)]);
  const digest = new DataView(await crypto.subtle.digest("SHA-256", material));
  return String(digest.getUint32(0) % 1_000_000).padStart(6, "0");
}

export async function sha256Hex(value: string): Promise<string> {
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", text(value)));
  return Array.from(digest, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

/** Decrypt a sealed PDF given its already-unwrapped data key. */
export async function openPdf(rawKey: Uint8Array<ArrayBuffer>, ciphertext: Uint8Array<ArrayBuffer>, id: string) {
  return unseal(await aesKey(rawKey), ciphertext, "pdf", id);
}

// ---------------------------------------------------------------------------
// Vault key and recovery code
// ---------------------------------------------------------------------------

const BASE32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
const RECOVERY_BYTES = 20; // 160 bits -> 32 base32 characters

/** 20 random bytes as XXXX-XXXX-... (base32, no ambiguous padding). */
export function newRecoveryCode(): string {
  let bits = "";
  for (const byte of random(RECOVERY_BYTES)) bits += byte.toString(2).padStart(8, "0");
  const chars = bits.match(/.{5}/g)!.map((chunk) => BASE32[parseInt(chunk, 2)]).join("");
  return chars.match(/.{4}/g)!.join("-");
}

/** Accepts the code with or without dashes/spaces, any case. Throws when malformed. */
export function parseRecoveryCode(code: string): Uint8Array<ArrayBuffer> {
  const clean = code.toUpperCase().replace(/[^A-Z2-7]/g, "");
  if (clean.length !== (RECOVERY_BYTES * 8) / 5) throw new Error("Código de recuperação incompleto.");
  const bits = Array.from(clean, (char) => BASE32.indexOf(char).toString(2).padStart(5, "0")).join("");
  return Uint8Array.from(bits.match(/.{8}/g)!, (byte) => parseInt(byte, 2));
}

/** High-entropy code: HKDF is enough. proof goes to the server (hashed there); key never leaves. */
export async function deriveRecovery(namespace: string, email: string, code: string) {
  const root = await crypto.subtle.importKey("raw", parseRecoveryCode(code), "HKDF", false, ["deriveBits"]);
  const salt = text(PREFIX + namespace + ":" + email);
  const derive = (purpose: string) => crypto.subtle.deriveBits(
    { name: "HKDF", hash: "SHA-256", salt, info: text(PREFIX + purpose) }, root, 256,
  );
  const [proof, key] = await Promise.all([derive("recovery-proof"), derive("recovery-key")]);
  return { proof: encode(proof), key: encode(key) };
}

export async function sealVault(wrappingKey: string, vault: Uint8Array<ArrayBuffer>, purpose: Purpose, email: string) {
  return encode(await seal(await aesKey(decode(wrappingKey)), vault, purpose, email));
}

export async function openVault(wrappingKey: string, wrapped: string, purpose: Purpose, email: string) {
  return unseal(await aesKey(decode(wrappingKey)), decode(wrapped), purpose, email);
}

/** Password credentials + a vault copy sealed by the password key, for an existing vault key. */
export async function sealVaultWithPassword(namespace: string, email: string, password: string, vault: Uint8Array<ArrayBuffer>) {
  const { authentication, passwordKey } = await deriveCredentials(namespace, email, password);
  return { authentication, wrappedPassword: await sealVault(passwordKey, vault, "vault-password", email) };
}

/** Everything a new (or replaced) account vault needs; recoveryCode is shown to the user once. */
export async function createAccountKeys(namespace: string, email: string, password: string) {
  const vault = random(32);
  const recoveryCode = newRecoveryCode();
  const recovery = await deriveRecovery(namespace, email, recoveryCode);
  const { authentication, wrappedPassword } = await sealVaultWithPassword(namespace, email, password, vault);
  return {
    authentication,
    wrappedPassword,
    wrappedRecovery: await sealVault(recovery.key, vault, "vault-recovery", email),
    recoveryProof: recovery.proof,
    recoveryCode,
    vault: encode(vault),
  };
}

/** Session-scoped storage slots (cleared when the tab closes). */
export const STORAGE = {
  vault: PREFIX + "vault",
  recipient: PREFIX + "recipient",
  pairing: PREFIX + "pairing",
} as const;

export const PAIRING_CODE = /^[2-9A-HJ-NP-Z]{8}\.[0-9a-f]{16}$/i;
