"use client";

import React, { useState } from "react";
import { WagmiProvider } from "wagmi";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RainbowKitProvider, darkTheme, type DisclaimerComponent } from "@rainbow-me/rainbowkit";
import "@rainbow-me/rainbowkit/styles.css";
import { config, TARGET_CHAIN_ID, WALLETCONNECT_PROJECT_ID } from "@/lib/web3/wagmi";
import { CAKE_WALLET_DOCS_URL } from "@/lib/web3/wallets";
import { cakeWalletSupportsChain } from "@/lib/web3/walletPolicy";
import { WrongChainBanner } from "@/components/layout/WrongChainBanner";
import { WalletConnectionNotice } from "@/components/layout/WalletConnectionNotice";
import { WalletConnectLifecycle } from "@/components/providers/WalletConnectLifecycle";

// Shown in the connect modal so the Cake Wallet limitation is visible before anyone connects.
const WalletDisclaimer: DisclaimerComponent = ({ Text, Link }) => (
  <Text>
    {WALLETCONNECT_PROJECT_ID === null
      ? "WalletConnect wallets (including Cake Wallet) are disabled: NEXT_PUBLIC_WC_PROJECT_ID is not set. "
      : ""}
    {cakeWalletSupportsChain(TARGET_CHAIN_ID)
      ? `Cake Wallet supports chain ${TARGET_CHAIN_ID} over WalletConnect. `
      : `Cake Wallet connects over WalletConnect on Ethereum, Polygon, Base, Arbitrum, BNB Smart Chain and Robinhood Chain only; it cannot sign on this deployment's chain (${TARGET_CHAIN_ID}). `}
    <Link href={CAKE_WALLET_DOCS_URL}>Cake Wallet WalletConnect docs</Link>
  </Text>
);

export function Web3Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            refetchOnWindowFocus: false,
            staleTime: 4000,
          },
        },
      })
  );

  return (
    <WagmiProvider config={config}>
      <QueryClientProvider client={queryClient}>
        <RainbowKitProvider
          appInfo={{ appName: "StressProof", disclaimer: WalletDisclaimer }}
          initialChain={TARGET_CHAIN_ID}
          theme={darkTheme({
            accentColor: "#ea580c",
            accentColorForeground: "#ffffff",
            borderRadius: "none",
            fontStack: "system",
          })}
        >
          <WalletConnectLifecycle />
          <WrongChainBanner />
          <WalletConnectionNotice />
          {children}
        </RainbowKitProvider>
      </QueryClientProvider>
    </WagmiProvider>
  );
}
