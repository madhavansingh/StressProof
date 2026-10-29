import { describe, it, expect, beforeEach } from "vitest";
import { EventEmitter } from "events";
import { connect, createConfig, createConnector, createStorage, getAccount, noopStorage, type CreateConnectorFn } from "@wagmi/core";
import { http, UserRejectedRequestError, getAddress } from "viem";
import { baseSepolia, hardhat } from "viem/chains";
import { withWalletConnectGuards } from "../src/lib/web3/walletConnectGuards";
import {
  clearWalletDiagnostic,
  getWalletDiagnostic,
  getWalletTiming,
  isWalletAttemptPending,
  resetWalletTiming,
} from "../src/lib/web3/walletDiagnostics";
import { cancelPendingWalletConnectAttempts } from "../src/lib/web3/walletConnectGuards";
import { mock } from "@wagmi/core";
import { checkWriteReadiness } from "../src/lib/web3/walletPolicy";
import { effectiveAccountStatus, walletButtonState } from "../src/lib/web3/walletButtonState";
import { cakeWalletSupportsChain } from "../src/lib/web3/walletPolicy";

const ADDR = "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC";
const ADDR2 = "0x90F79bf6EB2c4f870365E785982E1f101E93b906";
const anvil = { ...hardhat, id: 31337 as const };
const WRITE_METHODS = ["eth_sendTransaction", "eth_sendRawTransaction", "eth_signTransaction", "personal_sign", "eth_sign"];

type Behaviour = "approve" | "reject" | "expire" | "hang-after-approval" | "cake" | "manual";
interface ManualProposal {
  id: number;
  settled: boolean;
  approve: (accounts: string[]) => void;
  expire: () => void;
}
const CAKE_CHAINS = [1, 137, 8453, 42161, 56, 4663];
type Namespaces = Record<string, { accounts: string[]; methods: string[]; events: string[] }>;

/**
 * A stand-in for wagmi's WalletConnect connector with the same observable behaviour:
 * the session's first account chain becomes the active chain, and being asked for another chain
 * sends wallet_switchEthereumChain and waits forever (what Cake Wallet does for chain 31337).
 */
