# Continue CodexCoinHunt on your Mac

Prepared October 12, 2026. The phone/cloud work is packaged as `CodexCoinHunt.zip`. This session has not written to your Mac. The installer uses your Mac's home directory when you run it there.

## 1. Open this conversation on desktop

Sign in to the same ChatGPT account and workspace. Look in the **ChatGPT** view for this conversation; Work and Codex histories are separate. Cloud Work conversations can sync across desktop, mobile and web [1]. If it is absent, search chats for `CodexCoinHunt`, then check the account/workspace and archived chats [2].

## 2. Install the complete files

Download **CodexCoinHunt.zip** and **install_codexcoinhunt.py** from the message into Downloads. Run in Terminal:

```bash
python3 ~/Downloads/install_codexcoinhunt.py ~/Downloads/CodexCoinHunt.zip
```

The default destination is `~/Projects/CodexCoinHunt`. It installs the full copy under:

```text
~/Projects/CodexCoinHunt/codex-research/current
```

The installer verifies file hashes before writing, preserves existing files outside its managed directory, and archives an earlier recognized copy under `codex-research/snapshots`. An unrecognized existing `current` folder stays untouched; the installer prints a separate imported path. It does not run project code, install packages, access wallets or make network calls.

## 3. Give desktop GPT access to that folder

In the desktop app, create or edit a **local project** named `CodexCoinHunt`. Attach the installed folder printed by the installer, normally `~/Projects/CodexCoinHunt/codex-research/current`, and make it primary through **Edit project → Add folder / Make primary** [3]. Start the local task from that project. Synced conversation history does not itself provide local-folder access; existing cloud tasks may require a new local task [3].

The printed folder contains `AGENTS.md`, `CLAUDE.md`, `PROJECT_HANDOFF.md`, shared agent notes and the full `research` directory. Existing Claude material elsewhere in `~/Projects/CodexCoinHunt` remains available to you; it was not automatically reviewed or merged.

Paste this into the new local task:

> Continue Resolant Labs' CodexCoinHunt paper research from this local project. Read AGENTS.md, PROJECT_HANDOFF.md, the shared project/task/decision notes and research/Resolant_Memecoin_Project_Tracker.md first. The latest audit has forty further finalized responses and fourteen earlier exact-target swaps. Four sampled buyers supplied 97.21% of sampled buy notional and had already bought the mint; the remaining buyer is unknown. No independent funding cluster, completed strategy position or doubled campaign exists. Check first participation before costly ancestry work, trace carried-in quote-token capital and creator/service roles for later eligible candidates, then run an untouched new-versus-returning participation/capacity comparison with full costs and matched controls. Model candidates are untrained. Keep orders, funding and paid subscriptions disabled; do not handle private keys. Review actual Claude files before incorporating their findings. Update the detailed copy and preserve prior versions and UTC raw evidence.

## 4. Verify the offline research tools

From Terminal:

```bash
cd ~/Projects/CodexCoinHunt/codex-research/current/research
python3 -m unittest discover -s tests -v
```

The research release has **122 distinct engineering tests**, not profitability tests. These require Python **3.10 or newer** and the standard library; the copy installer itself only requires Python 3. Fresh collection commands are documented separately. No model-training dependency or credential is needed for these checks.

## What context is included?

The package contains our current code, recorded observations, source receipts, reports, tests, hypotheses, failed experiments and prior versions. It contains a detailed written research history, not a verbatim export of every chat message. The original phone conversation remains the source for the conversation itself when available in desktop history.

I know the high-level Northstar/Resolant goals you have shared, including paper-only operation and the separate five-minute V1/V2 forecast evaluation. I have not reviewed Claude's unshared chats, current repository, code changes or backtests. Shared notes mark Claude findings as unreviewed until supported by actual files/results.

Official OpenAI documentation checked October 12, 2026:

1. [Desktop Work conversation history](https://learn.chatgpt.com/docs/whats-new).
2. [Cross-device troubleshooting](https://learn.chatgpt.com/docs/reference/troubleshooting).
3. [Projects, local folders and separate file access](https://learn.chatgpt.com/docs/projects?surface=app).
