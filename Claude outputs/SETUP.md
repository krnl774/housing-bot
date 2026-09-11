# Setup: run the housing bot 24/7 for free (GitHub Actions + Telegram)

When you're done, GitHub's servers check Plaza and Roomspot about every 5 minutes
and your phone gets a Telegram message for every new listing. Your laptop can be off.

Takes about 15 minutes. You need a Telegram account and a (free) GitHub account.

---

## 1. Create your Telegram bot (2 min)

1. In Telegram, search for **@BotFather** (the one with the blue check mark) and open it.
2. Send `/newbot`.
3. Give it a name (anything, e.g. `Cosmin Housing`), then a username that ends in `bot`
   (e.g. `cosmin_housing_bot`).
4. BotFather replies with a **token** that looks like `8123456789:AAH3k...`.
   Copy it somewhere safe. **Treat it like a password.** Don't put it in any file.

## 2. Find your chat ID (2 min)

1. Open your new bot in Telegram (BotFather sends a link) and press **Start**, then send it `hi`.
2. In your browser, open this address, with your token pasted in place of `<TOKEN>`:
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
3. Look for `"chat":{"id":` followed by a number, e.g. `"chat":{"id":612345678,`.
   That number is your **chat ID**.
   If you only see `"result":[]`, send the bot another message and refresh the page.

## 3. Create your GitHub repository (2 min)

1. Sign in at https://github.com and go to https://github.com/new
2. Repository name: e.g. `housing-bot`
3. Choose **Public**. Free scheduled runs only work reliably on public repos.
   (Only the code is public. Your token and chat ID go into encrypted Secrets in step 5.)
4. Leave "Add a README" **unticked** and click **Create repository**.

## 4. Upload the code

Your folder `C:\Personal Projects\PlazaBot\Plaza-Apartment-scraper` is already a git
repository (it was cloned from someone else's GitHub). Point it at your new repo and push.

Open **PowerShell** and run these lines one by one, replacing `YOUR-USERNAME`:

```powershell
cd "C:\Personal Projects\PlazaBot\Plaza-Apartment-scraper"
# first time only: move the workflow file into the folder GitHub looks in
New-Item -ItemType Directory -Force .github\workflows | Out-Null
Move-Item housing-watcher.yml .github\workflows\ -ErrorAction SilentlyContinue
git remote set-url origin https://github.com/YOUR-USERNAME/housing-bot.git
git rm --cached --ignore-unmatch seen_listings.json seen_listings_plaza.json seen_listings_roomspot.json
git add -A
git commit -m "Telegram version + GitHub Actions"
git push -u origin main
```

A browser window may pop up asking you to sign in to GitHub. That's normal.
If `git commit` says *Please tell me who you are*, run these two lines once and commit again:

```powershell
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

Later on, the bot saves its own small updates to GitHub. So before you change files on your
PC and push again, run `git pull` first (or edit files directly on the GitHub website).

<details>
<summary>No git / the commands fail? Upload through the website instead</summary>

1. On your empty repo page click **uploading an existing file**.
2. Drag in these files: `scraper.py`, `requirements.txt`, `README.md`, `SETUP.md`,
   `env.example`, `.gitignore`. Click **Commit changes**.
3. Click **Add file → Create new file**. As the name type
   `.github/workflows/housing-watcher.yml` (typing the `/` makes the folders).
4. Open `housing-watcher.yml` from your folder in Notepad, copy
   everything, paste it into the page, and click **Commit changes**.
</details>

## 5. Add your secrets (2 min)

On your repo page: **Settings → Secrets and variables → Actions → New repository secret**.
Add two secrets (the names must match exactly):

| Name | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | the token from step 1 |
| `TELEGRAM_CHAT_ID` | the number from step 2 |

## 6. Test it

1. Open the **Actions** tab of your repo. If GitHub asks, click
   **I understand my workflows, go ahead and enable them**.
2. Click **Housing watcher** on the left, then **Run workflow** (right side).
3. Tick **Only send a Telegram test message**, then click the green **Run workflow**.
   Within a minute you should get: ✅ *Your housing bot can reach you.*
4. Run it once more **without** the tick. You'll get one overview message per site
   ("👋 Now watching Plaza…") listing what's online right now.

That's it. From now on it runs by itself about every 5 minutes, and you get:

- 🏢 / 🏠 a message with photo, price, size and a button for **every new listing**
- 🟢 one "still watching" message per day around 09:00, so you know it's alive
- ⚠️ a warning if a site stops responding for about an hour

The first automatic (scheduled) run can take up to an hour to appear after setup.

---

## Changing what you get notified about

On GitHub open `scraper.py`, click the ✏️ pencil, and edit the **YOUR SETTINGS** part at the top:

```python
ONLY_TYPES = ["Studio"]   # only studios ([] = everything)
MAX_RENT = 900            # skip anything above €900/month (None = no limit)
DAILY_HEARTBEAT = True    # False to turn off the daily "still watching" message
```

Click **Commit changes**. The next run uses the new settings.
To stop the bot entirely: Actions tab → Housing watcher → **⋯ → Disable workflow**.

## Troubleshooting

| Problem | Fix |
|---|---|
| Test run is red, log says `chat not found` | Open your bot in Telegram and press **Start** first. Check the chat ID. |
| Log says `Unauthorized` | The token is wrong. Copy it again from BotFather and update the secret. |
| Log says `set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID` | A secret is missing or the name has a typo. |
| "Save seen listings" step fails with *permission denied* | Settings → Actions → General → Workflow permissions → **Read and write** → Save. |
| Daily 🟢 message stopped | Open the Actions tab. GitHub pauses schedules on repos with no activity for 60 days (the bot's own daily save normally prevents that). Click **Enable workflow**. |
| Runs arrive 10–20 min apart instead of 5 | Normal at busy times on GitHub's free runners. |

## Security notes

- The bot never logs in anywhere and never needs your email or Plaza password.
- Your token and chat ID live only in GitHub Secrets. GitHub hides them in logs,
  and the script blanks the token out of its own messages too.
- If you think your token leaked: BotFather → `/revoke` → pick your bot → put the new
  token in the `TELEGRAM_BOT_TOKEN` secret.
- The public repo shows the code and a list of listing numbers the bot has seen. Nothing personal.
- GitHub's terms expect Actions to be used for the repo's own software. Small personal
  jobs like this are common, but if GitHub ever objects, the same code runs unchanged on a VPS.

## Running it somewhere else (optional)

Same code, no GitHub needed. On your PC or a VPS:

```bash
pip install -r requirements.txt
copy env.example .env        # (Linux/Mac: cp env.example .env) then fill in token + chat id
python scraper.py --test     # test message
python scraper.py            # checks every 5 minutes until you stop it
```

## Adding another website

Many Dutch housing sites run on the same platform as Plaza and Roomspot ("zig365").
Those only need a new block in `SITES` in `scraper.py`. Sites on other platforms need
a small new reader function. Send the site's address to Claude and it can add it.