function fakeWalletConnect(behaviour: Behaviour, namespaces: Namespaces | null) {
  // Like WalletConnect's SignClient: client.on() and client.events share one emitter, and
  // pending proposals live in a store; a proposal_expire event rejects that proposal's approval.
  const signClient: EventEmitter & { events?: EventEmitter; proposal?: { getAll: () => { id: number }[] } } =
    new EventEmitter();
  signClient.events = signClient;
  const provider = Object.assign(new EventEmitter(), {
    session: null as null | { topic: string; namespaces: Namespaces },
    signer: { client: signClient },
    proposedChains: [] as number[],
    /** One entry per proposal (QR code) in "manual" mode; the test approves or expires each. */
    proposals: [] as ManualProposal[],
    /** Count of proposals cleared through proposal_expire (the clean path, no stray rejection). */
    expiredByEvent: 0,
    /** Stand-in for EthereumProvider.connect: records the chains offered in the proposal. */
    async connect(opts: { optionalChains?: number[] } = {}) {
      provider.proposedChains = opts.optionalChains ?? [];
    },
    requests: [] as string[],
    async disconnect() {
      provider.requests.push("wc_disconnect");
      provider.session = null;
    },
  });
  signClient.proposal = { getAll: () => provider.proposals.filter((p) => !p.settled).map((p) => ({ id: p.id })) };
  signClient.on("proposal_expire", ({ id }: { id: number }) => {
    const proposal = provider.proposals.find((p) => p.id === id && !p.settled);
    if (!proposal) return;
    provider.expiredByEvent += 1;
    proposal.expire();
  });
  const accountsOf = () => {
    const accounts = provider.session?.namespaces.eip155?.accounts ?? [];
    const chain = accounts[0] ? Number(accounts[0].split(":")[1]) : 31337;
    return { chain, addresses: accounts.filter((a) => Number(a.split(":")[1]) === chain).map((a) => getAddress(a.split(":")[2])) };
  };
  const create: CreateConnectorFn = createConnector((config) => ({
    id: "fake-wc",
    name: "Fake WC",
    type: "walletConnect",
    async connect({ chainId }: { chainId?: number } = {}) {
      if (behaviour === "reject") throw new UserRejectedRequestError(new Error("User rejected."));
      if (behaviour === "expire") throw new Error("Proposal expired");
      if (behaviour === "manual") {
        return new Promise((resolve, reject) => {
          const id = provider.proposals.length + 1;
          const proposal: ManualProposal = {
            id,
            settled: false,
            approve: (accounts) => {
              if (proposal.settled) return;
              proposal.settled = true;
              provider.session = { topic: `session-${id}`, namespaces: ns(accounts) };
              provider.emit("connect", { chainId: "0x1" });
              const { chain, addresses } = accountsOf();
              resolve({ accounts: addresses, chainId: chain } as never);
            },
            expire: () => {
              if (proposal.settled) return;
              proposal.settled = true;
              reject(new Error("Proposal expired"));
            },
          };
          provider.proposals.push(proposal);
        });
      }
      if (behaviour === "cake") {
        // Like the real connector: the proposal offers the configured chains.
        await provider.connect({ optionalChains: config.chains.map((c) => c.id) });
        const usable = provider.proposedChains.filter((id) => CAKE_CHAINS.includes(id));
        // Observed with the real app: with no chain in common Cake Wallet never answers.
        if (!usable.length) throw new Error("Proposal expired");
        provider.session = { topic: "session-topic", namespaces: ns(usable.map((id) => `eip155:${id}:${ADDR}`)) };
        provider.emit("connect", { chainId: "0x1" });
        const { chain, addresses } = accountsOf();
        if (chainId && chainId !== chain) return new Promise(() => {});
        return { accounts: addresses, chainId: chain } as never;
      }
      provider.session = { topic: "session-topic", namespaces: namespaces ?? {} };
      provider.emit("connect", { chainId: "0x1" });
      if (behaviour === "hang-after-approval") return new Promise(() => {});
      const { chain, addresses } = accountsOf();
      if (chainId && chainId !== chain) {
        provider.requests.push("wallet_switchEthereumChain");
        return new Promise(() => {});
      }
      return { accounts: addresses, chainId: chain } as never;
    },
    async disconnect() {
      await provider.disconnect();
    },
    async getAccounts() {
      return accountsOf().addresses;
    },
    async getChainId() {
      return accountsOf().chain;
    },
    async getProvider() {
      return provider;
    },
    async isAuthorized() {
      return !!provider.session;
    },
    async switchChain({ chainId }) {
      provider.requests.push("wallet_switchEthereumChain");
      await new Promise(() => {});
      return config.chains.find((c) => c.id === chainId)!;
    },
    onAccountsChanged(accounts) {
      config.emitter.emit("change", { accounts: accounts.map((a) => getAddress(a)) });
    },
    onChainChanged(chain) {
      config.emitter.emit("change", { chainId: Number(chain) });
    },
    onDisconnect() {
      config.emitter.emit("disconnect");
    },
  }));
  return { create, provider };
}

function setup(
  behaviour: Behaviour,
  namespaces: Namespaces | null,
  timeoutMs = 2000,
  extraOptionalChains?: number[],
  proposalLifetimeMs?: number
) {
  const fake = fakeWalletConnect(behaviour, namespaces);
  const guarded = withWalletConnectGuards(fake.create, {
    walletName: "Cake Wallet",
    targetChainId: 31337,
    canSwitchTo: cakeWalletSupportsChain,
    setupTimeoutMs: timeoutMs,
    extraOptionalChains,
    proposalLifetimeMs,
  });
  const config = createConfig({
    chains: [anvil, baseSepolia],
    connectors: [guarded],
    transports: { [anvil.id]: http("http://127.0.0.1:1"), [baseSepolia.id]: http("http://127.0.0.1:1") },
    storage: createStorage({ storage: noopStorage }),
  });
  return { config, connector: config.connectors[0], provider: fake.provider };
}

