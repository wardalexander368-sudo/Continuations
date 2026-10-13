# The always-on box (approved by AJ 2026-10-13)

AJ approved the ~$5/month always-on machine on 2026-10-13 ("approved for all, ill add the box in the next few days").
What it runs: `tartar/autotrade/box.py`. It checks the 11 us_capit coins about 90 seconds after every hour closes with
the registered CAPIT Z=4 signal and buys on an Alpaca **paper** account at once (the hourly GitHub runner gets there
~90 min late, which costs about a third of the edge: `reviews/timing-2026-10-11.md`), then sells 24 hours later.
Paper only; it measures what the box adds. It does not change `us_capit` or the live rule's gate.

## What AJ sets up (once)
1. **A small Linux server** (any provider; 1 vCPU / 1 GB is plenty) with Python 3.11+ and git.
2. **A second Alpaca paper account** (Alpaca lets one login hold several paper accounts) and its API key. Use a
   separate account so the hourly runner's account-vs-book check sees only its own trades.
3. **Optional, to see results in the project:** a GitHub fine-grained token for this repo with "Contents: read and
   write", used only on the box. The box commits its files to the branch `box-data`, never to `main`.

## Install
```
git clone https://github.com/wardalexander368-sudo/Continuations.git tartrade && cd tartrade
git checkout -b box-data            # first time; later: git checkout box-data
python3 -m venv .venv && .venv/bin/pip install -e .
cat > ~/.box.env <<'X'               # never commit this file
APCA_API_KEY_ID=...
APCA_API_SECRET_KEY=...
X
chmod 600 ~/.box.env
set -a; . ~/.box.env; set +a; .venv/bin/python -m tartar.autotrade.box once   # one pass: should log nothing or a skip
```
Run it under systemd so it restarts after a reboot (`/etc/systemd/system/tartrade-box.service`):
```
[Unit]
Description=TarTrade box (CAPIT on Alpaca paper)
After=network-online.target
[Service]
WorkingDirectory=/home/USER/tartrade
EnvironmentFile=/home/USER/.box.env
ExecStart=/home/USER/tartrade/.venv/bin/python -m tartar.autotrade.box run --push
Restart=always
User=USER
[Install]
WantedBy=multi-user.target
```
`sudo systemctl enable --now tartrade-box`. Drop `--push` if no token was set up.

## Controls
* Stop new entries: `touch box/HALT` (exits still run). The box writes `HALT` itself when the account differs from its
  book or an order stays open over an hour. Remove the file to resume.
* `$100` per trade, one position per coin, at most 11 open (`--usd`, `--max-open`, `--coins` to change).
* Results: `box/fills.jsonl` (each buy and sell with the signal close, fill price, gap and latency) and
  `box/state.json`, on the `box-data` branch hourly with `--push`.
