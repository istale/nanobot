# nanobot (custom maintenance workflow)

This repository is maintained with a **2-branch workflow**:

- `main`: tracks upstream (`HKUDS/nanobot`) as closely as possible
- `custom`: your custom modifications (Gemini Web/CDP/textified patches, etc.)

## Remotes

- `origin` → your fork (this repo)
- `upstream` → official source repo

Check:

```bash
git remote -v
```

---

## Routine update flow (single maintainer)

### 1) Sync `main` from upstream

```bash
git fetch upstream
git checkout main
git pull origin main
git merge --ff-only upstream/main
git push origin main
```

### 2) Rebase `custom` onto latest `main`

```bash
git checkout custom
git rebase main
git push --force-with-lease origin custom
```

---

## One-command sync

Use the helper script in repo root:

```bash
./sync_branches.sh
```

What it does:
1. Verifies repo/remotes/branches
2. Syncs `main` with `upstream/main` using fast-forward only
3. Rebases `custom` on top of latest `main`
4. Pushes both branches to `origin`

---

## Conflict handling

If `git rebase main` reports conflicts on `custom`:

```bash
# resolve files

git add <resolved-files>
git rebase --continue

# if you want to abort
# git rebase --abort
```

Then push again:

```bash
git push --force-with-lease origin custom
```

---

## Notes

- This workflow assumes **single maintainer** on `custom`.
- `--ff-only` keeps `main` clean and prevents accidental merge commits.
- `custom` history is expected to be rewritten after rebase (hence force-with-lease).

---

## Intranet Open WebUI (CDP branch)

For branch `feature/openwebui-cdp-facade`, nanobot gateway can expose an OpenAI-compatible API for Open WebUI.

### Endpoints

- `GET /v1/models`
- `POST /v1/chat/completions` (non-stream)

### Start (Windows / PowerShell)

```powershell
cd D:\nanobot-root\repos\nanobot
.\.venv\Scripts\Activate.ps1

$env:NANOBOT_HOME="D:\nanobot-root\home"
$env:NANOBOT_CHROME_CDP_URL="http://127.0.0.1:9222"
$env:NANOBOT_GEMINI_WEB_URL="https://gemini.google.com/app"

nanobot gateway --port 18790 --verbose --webui-api-host 127.0.0.1 --webui-api-port 18080
```

### Open WebUI settings

- API Base URL: `http://127.0.0.1:18080/v1`
- Model: `nanobot-cdp`

### Quick check

```powershell
curl http://127.0.0.1:18080/v1/models
```