const ns = (accounts: string[]): Namespaces => ({
  eip155: { accounts, methods: ["eth_sendTransaction", "personal_sign"], events: ["accountsChanged", "chainChanged"] },
});

function header(config: ReturnType<typeof setup>["config"]) {
  const a = getAccount(config);
  return walletButtonState({
    mounted: true,
    status: effectiveAccountStatus(a.status, isWalletAttemptPending()),
    account: a.address ? { displayName: a.address } : undefined,
    chain: a.chainId ? { id: a.chainId } : undefined,
    targetChainId: 31337,
  });
}

function expectNoWrites(provider: { requests: string[] }) {
  expect(provider.requests.filter((r) => WRITE_METHODS.includes(r))).toEqual([]);
}

beforeEach(() => {
  clearWalletDiagnostic();
  resetWalletTiming();
});

describe("WalletConnect guards around wagmi's connect", () => {
  it("connects a wallet with an account on the deployment chain (normal EVM path)", async () => {
    const { config, provider } = setup("approve", ns([`eip155:31337:${ADDR}`]));
    const result = await connect(config, { connector: config.connectors[0], chainId: 31337 });
    expect(result).toEqual({ accounts: [ADDR], chainId: 31337 });
    expect(getAccount(config)).toMatchObject({ isConnected: true, address: ADDR, chainId: 31337 });
    expect(header(config)).toEqual({ kind: "connected", displayName: ADDR });
    expect(getWalletDiagnostic()?.stage).toBe("connected");
    expectNoWrites(provider);
  });

  it("regression: a session on another chain finishes connecting instead of hanging on a chain switch", async () => {
    const { config, provider } = setup("approve", ns([`eip155:1:${ADDR}`, `eip155:137:${ADDR}`]));
    // RainbowKit always passes the app chain; before the fix this never settled (stuck CONNECTING).
    const pending = connect(config, { connector: config.connectors[0], chainId: 31337 });
    expect(header(config)).toEqual({ kind: "connecting" });
    const result = await pending;
    expect(result).toEqual({ accounts: [ADDR], chainId: 1 });
    expect(provider.requests).not.toContain("wallet_switchEthereumChain");
    expect(getAccount(config)).toMatchObject({ isConnected: true, address: ADDR, chainId: 1 });
    expect(header(config)).toEqual({ kind: "wrong-network", chainId: 1 });
    expect(getWalletDiagnostic()?.stage).toBe("wrong-network");
    expectNoWrites(provider);
  });

  it("does not treat a pairing without an EVM account as connected", async () => {
    const { config, provider } = setup("approve", ns([]));
    await expect(connect(config, { connector: config.connectors[0], chainId: 31337 })).rejects.toThrow(
      /paired but did not share an EVM account/i
    );
    expect(getAccount(config)).toMatchObject({ isConnected: false, status: "disconnected", address: undefined });
    expect(header(config)).toEqual({ kind: "disconnected" });
    expect(getWalletDiagnostic()?.stage).toBe("no-account");
    expect(provider.requests).toContain("wc_disconnect");
    expectNoWrites(provider);
  });

  it("reports a session without an EVM namespace", async () => {
    const { config } = setup("approve", { solana: { accounts: ["solana:abc:xyz"], methods: [], events: [] } });
    await expect(connect(config, { connector: config.connectors[0], chainId: 31337 })).rejects.toThrow();
    expect(getWalletDiagnostic()?.stage).toBe("no-evm-namespace");
    expect(getAccount(config).isConnected).toBe(false);
  });

  it("reports a rejected connection", async () => {
    const { config, provider } = setup("reject", null);
    await expect(connect(config, { connector: config.connectors[0], chainId: 31337 })).rejects.toThrow();
    expect(getWalletDiagnostic()?.stage).toBe("rejected");
    expect(getAccount(config).status).toBe("disconnected");
    expectNoWrites(provider);
  });

  it("reports an expired proposal and ends CONNECTING", async () => {
    const { config } = setup("expire", null);
    await expect(connect(config, { connector: config.connectors[0], chainId: 31337 })).rejects.toThrow();
    expect(getWalletDiagnostic()?.stage).toBe("expired");
    expect(isWalletAttemptPending()).toBe(false);
    expect(getAccount(config).status).toBe("disconnected");
  });

  it("times out when setup stalls after the wallet approved, and drops the session", async () => {
    const { config, provider } = setup("hang-after-approval", ns([`eip155:1:${ADDR}`]), 30);
    await expect(connect(config, { connector: config.connectors[0], chainId: 31337 })).rejects.toThrow(/timed out/i);
    expect(getWalletDiagnostic()?.stage).toBe("timeout");
    expect(getAccount(config).status).toBe("disconnected");
    expect(provider.requests).toContain("wc_disconnect");
  });

  it("follows account and chain changes, then disconnection", async () => {
    const { config, connector, provider } = setup("approve", ns([`eip155:1:${ADDR}`]));
    await connect(config, { connector, chainId: 31337 });
    connector.onAccountsChanged([ADDR2]);
    expect(getAccount(config).address).toBe(ADDR2);
    connector.onChainChanged("0x7a69");
    expect(header(config)).toEqual({ kind: "connected", displayName: ADDR2 });
    provider.emit("session_delete", { topic: "t" });
    expect(getWalletDiagnostic()?.stage).toBe("disconnected");
    connector.onDisconnect();
    expect(getAccount(config)).toMatchObject({ status: "disconnected", address: undefined });
    expect(header(config)).toEqual({ kind: "disconnected" });
    expectNoWrites(provider);
  });

  it("lets a switch through to a chain the session itself approved", async () => {
    const { config, connector, provider } = setup("approve", ns([`eip155:1:${ADDR}`, `eip155:84532:${ADDR}`]));
    await connect(config, { connector, chainId: 31337 });
    void connector.switchChain!({ chainId: 84532 });
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(provider.requests).toContain("wallet_switchEthereumChain");
  });

  it("refuses to ask Cake Wallet to switch to a chain it cannot use, instead of waiting forever", async () => {
    const { config, connector, provider } = setup("approve", ns([`eip155:1:${ADDR}`]));
    await connect(config, { connector, chainId: 31337 });
    await expect(connector.switchChain!({ chainId: 31337 })).rejects.toThrow(/cannot switch to chain 31337/i);
    expect(provider.requests).not.toContain("wallet_switchEthereumChain");
  });

  it("records approval and validation times so the UI update after approval can be measured", async () => {
    const { config } = setup("approve", ns([`eip155:31337:${ADDR}`]));
    await connect(config, { connector: config.connectors[0], chainId: 31337 });
    const timing = getWalletTiming();
    expect(timing.approvedAt).toBeTypeOf("number");
    expect(timing.validatedAt).toBeGreaterThanOrEqual(timing.approvedAt!);
    // The app's own work between approval and a validated account: no network round trips.
    expect(timing.validatedAt! - timing.approvedAt!).toBeLessThan(100);
  });

  it("treats a session expiry as a disconnect at once (WalletConnect's provider does not)", async () => {
    const { config, connector, provider } = setup("approve", ns([`eip155:1:${ADDR}`]));
    await connect(config, { connector, chainId: 31337 });
    provider.signer.client.emit("session_expire", { topic: "other-topic" });
    expect(getAccount(config).isConnected).toBe(true);
    provider.signer.client.emit("session_expire", { topic: "session-topic" });
    await Promise.resolve();
    expect(getWalletDiagnostic()?.stage).toBe("disconnected");
    expect(getWalletDiagnostic()?.message).toMatch(/expired/i);
    expect(getAccount(config)).toMatchObject({ status: "disconnected", address: undefined });
    expect(header(config)).toEqual({ kind: "disconnected" });
  });

  it("keeps writes refused on the wrong chain and allows them only on the deployment chain", async () => {
    const { config, connector, provider } = setup("approve", ns([`eip155:1:${ADDR}`]));
    await connect(config, { connector, chainId: 31337 });
    const readiness = () => {
      const a = getAccount(config);
      return checkWriteReadiness({
        isConnected: a.isConnected,
        address: a.address,
        walletChainId: a.chainId,
        targetChainId: 31337,
        contractAddress: "0x5FbDB2315678afecb367f032d93F642f64180aa3",
      });
    };
    expect(readiness()).toMatchObject({ ok: false, kind: "wrong-network" });
    connector.onChainChanged("0x7a69");
    expect(readiness()).toEqual({ ok: true, chainId: 31337 });
    expectNoWrites(provider);
  });

  it("reproduces the phone result: a proposal with only 31337/84532 gets no answer from Cake Wallet", async () => {
    const { config, provider } = setup("cake", null);
    await expect(connect(config, { connector: config.connectors[0], chainId: 31337 })).rejects.toThrow(/expired/i);
    expect(provider.proposedChains).toEqual([31337, 84532]);
    expect(getWalletDiagnostic()?.stage).toBe("expired");
    expect(getAccount(config).status).toBe("disconnected");
  });

  it("offers Cake Wallet's own chains as optional, so it can share a real account (shown as WRONG_NETWORK)", async () => {
    const { config, provider } = setup("cake", null, 2000, CAKE_CHAINS);
    const result = await connect(config, { connector: config.connectors[0], chainId: 31337 });
    expect(provider.proposedChains.slice(0, 2)).toEqual([31337, 84532]);
    expect(provider.proposedChains).toEqual(expect.arrayContaining(CAKE_CHAINS));
    expect(result).toEqual({ accounts: [ADDR], chainId: 1 });
    expect(header(config)).toEqual({ kind: "wrong-network", chainId: 1 });
    expect(getWalletDiagnostic()?.stage).toBe("wrong-network");
    expectNoWrites(provider);
  });

  it("adds the extra chains once, even across repeated connects", async () => {
    const { config, connector, provider } = setup("cake", null, 2000, CAKE_CHAINS);
    await connect(config, { connector, chainId: 31337 });
    const first = [...provider.proposedChains];
    await connector.disconnect();
    config.setState((x) => ({ ...x, current: null, status: "disconnected" }));
    await connect(config, { connector, chainId: 31337 });
    expect(provider.proposedChains).toEqual(first);
    expect(new Set(provider.proposedChains).size).toBe(provider.proposedChains.length);
  });
});

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

