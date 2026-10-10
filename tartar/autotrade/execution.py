"""Live execution for the agent: route selection and the executors that buy and sell a Solana token.

Routes (profitability §3.19, measured by the execution-cost thread; not re-measured here):

* ``jupiter``: Jupiter's Swap API, signed locally with our own wallet (``TARTAR_WALLET_KEY``, a base58
  secret key in an environment secret). No route fee; the empty token account is closed after a sell
  so its rent comes back. Round trip on a deep PumpSwap pool ~1.1% at 0.01 SOL.
* ``lightning``: PumpPortal's Lightning API (``PUMPPORTAL_API_KEY``), its custodial wallet. 1% fee per
  side on top of the pool's; rent cannot be reclaimed. Round trip measured at -3.07% on CATE.
* ``dry``: Jupiter quotes only. Nothing is signed or sent and no key is needed; the "fill" is what the
  quote says the route would have returned at that moment. Used by mode ``dry_live``.

``select_route`` prefers Jupiter whenever its key exists, else Lightning, else nothing (the agent stays
on paper). Every executor returns a ``Fill`` with the SOL and token amounts the wallet actually moved
(read from the confirmed transaction), so the broker can compare each live fill with its paper twin.

Sending is safe by construction rather than by care:

* Nothing here decides *whether* to trade; ``broker.LiveBroker`` only builds a signing executor in mode
  ``live`` with ``live_approved_on`` matching ``TARTAR_LIVE_APPROVED`` and a route key present.
* Before signing, ``check_tx`` refuses any transaction whose fee payer is not our wallet or that needs a
  second signer (a malformed or hostile swap response cannot spend from us in someone else's name).
* A sent transaction ends in one of three states: confirmed (fill read from the chain), failed (it
  errored on chain, or its blockhash expired without it landing: nothing moved), or ``unknown`` (no
  answer before the timeout). The broker treats ``unknown`` as possibly filled: it records the leg in
  ``live.orphans`` with its signature and halts that strategy's live entries, never retrying blind.
* ``simulate=True`` (both routes) builds the real transaction for a stand-in wallet and has the RPC
  simulate it with signature checks off: no key, nothing sent (``python -m tartar.autotrade dry-swap``).
"""

from __future__ import annotations

import base64
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any

SOL = "So11111111111111111111111111111111111111112"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
STAND_IN = "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM"  # dry simulations run as this wallet; we never hold its key
LIGHTNING = "https://pumpportal.fun/api/trade"
TRADE_LOCAL = "https://pumpportal.fun/api/trade-local"  # same order, returned unsigned (used to simulate the route)


def select_route(live_cfg: dict, env=None) -> str | None:
    """The route to trade on: config ``live.route`` ("auto", "jupiter", "lightning" or "dry"), limited to the
    keys present. "auto" prefers Jupiter (no route fee) over Lightning (1% per side)."""
    env = os.environ if env is None else env
    want = live_cfg.get("route", "auto")
    if want == "dry":
        return "dry"
    if want in ("auto", "jupiter") and env.get("TARTAR_WALLET_KEY"):
        return "jupiter"
    if want in ("auto", "lightning") and env.get("PUMPPORTAL_API_KEY"):
        return "lightning"
    return None


