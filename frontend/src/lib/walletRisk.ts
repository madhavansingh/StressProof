/**
 * Deterministic DeFi risk profile derivation for connected wallets.
 * Ensures every connected wallet address displays realistic, consistent,
 * and visibly distinct collateral, debt, LTV, health factor, and stress margins.
 */

export interface WalletRiskProfile {
  address: `0x${string}`;
  shortAddress: string;
  role: string;
  roleDescription: string;
  roleBadgeClass: string;
  collateralUsd: number;
  collateralEth: number;
  debtUsd: number;
  accountLtvBps: number;
  accountLtvPct: number;
  protocolMaxLtvPct: number;
  healthFactor: number;
  healthStatus: "SAFE" | "MODERATE" | "AT_RISK" | "CRITICAL";
  liquidationPriceEth: number;
  liquidationDropPct: number;
  stressLossUsd: number;
  bondedEth: number;
  claimsCount: number;
  withdrawableCreditsEth: number;
}

export const SAMPLE_WALLETS = [
  {
    label: "YOUR_WALLET",
    address: "0xd990364d241de18f7dbf17424177b944208a7980" as `0x${string}`,
    description: "Active Connected Session",
  },
  {
    label: "DEPLOYER_VAULT_ADMIN",
    address: "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266" as `0x${string}`,
    description: "DemoVault Owner & Core Deployer",
  },
  {
    label: "BONDED_ATTESTER",
    address: "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC" as `0x${string}`,
    description: "Optimistic Claim Publisher (0.01 ETH Bond)",
  },
  {
    label: "PROTOCOL_RESOLVER",
    address: "0x70997970C51812dc3A010C7d01b50e0d17dc79C8" as `0x${string}`,
    description: "Designated Arbitrator & Dispute Resolver",
  },
  {
    label: "HIGH_LEVERAGE_WHALE",
    address: "0x90F79bf6EB2c4f870365E785982E1f101E93b906" as `0x${string}`,
    description: "High-LTV Borrower Near Liquidation Threshold",
  },
] as const;

const ETH_PRICE_USD = 3000;
const LIQUIDATION_THRESHOLD_BPS = 8250; // 82.5% liquidation threshold

function parseAddressHash(addr: string): number[] {
  const clean = addr.toLowerCase().replace(/^0x/, "").padEnd(40, "0");
  const chunks: number[] = [];
  for (let i = 0; i < 40; i += 8) {
    chunks.push(parseInt(clean.slice(i, i + 8), 16) || 0);
  }
  return chunks;
}

/**
 * Derives a deterministic risk profile for any given wallet address.
 * Two different addresses will always produce distinctly different values,
 * while the same address always produces the exact same profile.
 */
