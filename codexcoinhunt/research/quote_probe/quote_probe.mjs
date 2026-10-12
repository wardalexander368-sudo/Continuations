#!/usr/bin/env node
/** Read-only PumpSwap state probe. It cannot sign, build or send a transaction. */
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import BN from "bn.js";
import { Connection, PublicKey } from "@solana/web3.js";
import {
  OnlinePumpAmmSdk,
  isPumpPool,
  multiHopSwapQuote,
} from "@pump-fun/pump-swap-sdk";

const PUMP_AMM_PROGRAM = new PublicKey("pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA");
const WSOL = "So11111111111111111111111111111111111111112";
const USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v";
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const outDir = path.resolve(process.argv[2] || path.join(root, "results", "quote_probe_latest"));
const rpcUrl = process.env.SOLANA_RPC_URL || "https://api.mainnet-beta.solana.com";
const maxAgeMs = Number(process.env.MAX_QUOTE_AGE_MS || "2000");
const maxMarketReferenceAgeMs = Number(process.env.MAX_MARKET_REFERENCE_AGE_MS || "5000");
const rpcCommitment = process.env.RPC_COMMITMENT || "processed";
const positionUsd = Number(process.env.POSITION_USD || "7");
const allocatedDataUsd = 0.05;
const buyFixedUsd = 0.02;
const sellFixedUsd = 0.02;
const localFeeFraction = 0.005;
const adverseAllowanceFraction = 0.005;
fs.mkdirSync(outDir, { recursive: true });

const now = () => new Date().toISOString();
const rawRpcPath = path.join(outDir, "rpc_evidence.jsonl");
const append = (p, obj) => fs.appendFileSync(p, JSON.stringify(obj) + "\n");
let firstStateRequestMs = null;
let lastStateReceiptMs = null;
const accountOwners = new Map();

const captureFetch = async (url, options = {}) => {
  const requestedAt = now();
  const requestedMs = Date.now();
  if (firstStateRequestMs === null) firstStateRequestMs = requestedMs;
  let status = null;
  try {
    const response = await fetch(url, options);
    status = response.status;
    const receivedAt = now();
    lastStateReceiptMs = Date.now();
    const text = await response.clone().text();
    const requestBody = options.body ? JSON.parse(String(options.body)) : null;
    const responseBody = JSON.parse(text);
    if (requestBody?.method === "getMultipleAccounts") {
      const keys = requestBody.params?.[0] || [];
      const values = responseBody?.result?.value || [];
      keys.forEach((key, i) => {
        if (values[i]?.owner) accountOwners.set(key, values[i].owner);
      });
    }
    append(rawRpcPath, {
      requested_at_utc: requestedAt,
      received_at_utc: receivedAt,
      url: String(url),
      method: options.method || "GET",
      request_body: requestBody,
      http_status: status,
      response_body: responseBody,
    });
    return response;
  } catch (error) {
    append(rawRpcPath, {
      requested_at_utc: requestedAt,
      failed_at_utc: now(),
      url: String(url),
      method: options.method || "GET",
      http_status: status,
      error: String(error),
    });
    throw error;
  }
};

function parseCsv(text) {
  const lines = text.trim().split(/\r?\n/);
  const header = lines.shift().split(",");
  return lines.map((line) => {
    const values = line.split(",");
    return Object.fromEntries(header.map((key, i) => [key, values[i] ?? ""]));
  });
}

async function dexPairs(poolAddresses) {
  const result = new Map();
  const raw = [];
  for (let i = 0; i < poolAddresses.length; i += 30) {
    const batch = poolAddresses.slice(i, i + 30);
    const url = `https://api.dexscreener.com/latest/dex/pairs/solana/${batch.join(",")}`;
    const requestedAt = now();
    const response = await fetch(url, { headers: { "User-Agent": "ResolantReadOnlyResearch/0.1" } });
    const receivedAt = now();
    const receivedMs = Date.now();
    const body = await response.json();
    raw.push({ requested_at_utc: requestedAt, received_at_utc: receivedAt, url, http_status: response.status, response_body: body });
    for (const pair of body.pairs || []) result.set(pair.pairAddress, { pair, receivedMs });
  }
  fs.writeFileSync(path.join(outDir, "dex_evidence.json"), JSON.stringify(raw, null, 2) + "\n");
  return result;
}