@dataclass
class Fill:
    """One leg as the wallet saw it. ``sol`` is SOL spent (buy) or received (sell), network fees included and
    token-account rent excluded (it is reported in ``rent_sol``); ``token_raw`` the token amount bought or
    sold in base units."""

    route: str
    leg: str  # "buy" | "sell"
    mint: str
    ok: bool
    sol: float = 0.0
    token_raw: int = 0
    fee_sol: float = 0.0
    rent_sol: float = 0.0
    quote_out: int | None = None  # what the route's quote promised just before sending
    signature: str | None = None
    sent_at: float | None = None
    confirmed_at: float | None = None
    dry: bool = False
    unknown: bool = False  # sent, but whether it landed is not known: treat as possibly filled
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class Chain:
    """Solana JSON-RPC: retries 429s, confirms signatures, reads a transaction's effect on the wallet."""

    def __init__(self, http=None, url: str | None = None, sleep=time.sleep):
        import httpx

        self.http = http or httpx.Client(timeout=30)
        self.url = url or os.environ.get("SOLANA_RPC_HTTP", "https://api.mainnet-beta.solana.com")
        self.sleep = sleep

    def call(self, method: str, params: list):
        for wait in (1, 2, 4, 8, 0):
            r = self.http.post(self.url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
            if r.status_code != 429 or not wait:
                break
            self.sleep(wait)
        r.raise_for_status()
        body = r.json()
        if body.get("error"):
            raise RuntimeError(f"{method}: {body['error']}")
        return body.get("result")

    def balance_sol(self, wallet: str) -> float:
        return self.call("getBalance", [wallet, {"commitment": "confirmed"}])["value"] / 1e9

    def held_raw(self, wallet: str, mint: str) -> int:
        return self.held(wallet, mint)[0]

    def held(self, wallet: str, mint: str) -> tuple[int, int | None]:
        """The wallet's balance of ``mint`` in base units, and the mint's decimals (None if no account)."""
        res = self.call("getTokenAccountsByOwner", [wallet, {"mint": mint}, {"encoding": "jsonParsed"}])["value"]
        amts = [a["account"]["data"]["parsed"]["info"]["tokenAmount"] for a in res]
        return sum(int(t["amount"]) for t in amts), (int(amts[0]["decimals"]) if amts else None)

    def decimals(self, mint: str) -> int:
        return int(self.call("getTokenSupply", [mint])["value"]["decimals"])

    def confirm(self, signature: str, timeout: float = 90.0, last_valid: int | None = None,
                clock=time.time) -> tuple[dict | None, float | None]:
        """(transaction, time seen) once confirmed; ({"meta": {"err": ...}}, t) if it failed on chain or its
        blockhash expired (``last_valid``, the last block height it could land in) without it landing;
        (None, None) if neither is known by ``timeout``; (None, t) if confirmed but unreadable."""
        end = clock() + timeout
        polls = 0
        while clock() < end:
            st = self.call("getSignatureStatuses", [[signature], {"searchTransactionHistory": True}])["value"][0]
            if st and st.get("err"):
                return {"meta": {"err": st["err"]}}, clock()
            if not st and last_valid is not None and polls % 4 == 3:
                if self.call("getBlockHeight", [{"commitment": "confirmed"}]) > last_valid:
                    # status first, height second: if it had landed by then, this re-check sees it
                    st = self.call("getSignatureStatuses", [[signature], {"searchTransactionHistory": True}])["value"][0]
                    if not st:
                        return {"meta": {"err": f"expired: not landed by block height {last_valid}"}}, clock()
                    continue
            polls += 1
            if st and st.get("confirmationStatus") in ("confirmed", "finalized"):
                seen = clock()
                for _ in range(20):
                    tx = self.call("getTransaction", [signature, {"encoding": "jsonParsed", "commitment": "confirmed",
                                                                  "maxSupportedTransactionVersion": 0}])
                    if tx:
                        return tx, seen
                    self.sleep(1.0)
                return None, seen
            self.sleep(0.5)
        return None, None


def effects(tx: dict, mint: str, wallet: str) -> dict:
    """The wallet's SOL change, token change (base units), network fee and new token-account rent."""
    meta = tx["meta"]
    if meta.get("err") or "transaction" not in tx:
        return {"err": meta.get("err") or "no transaction"}
    keys = [k["pubkey"] if isinstance(k, dict) else k for k in tx["transaction"]["message"]["accountKeys"]]
    i_w = keys.index(wallet) if wallet in keys else 0

    def tokens(balances):
        return sum(int(b["uiTokenAmount"]["amount"]) for b in balances or [] if b.get("mint") == mint and b.get("owner") == wallet)

    rent = 0.0
    for i in range(len(keys)):
        if i != i_w and meta["preBalances"][i] == 0 and meta["postBalances"][i] > 0 and any(
                b.get("accountIndex") == i and b.get("owner") == wallet for b in meta.get("postTokenBalances") or []):
            rent += meta["postBalances"][i] / 1e9
    return {"err": None, "sol_change": (meta["postBalances"][i_w] - meta["preBalances"][i_w]) / 1e9,
            "token_change": tokens(meta.get("postTokenBalances")) - tokens(meta.get("preTokenBalances")),
            "fee_sol": meta["fee"] / 1e9 if i_w == 0 else 0.0, "rent_sol": rent, "slot": tx.get("slot")}


def check_tx(raw: bytes, wallet: str) -> None:
    """Refuse to sign a transaction that is not ours alone: the fee payer must be ``wallet`` and it must need
    exactly one signature."""
    from solders.transaction import VersionedTransaction

    msg = VersionedTransaction.from_bytes(raw).message
    keys = [str(k) for k in msg.account_keys]
    if not keys or keys[0] != wallet:
        raise RuntimeError(f"transaction fee payer {keys[:1]} is not our wallet")
    if msg.header.num_required_signatures != 1:
        raise RuntimeError(f"transaction needs {msg.header.num_required_signatures} signatures, expected 1")


def fill_from(route: str, leg: str, mint: str, eff: dict | None, **kw) -> Fill:
    if not eff:  # sent, outcome not established
        return Fill(route, leg, mint, False, unknown=True, error="not confirmed: outcome unknown", **kw)
    if eff.get("err"):
        return Fill(route, leg, mint, False, error=str((eff or {}).get("err") or "not confirmed"), **kw)
    if leg == "buy":
        sol, raw = -eff["sol_change"] - eff["rent_sol"], eff["token_change"]
    else:
        sol, raw = eff["sol_change"], -eff["token_change"]
    ok = raw > 0 and sol > 0
    return Fill(route, leg, mint, ok, sol=sol, token_raw=raw, fee_sol=eff["fee_sol"], rent_sol=eff["rent_sol"],
                error=None if ok else "no tokens moved", extra={"slot": eff.get("slot")}, **kw)


class Quotes:
    """Jupiter quotes (keyless lite-api unless ``JUPITER_API_KEY`` is set)."""

    def __init__(self, http=None, slippage_bps: int = 300):
        import httpx

        key = os.environ.get("JUPITER_API_KEY")
        self.base = "https://api.jup.ag" if key else "https://lite-api.jup.ag"
        self.http = http or httpx.Client(timeout=30, headers={"x-api-key": key} if key else None)
        self.slippage_bps = slippage_bps

    def quote(self, input_mint: str, output_mint: str, amount: int) -> dict:
        r = self.http.get(f"{self.base}/swap/v1/quote", params={"inputMint": input_mint, "outputMint": output_mint,
                                                                "amount": int(amount), "slippageBps": self.slippage_bps})
        r.raise_for_status()
        q = r.json()
        if "outAmount" not in q:
            raise RuntimeError(f"no route: {str(q)[:200]}")
        return q

    def swap(self, quote: dict, wallet: str, priority_sol: float) -> tuple[bytes, int | None]:
        """The unsigned swap transaction and the last block height it can land in."""
        r = self.http.post(f"{self.base}/swap/v1/swap", json={
            "quoteResponse": quote, "userPublicKey": wallet, "dynamicComputeUnitLimit": True,
            "prioritizationFeeLamports": int(round(priority_sol * 1e9))})
        r.raise_for_status()
        body = r.json()
        if body.get("simulationError"):
            raise RuntimeError(f"Jupiter simulation failed: {str(body['simulationError'])[:200]}")
        lv = body.get("lastValidBlockHeight")
        return base64.b64decode(body["swapTransaction"]), int(lv) if lv is not None else None

    def swap_tx(self, quote: dict, wallet: str, priority_sol: float) -> bytes:
        return self.swap(quote, wallet, priority_sol)[0]

    def sol_usd(self) -> float:
        return int(self.quote(SOL, USDC, 10**9)["outAmount"]) / 1e6


class DryExecutor:
    """Quote-only: what Jupiter would have filled right now, less the network fee a real send would pay
    (base fee + priority per leg). Signs and sends nothing."""

    name = "dry"
    BASE_FEE_SOL = 0.000005

    def __init__(self, quotes: Quotes | None = None, balance_sol: float = 0.05, priority_sol: float = 0.00002):
        self.quotes = quotes or Quotes()
        self._balance = balance_sol
        self._tokens: dict[str, int] = {}
        self.fee_sol = self.BASE_FEE_SOL + priority_sol
        self.wallet = STAND_IN
        self.path = None

    def attach(self, path, seed: dict[str, int] | None = None) -> None:
        """Keep the simulated wallet in ``path`` (written through on every fill, like a chain), so a run that
        dies mid-order leaves it the way a real wallet would be. A new file starts at ``balance_sol`` holding
        ``seed`` (the twins already in the book)."""
        import json
        from pathlib import Path

        self.path = Path(path)
        if not self.path.exists():
            self._tokens = {m: int(r) for m, r in (seed or {}).items() if r}
            self._save()
        self._load()

    def _load(self) -> None:
        import json

        if self.path and self.path.exists():
            w = json.loads(self.path.read_text())
            self._balance, self._tokens = float(w["sol"]), {m: int(r) for m, r in w["tokens"].items()}

    def _save(self) -> None:
        import json

        if self.path:
            keep = json.loads(self.path.read_text()) if self.path.exists() else {}
            keep.update({"sol": round(self._balance, 9), "tokens": self._tokens, "note": "simulated wallet of the dry route (no real funds)"})
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(keep, indent=1, sort_keys=True))
            tmp.replace(self.path)

    def _move(self, sol: float, mint: str, raw: int) -> None:
        self._load()
        self._balance += sol
        left = self._tokens.get(mint, 0) + raw
        if left > 0:
            self._tokens[mint] = left
        else:
            self._tokens.pop(mint, None)
        self._save()

    def balance_sol(self) -> float:
        self._load()
        return self._balance

    def holdings(self, mints) -> dict[str, int]:
        self._load()
        return {m: self._tokens.get(m, 0) for m in mints}

    def sol_usd(self) -> float:
        return self.quotes.sol_usd()

    def buy(self, mint: str, sol: float) -> Fill:
        t0 = time.time()
        try:
            q = self.quotes.quote(SOL, mint, int(sol * 1e9))
        except Exception as exc:  # noqa: BLE001
            return Fill(self.name, "buy", mint, False, dry=True, error=f"{type(exc).__name__}: {exc}"[:300])
        self._move(-(sol + self.fee_sol), mint, int(q["outAmount"]))
        return Fill(self.name, "buy", mint, True, sol=sol + self.fee_sol, token_raw=int(q["outAmount"]), quote_out=int(q["outAmount"]),
                    fee_sol=self.fee_sol, sent_at=t0, confirmed_at=t0, dry=True)

    def sell(self, mint: str, token_raw: int) -> Fill:
        t0 = time.time()
        try:
            q = self.quotes.quote(mint, SOL, token_raw)
        except Exception as exc:  # noqa: BLE001
            return Fill(self.name, "sell", mint, False, dry=True, error=f"{type(exc).__name__}: {exc}"[:300])
        sol = int(q["outAmount"]) / 1e9 - self.fee_sol
        self._move(sol, mint, -token_raw)
        return Fill(self.name, "sell", mint, True, sol=sol, token_raw=token_raw, quote_out=int(q["outAmount"]),
                    fee_sol=self.fee_sol, sent_at=t0, confirmed_at=t0, dry=True)


