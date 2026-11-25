import { describe, expect, it } from "vitest";

import {
  aesKey, consultationKey, createAccountKeys, decode, deriveCredentials, deriveRecovery, encode, exportPublic,
  newKeyPair, newRecoveryCode, openPdf, openText, openVault, parseRecoveryCode, publicFingerprint, sealPdf, seal,
  sealText, sealVaultWithPassword, unseal, comparisonCode, sha256Hex,
} from "./crypto";

// Reference values computed independently with Python hashlib / cryptography.
const PYTHON_VECTOR = {
  authentication: "-yPMFhzp_V_pTaVsCT47C6jhjAr3LLrwWO4HCQNBk6Y",
  passwordKey: "hvuIgjfu_6EaJHf99rVQ-eCkf5ebxJkFmbLLdEtAUYQ",
};
const P256_GENERATOR = "BGsX0fLhLEJH-Lzm5WOkQPJ3A32BLeszoPShOUXYmMKWT-NC4v4af5uO5-tKfA-eFivOM1drMV7Oy7ZAaDe_UfU";
const pdf = new TextEncoder().encode("%PDF-1.4\n%%EOF\n").buffer as ArrayBuffer;

describe("deriveCredentials", () => {
  it("test_deriveCredentials_python_vector_matches", async () => {
    expect(await deriveCredentials("ns-test", "ana", "senha longa de teste")).toEqual(PYTHON_VECTOR);
  });
});

describe("publicFingerprint", () => {
  it("test_publicFingerprint_matches_backend_sha256_prefix", async () => {
    expect(await publicFingerprint(P256_GENERATOR)).toBe("698bea63dc44a344");
  });
});

describe("seal / unseal", () => {
  it("test_sealPdf_roundtrip_returns_original_and_backend_sized_wrapped_key", async () => {
    const vault = await aesKey(decode(PYTHON_VECTOR.passwordKey));
    const { ciphertext, wrappedKey } = await sealPdf(vault, pdf, "exam-1");
    expect(ciphertext[0]).toBe(1);
    expect(decode(wrappedKey).length).toBe(61); // exams/crypto_format.wrapped_key_bytes
    const rawKey = await unseal(vault, decode(wrappedKey), "owner", "exam-1");
    expect(new TextDecoder().decode(await openPdf(rawKey, ciphertext, "exam-1"))).toContain("%PDF-1.4");
  });

  it("test_unseal_other_exam_id_rejects", async () => {
    const key = await aesKey(crypto.getRandomValues(new Uint8Array(32)));
    const envelope = await seal(key, new Uint8Array([1, 2, 3]), "pdf", "a");
    await expect(unseal(key, envelope, "pdf", "b")).rejects.toThrow();
  });

  it("test_encode_decode_roundtrip_is_url_safe", () => {
    const bytes = crypto.getRandomValues(new Uint8Array(65));
    const value = encode(bytes);
    expect(value).toMatch(/^[A-Za-z0-9_-]+$/);
    expect(decode(value)).toEqual(bytes);
  });
});

describe("consultationKey", () => {
  it("test_consultationKey_owner_and_office_agree", async () => {
    const office = await newKeyPair();
    const owner = await newKeyPair();
    const code = "ABCD2345";
    const ownerSide = await consultationKey(owner.privateKey, await exportPublic(office.publicKey), code);
    const officeSide = await consultationKey(office.privateKey, await exportPublic(owner.publicKey), code);
    const dataKey = crypto.getRandomValues(new Uint8Array(32));
    const wrapped = await seal(ownerSide, dataKey, "recipient", "exam-1");
    expect(await unseal(officeSide, wrapped, "recipient", "exam-1")).toEqual(dataKey);
    const otherCode = await consultationKey(office.privateKey, await exportPublic(owner.publicKey), "ZZZZ9999");
    await expect(unseal(otherCode, wrapped, "recipient", "exam-1")).rejects.toThrow();
  });
});

describe("account vault and recovery", () => {
  it("test_recoveryCode_parse_ignores_dashes_and_case", () => {
    const code = newRecoveryCode();
    expect(code).toMatch(/^([A-Z2-7]{4}-){7}[A-Z2-7]{4}$/);
    expect(parseRecoveryCode(code.toLowerCase().replaceAll("-", " "))).toEqual(parseRecoveryCode(code));
    expect(() => parseRecoveryCode("ABCD-EFGH")).toThrow();
  });

  it("test_createAccountKeys_password_and_recovery_open_same_vault", async () => {
    const keys = await createAccountKeys("ns", "ana@example.com", "senha longa de teste");
    expect(decode(keys.wrappedPassword).length).toBe(61);
    const { passwordKey } = await deriveCredentials("ns", "ana@example.com", "senha longa de teste");
    const viaPassword = await openVault(passwordKey, keys.wrappedPassword, "vault-password", "ana@example.com");
    const recovery = await deriveRecovery("ns", "ana@example.com", keys.recoveryCode);
    expect(recovery.proof).toBe(keys.recoveryProof);
    const viaRecovery = await openVault(recovery.key, keys.wrappedRecovery, "vault-recovery", "ana@example.com");
    expect(encode(viaPassword)).toBe(keys.vault);
    expect(encode(viaRecovery)).toBe(keys.vault);
  });

  it("test_reset_with_recovery_reseals_vault_for_new_password", async () => {
    const keys = await createAccountKeys("ns", "ana@example.com", "senha antiga e longa");
    const recovery = await deriveRecovery("ns", "ana@example.com", keys.recoveryCode);
    const vault = await openVault(recovery.key, keys.wrappedRecovery, "vault-recovery", "ana@example.com");
    const resealed = await sealVaultWithPassword("ns", "ana@example.com", "senha nova bem longa", vault);
    const { passwordKey } = await deriveCredentials("ns", "ana@example.com", "senha nova bem longa");
    expect(encode(await openVault(passwordKey, resealed.wrappedPassword, "vault-password", "ana@example.com"))).toBe(keys.vault);
    const old = await deriveCredentials("ns", "ana@example.com", "senha antiga e longa");
    await expect(openVault(old.passwordKey, resealed.wrappedPassword, "vault-password", "ana@example.com")).rejects.toThrow();
  });
});

describe("sealed metadata and @nome requests", () => {
  it("test_comparisonCode_matches_python_vector", async () => {
    expect(await comparisonCode(P256_GENERATOR, "a1b2c3d4e5f60718")).toBe("249780");
  });

  it("test_sealText_roundtrip_bound_to_purpose_and_id", async () => {
    const rawKey = crypto.getRandomValues(new Uint8Array(32));
    const sealed = await sealText(rawKey, "Hemograma completo", "meta-title", "doc-1");
    expect(await openText(rawKey, sealed, "meta-title", "doc-1")).toBe("Hemograma completo");
    await expect(openText(rawKey, sealed, "meta-issuer", "doc-1")).rejects.toThrow();
    expect(await openText(rawKey, "", "meta-issuer", "doc-1")).toBe("");
  });

  it("test_sha256Hex_known_value", async () => {
    expect(await sha256Hex("abc")).toBe("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
  });
});
