/**
 * Security validation and sanitization helpers per Task F12 and T-F-05.
 * Enforces safe URI schemes and ensures rationales render strictly as text.
 */

const ALLOWED_URI_PROTOCOLS = ["https:", "ipfs:"];

/**
 * Validates that an external link uses only https: or ipfs: protocol.
 * Rejects javascript:, data:, file:, and other unsafe schemes.
 */
export function isValidExternalLink(uri: string): boolean {
  if (!uri || typeof uri !== "string") return false;
  const trimmed = uri.trim();

  if (trimmed.startsWith("ipfs://")) {
    return true;
  }

  try {
    const parsed = new URL(trimmed);
    return ALLOWED_URI_PROTOCOLS.includes(parsed.protocol);
  } catch {
    return false;
  }
}

/**
 * Escapes HTML entities to ensure user/agent rationale strings render safely as plain text.
 */
export function escapeHtml(input: string): string {
  if (!input) return "";
  return input
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