def simulated(chain: Chain, route: str, leg: str, mint: str, raw: bytes, amount, out: int | None) -> Fill:
    """Have the RPC simulate an unsigned transaction (signature checks off, fresh blockhash). The stand-in
    wallet holds no tokens, so a sell can only be checked as far as the quote and the built transaction."""
    res = chain.call("simulateTransaction", [base64.b64encode(raw).decode(), {
        "encoding": "base64", "sigVerify": False, "replaceRecentBlockhash": True}])["value"]
    sim_ok = res.get("err") is None
    ok = sim_ok or leg == "sell"
    if leg == "buy":
        sol, tok = amount / 1e9, out or 0
    else:
        sol, tok = (out or 0) / 1e9, amount
    return Fill(route, leg, mint, ok, sol=sol, token_raw=tok, quote_out=out, dry=True,
                error=None if ok else str(res.get("err"))[:300],
                extra={"units": res.get("unitsConsumed"), "simulated": sim_ok,
                       **({} if sim_ok else {"simulation_err": str(res.get("err"))[:200], "logs": (res.get("logs") or [])[-5:]})})


def send_signed(chain: Chain, keypair, route: str, leg: str, mint: str, raw: bytes, wallet: str, out: int | None,
                last_valid: int | None, timeout: float = 90.0, guard=None, counter: str | None = None) -> Fill:
    """Sign ``raw`` (already through ``check_tx``) with our key, send it, and read the fill from the chain.
    ``guard`` (the shared live gate, ``gate.require_live``) runs first; if it raises, nothing is signed.
    ``counter``: the swap's other token when it is not SOL (e.g. USDC); its change goes to
    ``extra["counter_change"]`` and decides, with the token change, whether the swap filled."""
    from solders.transaction import VersionedTransaction

    try:
        if guard:
            guard()
    except Exception as exc:  # noqa: BLE001
        return Fill(route, leg, mint, False, quote_out=out, error=f"live gate: {exc}"[:300])

    signed = VersionedTransaction(VersionedTransaction.from_bytes(raw).message, [keypair])
    t0 = time.time()
    try:
        sig = chain.call("sendTransaction", [base64.b64encode(bytes(signed)).decode(), {
            "encoding": "base64", "maxRetries": 5, "preflightCommitment": "processed"}])
    except Exception as exc:  # noqa: BLE001 - a refused send (preflight error) moved nothing
        return Fill(route, leg, mint, False, quote_out=out, sent_at=t0, error=f"send: {exc}"[:300])
    tx, seen = chain.confirm(sig, timeout=timeout, last_valid=last_valid)
    eff = effects(tx, mint, wallet) if tx else None
    if counter and eff and not eff.get("err"):
        c = effects(tx, counter, wallet)["token_change"]
        raw = eff["token_change"] if leg == "buy" else -eff["token_change"]
        ok = raw > 0 and (c < 0 if leg == "buy" else c > 0)
        return Fill(route, leg, mint, ok, sol=-eff["sol_change"], token_raw=raw, fee_sol=eff["fee_sol"], rent_sol=eff["rent_sol"],
                    quote_out=out, signature=sig, sent_at=t0, confirmed_at=seen, error=None if ok else "no tokens moved",
                    extra={"slot": eff.get("slot"), "counter_change": c})
    return fill_from(route, leg, mint, eff, quote_out=out, signature=sig, sent_at=t0, confirmed_at=seen)


