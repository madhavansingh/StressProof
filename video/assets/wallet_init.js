(() => {
  // Test-only EIP-1193 wallet for the LOCAL ANVIL DEMONSTRATION: forwards to Anvil, which signs for its
  // public, unlocked development accounts. No private keys are involved.
  window.__acct = "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC";
  const RPC = "http://127.0.0.1:8546", listeners = {};
  const rpc = async (method, params) => {
    const r = await fetch(RPC, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ jsonrpc: "2.0", id: Date.now(), method, params: params || [] }) });
    const j = await r.json(); if (j.error) { const e = new Error(j.error.message); e.code = j.error.code; e.data = j.error.data; throw e; } return j.result;
  };
  const provider = {
    request: async ({ method, params }) => {
      if (method === "eth_requestAccounts" || method === "eth_accounts") return [window.__acct];
      if (method === "eth_chainId") return "0x7a69";
      if (method === "net_version") return "31337";
      if (method === "wallet_switchEthereumChain") return null;
      if (method === "wallet_requestPermissions" || method === "wallet_getPermissions") return [{ parentCapability: "eth_accounts" }];
      if (method === "eth_sendTransaction") params[0].from = window.__acct;
      return rpc(method, params);
    },
    on: (e, f) => { (listeners[e] = listeners[e] || []).push(f); },
    removeListener: (e, f) => { listeners[e] = (listeners[e] || []).filter((x) => x !== f); },
  };
  window.ethereum = provider;
  const info = Object.freeze({ uuid: "6f1c2a8e-0b7d-4c55-9a77-5e3c1d2b4f10", name: "Anvil Test Wallet", icon: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='32' height='32'%3E%3Crect width='32' height='32' fill='%23ea580c'/%3E%3C/svg%3E", rdns: "dev.stressproof.anviltest" });
  const announce = () => window.dispatchEvent(new CustomEvent("eip6963:announceProvider", { detail: Object.freeze({ info, provider }) }));
  window.addEventListener("eip6963:requestProvider", announce);
  announce();
})();