describe("expired, overlapping and stale WalletConnect attempts", () => {
  it("ends a QR code just before WalletConnect's own timer, through its clean expiry path", async () => {
    const { config, connector, provider } = setup("manual", null, 2000, undefined, 40);
    const attempt = connect(config, { connector, chainId: 31337 });
    await tick();
    expect(header(config)).toEqual({ kind: "connecting" });
    await expect(attempt).rejects.toThrow("Proposal expired");
    expect(provider.expiredByEvent).toBe(1);
    expect(getWalletDiagnostic()).toMatchObject({
      stage: "expired",
      message: "Connection request expired. Generate a new QR code and scan again.",
    });
    expect(isWalletAttemptPending()).toBe(false);
    expect(header(config)).toEqual({ kind: "disconnected" });
  });

  it("a retry after expiry starts a fresh proposal; the expired one is never reused", async () => {
    const { config, connector, provider } = setup("manual", null);
    const first = connect(config, { connector, chainId: 31337 });
    await tick();
    provider.proposals[0].expire();
    await expect(first).rejects.toThrow(/expired/i);
    expect(getWalletDiagnostic()?.stage).toBe("expired");

    const retry = connect(config, { connector, chainId: 31337 });
    await tick();
    expect(provider.proposals).toHaveLength(2);
    expect(getWalletDiagnostic()).toBeNull();
    provider.proposals[0].approve([`eip155:1:${ADDR}`]);
    expect(getAccount(config).isConnected).toBe(false);
    provider.proposals[1].approve([`eip155:1:${ADDR}`]);
    await expect(retry).resolves.toEqual({ accounts: [ADDR], chainId: 1 });
    expect(header(config)).toEqual({ kind: "wrong-network", chainId: 1 });
  });

  it("a new QR replaces the old one: the old proposal is withdrawn and CONNECTING stays for the new one", async () => {
    const { config, connector, provider } = setup("manual", null);
    const older = connect(config, { connector, chainId: 31337 });
    await tick();
    const newer = connect(config, { connector, chainId: 31337 });
    await expect(older).rejects.toThrow("Proposal expired");
    expect(provider.expiredByEvent).toBe(1);
    expect(getWalletDiagnostic()).toBeNull();
    expect(isWalletAttemptPending()).toBe(true);
    expect(header(config)).toEqual({ kind: "connecting" });
    // Scanning the replaced QR can no longer connect anything.
    provider.proposals[0].approve([`eip155:1:${ADDR}`]);
    expect(getAccount(config).isConnected).toBe(false);
    provider.proposals[1].approve([`eip155:31337:${ADDR}`]);
    await newer;
    expect(header(config)).toEqual({ kind: "connected", displayName: ADDR });
  });

  it("closing the modal withdraws the pending proposal and reports nothing", async () => {
    const { config, connector, provider } = setup("manual", null);
    const attempt = connect(config, { connector, chainId: 31337 });
    await tick();
    cancelPendingWalletConnectAttempts();
    expect(isWalletAttemptPending()).toBe(false);
    await expect(attempt).rejects.toThrow("Proposal expired");
    expect(provider.expiredByEvent).toBe(1);
    expect(getWalletDiagnostic()).toBeNull();
  });

  it("keeps a live session when an old proposal's expiry arrives afterwards", async () => {
    const { config, connector, provider } = setup("manual", null);
    const attempt = connect(config, { connector, chainId: 31337 });
    await tick();
    provider.proposals[0].approve([`eip155:1:${ADDR}`]);
    await attempt;
    provider.signer.client.events!.emit("proposal_expire", { id: 1 });
    expect(getAccount(config)).toMatchObject({ isConnected: true, address: ADDR, chainId: 1 });
    expect(getWalletDiagnostic()?.stage).toBe("wrong-network");
    expect(provider.requests).not.toContain("wc_disconnect");
    expectNoWrites(provider);
  });
});

describe("MetaMask on Anvil (browser wallet, not wrapped)", () => {
  it("connects on 31337 with a real account and passes the write readiness check", async () => {
    const config = createConfig({
      chains: [anvil, baseSepolia],
      connectors: [mock({ accounts: [ADDR] })],
      transports: { [anvil.id]: http("http://127.0.0.1:1"), [baseSepolia.id]: http("http://127.0.0.1:1") },
      storage: createStorage({ storage: noopStorage }),
    });
    const result = await connect(config, { connector: config.connectors[0], chainId: 31337 });
    expect(result.chainId).toBe(31337);
    expect(header(config as never)).toEqual({ kind: "connected", displayName: ADDR });
    const a = getAccount(config);
    expect(
      checkWriteReadiness({
        isConnected: a.isConnected,
        address: a.address,
        walletChainId: a.chainId,
        targetChainId: 31337,
        contractAddress: "0x5FbDB2315678afecb367f032d93F642f64180aa3",
      })
    ).toEqual({ ok: true, chainId: 31337 });
  });
});