class JupiterExecutor:
    """Jupiter Swap API, signed with our own key. ``simulate=True`` builds the same transaction for a stand-in
    wallet and has the RPC simulate it instead (no key, nothing sent)."""

    name = "jupiter"

    def __init__(self, secret: str | None = None, quotes: Quotes | None = None, chain: Chain | None = None,
                 priority_sol: float = 0.00002, simulate: bool = False):
        self.quotes = quotes or Quotes()
        self.chain = chain or Chain()
        self.priority_sol = priority_sol
        self.simulate = simulate
        self.guard = None  # set by the broker to the shared live gate, checked right before each send
        self.keypair = None
        if not simulate:
            from solders.keypair import Keypair

            secret = secret or os.environ.get("TARTAR_WALLET_KEY")
            if not secret:
                raise RuntimeError("TARTAR_WALLET_KEY is not set")
            self.keypair = Keypair.from_base58_string(secret.strip())
        self.wallet = str(self.keypair.pubkey()) if self.keypair else STAND_IN

    def balance_sol(self) -> float:
        return self.chain.balance_sol(self.wallet)

    def holdings(self, mints) -> dict[str, int]:
        return {m: self.chain.held(self.wallet, m)[0] for m in mints}

    def sol_usd(self) -> float:
        return self.quotes.sol_usd()

    def _swap(self, leg: str, mint: str, amount: int) -> Fill:
        pair = (SOL, mint) if leg == "buy" else (mint, SOL)
        try:
            q = self.quotes.quote(*pair, amount)
            raw, last_valid = self.quotes.swap(q, self.wallet, self.priority_sol)
            check_tx(raw, self.wallet)
        except Exception as exc:  # noqa: BLE001
            return Fill(self.name, leg, mint, False, error=f"{type(exc).__name__}: {exc}"[:300])
        out = int(q["outAmount"])
        if self.simulate:
            return simulated(self.chain, self.name, leg, mint, raw, amount, out)
        return send_signed(self.chain, self.keypair, self.name, leg, mint, raw, self.wallet, out, last_valid, guard=self.guard)

    def buy(self, mint: str, sol: float) -> Fill:
        return self._swap("buy", mint, int(sol * 1e9))

    def sell(self, mint: str, token_raw: int) -> Fill:
        f = self._swap("sell", mint, token_raw)
        if f.ok and not self.simulate:
            try:
                f.extra["rent_back_sol"] = self.close_empty(mint)
            except Exception as exc:  # noqa: BLE001 - the rent stays parked; the sell itself is done
                f.extra["close_error"] = f"{type(exc).__name__}: {exc}"[:200]
        return f

    def close_empty(self, mint: str) -> float:
        """Close the wallet's empty token accounts for ``mint`` (rent ~0.002 SOL each comes back)."""
        from solders.hash import Hash
        from solders.instruction import AccountMeta, Instruction
        from solders.message import MessageV0
        from solders.pubkey import Pubkey
        from solders.transaction import VersionedTransaction

        owner = self.keypair.pubkey()
        res = self.chain.call("getTokenAccountsByOwner", [str(owner), {"mint": mint}, {"encoding": "jsonParsed"}])["value"]
        empty = [a for a in res if int(a["account"]["data"]["parsed"]["info"]["tokenAmount"]["amount"]) == 0]
        if not empty:
            return 0.0
        ixs = [Instruction(Pubkey.from_string(a["account"]["owner"]), bytes([9]),  # CloseAccount (SPL Token, Token-2022)
                           [AccountMeta(Pubkey.from_string(a["pubkey"]), False, True), AccountMeta(owner, False, True),
                            AccountMeta(owner, True, False)]) for a in empty]
        blockhash = Hash.from_string(self.chain.call("getLatestBlockhash", [{"commitment": "confirmed"}])["value"]["blockhash"])
        tx = VersionedTransaction(MessageV0.try_compile(owner, ixs, [], blockhash), [self.keypair])
        self.chain.call("sendTransaction", [base64.b64encode(bytes(tx)).decode(), {"encoding": "base64", "maxRetries": 5}])
        return sum(a["account"]["lamports"] for a in empty) / 1e9