export function deriveWalletRiskProfile(
  rawAddress?: string | null,
  options?: {
    onChainDebtUsd8?: bigint | null;
    onChainCreditsWei?: bigint | null;
    protocolMaxLtvBps?: number | null;
  }
): WalletRiskProfile {
  const address = (
    rawAddress && rawAddress.startsWith("0x")
      ? rawAddress.toLowerCase()
      : "0xd990364d241de18f7dbf17424177b944208a7980"
  ) as `0x${string}`;

  const shortAddress = `${address.slice(0, 6)}...${address.slice(-4)}`;
  const [s1, s2, s3, s4, s5] = parseAddressHash(address);

  // 1. Role Assignment
  let role = "INSTITUTIONAL_BORROWER";
  let roleDescription = "Institutional Credit Line & Collateral Depositor";
  let roleBadgeClass = "border-sky-500 bg-sky-950/40 text-sky-400";

  const lower = address.toLowerCase();
  if (lower === "0x70997970c51812dc3a010c7d01b50e0d17dc79c8") {
    role = "PROTOCOL_RESOLVER";
    roleDescription = "Authorized Dispute Resolver & Claim Arbitrator";
    roleBadgeClass = "border-purple-500 bg-purple-950/40 text-purple-300";
  } else if (lower === "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266") {
    role = "VAULT_ADMIN";
    roleDescription = "DemoVault Owner & Circuit Breaker Controller";
    roleBadgeClass = "border-emerald-500 bg-emerald-950/40 text-emerald-400";
  } else if (lower === "0x3c44cdddb6a900fa2b585dd299e03d12fa4293bc") {
    role = "BONDED_ATTESTER";
    roleDescription = "Automated Off-Chain Attestation Agent";
    roleBadgeClass = "border-[#ea580c] bg-orange-950/40 text-[#ea580c]";
  } else if (lower === "0x90f79bf6eb2c4f870365e785982e1f101e93b906") {
    role = "LEVERAGED_BORROWER";
    roleDescription = "High-LTV Yield Seeking Borrower";
    roleBadgeClass = "border-amber-500 bg-amber-950/40 text-amber-400";
  } else {
    const roleIdx = s1 % 4;
    if (roleIdx === 0) {
      role = "LEVERAGED_BORROWER";
      roleDescription = "Active Multi-Asset Borrower & Staker";
      roleBadgeClass = "border-amber-500 bg-amber-950/40 text-amber-400";
    } else if (roleIdx === 1) {
      role = "MARKET_MAKER";
      roleDescription = "Liquidity Provider & Credit Facility User";
      roleBadgeClass = "border-cyan-500 bg-cyan-950/40 text-cyan-400";
    } else if (roleIdx === 2) {
      role = "YIELD_STRATEGIST";
      roleDescription = "Delta-Neutral Yield Strategy Account";
      roleBadgeClass = "border-indigo-500 bg-indigo-950/40 text-indigo-400";
    } else {
      role = "INSTITUTIONAL_VAULT";
      roleDescription = "Enterprise Custody & Collateral Vault";
      roleBadgeClass = "border-emerald-500 bg-emerald-950/40 text-emerald-400";
    }
  }

  // 2. Deterministic Collateral (USD $12,000 - $78,000 in increments of $500)
  const collateralSteps = (s2 % 133) + 24; // 24..156
  const collateralUsd = collateralSteps * 500;
  const collateralEth = +(collateralUsd / ETH_PRICE_USD).toFixed(2);

  // 3. Target LTV (38% to 76%)
  const targetLtvBps = 3800 + (s3 % 3800); // 3800..7600
  let debtUsd = Math.round((collateralUsd * targetLtvBps) / 10000);

  // If on-chain debt was recorded and > 0, integrate real debt
  if (options?.onChainDebtUsd8 && options.onChainDebtUsd8 > 0n) {
    const onChainDebt = Number(options.onChainDebtUsd8 / 100000000n);
    if (onChainDebt > 0) {
      debtUsd = onChainDebt;
    }
  }

  const accountLtvBps = Math.min(10000, Math.round((debtUsd / collateralUsd) * 10000));
  const accountLtvPct = +(accountLtvBps / 100).toFixed(2);
  const protocolMaxLtvPct = options?.protocolMaxLtvBps ? +(options.protocolMaxLtvBps / 100).toFixed(2) : 80.0;

  // 4. Health Factor: (Collateral * LiquidationThreshold) / Debt
  const maxBorrowThresholdUsd = (collateralUsd * LIQUIDATION_THRESHOLD_BPS) / 10000;
  const healthFactor = +(maxBorrowThresholdUsd / Math.max(1, debtUsd)).toFixed(2);

  // 5. Health Status
  let healthStatus: "SAFE" | "MODERATE" | "AT_RISK" | "CRITICAL" = "SAFE";
  if (healthFactor < 1.05) {
    healthStatus = "CRITICAL";
  } else if (healthFactor < 1.18) {
    healthStatus = "AT_RISK";
  } else if (healthFactor < 1.35) {
    healthStatus = "MODERATE";
  }

  // 6. Liquidation Cushion & Price
  // Liquidation occurs when (CollateralEth * Price * 0.825) <= debtUsd
  // Price = debtUsd / (CollateralEth * 0.825)
  const liquidationPriceEth = Math.round(debtUsd / (collateralEth * (LIQUIDATION_THRESHOLD_BPS / 10000)));
  const dropUsd = Math.max(0, ETH_PRICE_USD - liquidationPriceEth);
  const liquidationDropPct = +((dropUsd / ETH_PRICE_USD) * 100).toFixed(1);

  // 7. Projected Bad Debt Under -30% Price Shock
  // If price drops 30% ($2,100), collateral value is collateralEth * 2100
  const stressedCollateralValue = collateralEth * (ETH_PRICE_USD * 0.7);
  const liquidationRecoverable = stressedCollateralValue * 0.95; // 5% liquidation penalty/slippage
  const stressLossUsd = Math.max(0, Math.round(debtUsd - liquidationRecoverable));

  // 8. Protocol Staking & Credits
  let bondedEth = 0;
  let claimsCount = 0;
  if (role === "BONDED_ATTESTER") {
    bondedEth = 0.03;
    claimsCount = 3;
  } else if (role === "PROTOCOL_RESOLVER") {
    bondedEth = 0.0;
    claimsCount = 0;
  } else if (s4 % 2 === 0) {
    bondedEth = 0.01;
    claimsCount = 1;
  }

  let withdrawableCreditsEth = 0;
  if (options?.onChainCreditsWei && options.onChainCreditsWei > 0n) {
    withdrawableCreditsEth = +(Number(options.onChainCreditsWei) / 1e18).toFixed(4);
  } else if (role === "PROTOCOL_RESOLVER" || s5 % 5 === 0) {
    withdrawableCreditsEth = 0.02;
  }

  return {
    address,
    shortAddress,
    role,
    roleDescription,
    roleBadgeClass,
    collateralUsd,
    collateralEth,
    debtUsd,
    accountLtvBps,
    accountLtvPct,
    protocolMaxLtvPct,
    healthFactor,
    healthStatus,
    liquidationPriceEth,
    liquidationDropPct,
    stressLossUsd,
    bondedEth,
    claimsCount,
    withdrawableCreditsEth,
  };
}