function quoteUnitsForUsd(pair, quoteMint, swapInputUsd) {
  if (quoteMint === USDC) return { units: BigInt(Math.floor(swapInputUsd * 1e6)), quote_usd: 1 };
  if (quoteMint !== WSOL) throw new Error("unsupported quote mint");
  const priceUsd = Number(pair?.priceUsd);
  const priceNative = Number(pair?.priceNative);
  const solUsd = priceUsd / priceNative;
  if (!(solUsd > 0 && Number.isFinite(solUsd))) throw new Error("missing SOL/USD conversion from exact pair");
  return { units: BigInt(Math.floor((swapInputUsd / solUsd) * 1e9)), quote_usd: solUsd };
}

function bnJson(value) {
  if (BN.isBN(value)) return value.toString(10);
  if (value instanceof PublicKey) return value.toBase58();
  if (Array.isArray(value)) return value.map(bnJson);
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, bnJson(v)]));
  return value;
}

async function main() {
  const sample = parseCsv(fs.readFileSync(path.join(root, "results", "first_market_sample.csv"), "utf8"));
  const candidates = sample.filter((r) => r.pool_liquidity_age_prefilter_only === "True" && r.dex === "pumpswap");
  const pairMap = await dexPairs(candidates.map((r) => r.fixed_pool_address));
  const connection = new Connection(rpcUrl, { commitment: rpcCommitment, fetch: captureFetch });
  // Warm the public RPC/TLS path. This request is preserved but excluded from the quote-state age.
  await connection.getSlot(rpcCommitment);
  firstStateRequestMs = null;
  lastStateReceiptMs = null;
  const sdk = new OnlinePumpAmmSdk(connection);
  const poolKeys = candidates.map((r) => new PublicKey(r.fixed_pool_address));
  const state = await sdk.multiHopPoolHops(poolKeys);
  const assembledMs = Date.now();
  const stateWindowMs = assembledMs - firstStateRequestMs;
  const receiptToQuoteMs = assembledMs - lastStateReceiptMs;
  const rows = [];
  for (let i = 0; i < candidates.length; i++) {
    const candidate = candidates[i];
    const hop = state.hops[i];
    const row = {
      observed_at_utc: now(),
      mint: candidate.mint,
      symbol: candidate.symbol,
      pool_address: candidate.fixed_pool_address,
      exact_pool_owner_verified: accountOwners.get(candidate.fixed_pool_address) === PUMP_AMM_PROGRAM.toBase58(),
      exact_base_mint_verified: hop.pool.baseMint.toBase58() === candidate.mint,
      canonical_pump_pool_verified: isPumpPool(hop.pool.baseMint, hop.pool.creator),
      quote_mint: hop.pool.quoteMint.toBase58(),
      state_window_ms: stateWindowMs,
      receipt_to_quote_ms: receiptToQuoteMs,
      max_quote_age_ms: maxAgeMs,
      decision: "REJECT",
      reasons: [],
    };
    try {
      if (!row.exact_pool_owner_verified) row.reasons.push("wrong pool program owner");
      if (!row.exact_base_mint_verified) row.reasons.push("pool base mint mismatch");
      if (!row.canonical_pump_pool_verified) row.reasons.push("noncanonical pool");
      if (stateWindowMs > maxAgeMs) row.reasons.push("quote state window stale");
      const pairRecord = pairMap.get(candidate.fixed_pool_address);
      if (!pairRecord) row.reasons.push("exact DEX pair missing");
      const marketReferenceAgeMs = pairRecord ? assembledMs - pairRecord.receivedMs : null;
      if (marketReferenceAgeMs === null || marketReferenceAgeMs > maxMarketReferenceAgeMs) row.reasons.push("market reference stale");
      const swapInputUsd = (positionUsd - allocatedDataUsd - buyFixedUsd) * (1 - localFeeFraction) * (1 - adverseAllowanceFraction);
      const { units, quote_usd: quoteUsd } = quoteUnitsForUsd(pairRecord?.pair, row.quote_mint, swapInputUsd);
      const buy = multiHopSwapQuote({
        inMint: hop.pool.quoteMint,
        hops: [hop],
        amountIn: new BN(units.toString()),
        slippage: 0,
        globalConfig: state.globalConfig,
        feeConfig: state.feeConfig,
      });
      const sell = multiHopSwapQuote({
        inMint: hop.pool.baseMint,
        hops: [hop],
        amountIn: buy.amountOut,
        slippage: 0,
        globalConfig: state.globalConfig,
        feeConfig: state.feeConfig,
      });
      const decimals = row.quote_mint === WSOL ? 9 : 6;
      const soldQuote = Number(sell.amountOut.toString()) / 10 ** decimals;
      const routeExitUsd = soldQuote * quoteUsd;
      const routeRatio = Number(sell.amountOut.toString()) / Number(units);
      const netAfterLocalAndLatency = routeExitUsd * (1 - localFeeFraction) * (1 - adverseAllowanceFraction);
      const recoverableUsd = Math.max(0, netAfterLocalAndLatency - sellFixedUsd);
      const allInRoundtripCost = 1 - recoverableUsd / positionUsd;
      Object.assign(row, {
        position_budget_usd: positionUsd,
        pool_swap_input_usd: swapInputUsd,
        market_reference_age_ms: marketReferenceAgeMs,
        max_market_reference_age_ms: maxMarketReferenceAgeMs,
        quote_input_raw: units.toString(),
        base_output_raw: buy.amountOut.toString(),
        immediate_sell_output_raw: sell.amountOut.toString(),
        route_only_roundtrip_ratio: routeRatio,
        route_exit_usd: routeExitUsd,
        all_in_recoverable_usd: recoverableUsd,
        all_in_roundtrip_cost_fraction: allInRoundtripCost,
        pool_state: bnJson({
          base_reserve: hop.poolBaseAmount,
          quote_vault: hop.poolQuoteAmount,
          virtual_quote_reserves: hop.pool.virtualQuoteReserves,
          protocol_fee_bucket: hop.pool.protocolFees,
          creator_fee_bucket: hop.pool.creatorFees,
          base_mint_supply: hop.baseMintSupply,
          mayhem: hop.pool.isMayhemMode,
          cashback: hop.pool.isCashbackCoin,
          configured_creator_fee_bps: hop.pool.creatorFeeBps,
        }),
        cost_model: {
          local_buy_fee_fraction: localFeeFraction,
          local_sell_fee_fraction: localFeeFraction,
          adverse_entry_allowance_fraction: adverseAllowanceFraction,
          adverse_exit_allowance_fraction: adverseAllowanceFraction,
          allocated_data_usd: allocatedDataUsd,
          buy_fixed_usd: buyFixedUsd,
          sell_fixed_usd: sellFixedUsd,
          note: "Official SDK state quote plus existing conservative non-pool assumptions; no transaction simulation or fill.",
        },
      });
      if (allInRoundtripCost > 0.06) row.reasons.push("all-in same-state roundtrip exceeds 6%");
      if (row.reasons.length === 0) row.decision = "CAPACITY_PASS_ONLY";
    } catch (error) {
      row.reasons.push(String(error?.message || error));
    }
    rows.push(row);
  }
  const summary = {
    status: "read-only current-state engineering probe; not historical fills or strategy evidence",
    completed_at_utc: now(),
    official_sdk: "@pump-fun/pump-swap-sdk@2.1.0",
    rpc_commitment: rpcCommitment,
    candidate_source: "five PumpSwap pools from the fixed initial pool/liquidity prefilter",
    candidates: rows.length,
    capacity_pass_only: rows.filter((r) => r.decision === "CAPACITY_PASS_ONLY").length,
    rejected: rows.filter((r) => r.decision === "REJECT").length,
    state_window_ms: stateWindowMs,
    max_quote_age_ms: maxAgeMs,
    results: rows,
  };
  fs.writeFileSync(path.join(outDir, "quote_results.json"), JSON.stringify(summary, null, 2) + "\n");
  console.log(JSON.stringify(summary, null, 2));
}

main().catch((error) => {
  fs.writeFileSync(path.join(outDir, "fatal_error.json"), JSON.stringify({ failed_at_utc: now(), error: String(error), stack: error?.stack }, null, 2) + "\n");
  console.error(error);
  process.exitCode = 1;
});