class LightningExecutor:
    """PumpPortal Lightning (its custodial wallet; ``live.lightning_wallet`` is that wallet's public key, used
    to read fills and the balance). 1% route fee per side; token-account rent stays parked.

    Sells are sized to the twin: the wallet may hold the same mint for another twin, so "100%" is sent only
    when the twin is everything held. ``simulate=True`` asks PumpPortal's trade-local endpoint for the same
    order as an unsigned transaction for a stand-in wallet and has the RPC simulate it (no key, nothing sent;
    trade-local's fee is 0.5%, so the simulated amounts are a little better than Lightning's)."""

    name = "lightning"
    CONFIRM_S = 150.0  # Lightning gives no blockhash expiry; by then any blockhash it used has expired

    def __init__(self, wallet: str | None = None, api_key: str | None = None, http=None, chain: Chain | None = None,
                 quotes: Quotes | None = None, slippage_pct: float = 5.0, priority_sol: float = 0.00002,
                 simulate: bool = False):
        import httpx

        self.simulate = simulate
        self.guard = None  # set by the broker to the shared live gate, checked right before each send
        if simulate:
            wallet, api_key = wallet or STAND_IN, None
        else:
            if not wallet:
                raise RuntimeError("live.lightning_wallet (the Lightning wallet's public key) is not set")
            api_key = api_key or os.environ.get("PUMPPORTAL_API_KEY")
            if not api_key:
                raise RuntimeError("PUMPPORTAL_API_KEY is not set")
        self.api_key = api_key
        self.wallet = wallet
        self.http = http or httpx.Client(timeout=30)
        self.chain = chain or Chain()
        self.quotes = quotes or Quotes()
        self.slippage_pct, self.priority_sol = slippage_pct, priority_sol

    def balance_sol(self) -> float:
        return self.chain.balance_sol(self.wallet)

    def holdings(self, mints) -> dict[str, int]:
        return {m: self.chain.held(self.wallet, m)[0] for m in mints}

    def sol_usd(self) -> float:
        return self.quotes.sol_usd()

    def _trade(self, leg: str, mint: str, amount, in_sol: bool, quote_out: int | None, raw_amount) -> Fill:
        payload = {"action": leg, "mint": mint, "amount": amount, "denominatedInSol": "true" if in_sol else "false",
                   "slippage": self.slippage_pct, "priorityFee": self.priority_sol, "pool": "auto"}
        if self.simulate:
            try:
                r = self.http.post(TRADE_LOCAL, data={**payload, "publicKey": self.wallet})
                if r.status_code != 200:
                    raise RuntimeError(f"trade-local {r.status_code}: {r.text[:200]}")
                check_tx(r.content, self.wallet)
            except Exception as exc:  # noqa: BLE001
                return Fill(self.name, leg, mint, False, dry=True, quote_out=quote_out, error=f"{type(exc).__name__}: {exc}"[:300])
            return simulated(self.chain, self.name, leg, mint, r.content, raw_amount, quote_out)
        try:
            if self.guard:
                self.guard()
        except Exception as exc:  # noqa: BLE001
            return Fill(self.name, leg, mint, False, quote_out=quote_out, error=f"live gate: {exc}"[:300])
        t0 = time.time()
        try:
            r = self.http.post(LIGHTNING, params={"api-key": self.api_key}, data=payload)
            body = r.json()
        except Exception as exc:  # noqa: BLE001 - no answer: the order may or may not have gone out
            return Fill(self.name, leg, mint, False, unknown=True, quote_out=quote_out, sent_at=t0,
                        error=f"send: no answer ({type(exc).__name__}: {exc})"[:300])
        sig = body.get("signature") if isinstance(body, dict) else None
        if not sig:
            return Fill(self.name, leg, mint, False, quote_out=quote_out, sent_at=t0, error=f"no signature: {r.text[:200]}")
        tx, seen = self.chain.confirm(sig, timeout=self.CONFIRM_S)
        eff = effects(tx, mint, self.wallet) if tx else None
        return fill_from(self.name, leg, mint, eff, quote_out=quote_out, signature=sig, sent_at=t0, confirmed_at=seen)

    def buy(self, mint: str, sol: float) -> Fill:
        try:
            q = int(self.quotes.quote(SOL, mint, int(sol * 1e9))["outAmount"])
        except Exception:  # noqa: BLE001 - the quote is only the reference
            q = None
        return self._trade("buy", mint, sol, True, q, int(sol * 1e9))

    def sell_amount(self, mint: str, token_raw: int):
        """PumpPortal's amount for selling ``token_raw``: "100%" when that is all the wallet holds, else the
        token count in whole units (always the count when simulating)."""
        if self.simulate:  # the stand-in holds none, so "100%" would be nothing: ask for the amount itself
            return token_raw / 10 ** self.chain.decimals(mint)
        held, decimals = self.chain.held(self.wallet, mint)
        if held <= token_raw or decimals is None:
            return "100%"
        return token_raw / 10 ** decimals

    def sell(self, mint: str, token_raw: int) -> Fill:
        try:
            q = int(self.quotes.quote(mint, SOL, token_raw)["outAmount"])
        except Exception:  # noqa: BLE001
            q = None
        try:
            amount = self.sell_amount(mint, token_raw)
        except Exception as exc:  # noqa: BLE001 - not knowing what we hold, don't guess
            return Fill(self.name, "sell", mint, False, quote_out=q, error=f"balance: {exc}"[:300])
        return self._trade("sell", mint, amount, False, q, token_raw)


def make_executor(route: str, live_cfg: dict, env=None):
    """The executor for ``route``. Only ``broker.LiveBroker`` calls this with a signing route, and only in
    mode ``live`` with the approval matching; ``dry`` signs nothing."""
    env = os.environ if env is None else env
    if route == "dry":
        return DryExecutor(balance_sol=float(live_cfg.get("dry_balance_sol", 0.05)), priority_sol=float(live_cfg.get("priority_sol", 0.00002)))
    if route == "jupiter":
        return JupiterExecutor(secret=env.get("TARTAR_WALLET_KEY"), priority_sol=float(live_cfg.get("priority_sol", 0.00002)))
    if route == "lightning":
        return LightningExecutor(live_cfg.get("lightning_wallet", ""), api_key=env.get("PUMPPORTAL_API_KEY"),
                                 priority_sol=float(live_cfg.get("priority_sol", 0.00002)))
    raise RuntimeError(f"no executor for route {route!r}")
