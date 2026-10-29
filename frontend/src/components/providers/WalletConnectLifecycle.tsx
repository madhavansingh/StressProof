"use client";

import { useEffect, useRef } from "react";
import { useConnectModal } from "@rainbow-me/rainbowkit";
import { useWalletDiagnostic } from "@/lib/web3/useWalletDiagnostic";
import { cancelPendingWalletConnectAttempts } from "@/lib/web3/walletConnectGuards";

/** Closes RainbowKit's connect modal the way a user does (its dialog listens for Escape). */
function closeConnectModal(): void {
  document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
}

/**
 * WalletConnect housekeeping for the whole app (rendered once inside RainbowKitProvider):
 * - closing the connect modal withdraws the proposals it started (no stray expiry later);
 * - when the current QR code expires, the modal closes and the notice offers a fresh retry.
 */
export function WalletConnectLifecycle() {
  const { connectModalOpen } = useConnectModal();
  const diagnostic = useWalletDiagnostic();
  const wasOpen = useRef(connectModalOpen);

  useEffect(() => {
    if (wasOpen.current && !connectModalOpen) cancelPendingWalletConnectAttempts();
    wasOpen.current = connectModalOpen;
  }, [connectModalOpen]);

  useEffect(() => {
    if (diagnostic?.stage === "expired" && connectModalOpen) closeConnectModal();
    // Only a new diagnostic should close the modal, not reopening it later.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [diagnostic]);

  return null;
}
