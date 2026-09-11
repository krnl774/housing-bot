# Setup: housing bot on GitHub (free, 24/7) with Telegram + Plaza auto-apply

When you're done, GitHub's servers check Plaza and Roomspot about **once a minute**.
You get a Telegram message for every new listing in Enschede. On Plaza the bot also
**applies automatically** for listings that match your Plaza preferences (the green house),
bigger rooms on higher floors first, and tells you each time it applies.

You need: Telegram, a free GitHub account, and your Plaza login. About 20 minutes.

---

## 1. Telegram bot token

1. In Telegram open **@BotFather** (blue check mark), send `/newbot`.
2. Pick a name, then a username ending in `bot`.
3. Copy the **token** it gives you (looks like `8123456789:AAH3k...`). Treat it like a password.

## 2. Your chat ID

1. Open your new bot, press **Start**, send it `hi`.
2. In your browser open `https://api.telegram.org/bot<TOKEN>/getUpdates` (your token instead of `<TOKEN>`).
3. The number after `"chat":{"id":` is your **chat ID**. Empty `"result":[]`? Send another message and refresh.

## 3. Create the GitHub repository

1. Sign in at https://github.com and go to https://github.com/new
2. Name: `housing-bot`. Choose **Public** (free scheduled runs need that; only the code is public).
3. Leave "Add a README" **unticked**. Click **Create repository**.

## 4. Add your secrets (before uploading the code)

In the new repo: **Settings → Secrets and variables → Actions → New repository secret**.
Add these four. The names must match exactly:

| Name | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | token from step 1 |
| `TELEGRAM_CHAT_ID` | number from step 2 |
| `PLAZA_USERNAME` | your Plaza username |
| `PLAZA_PASSWORD` | your Plaza password |

Secrets are encrypted. Nobody can read them back, not even you, and GitHub hides them in logs.
Without the two `PLAZA_` secrets the bot only notifies and never applies.

## 5. Upload the code

Open **PowerShell** and run these lines one by one (replace `YOUR-USERNAME`):

```powershell
cd "C:\Personal Projects\PlazaBot\Plaza-Apartment-scraper"
New-Item -ItemType Directory -Force .github\workflows | Out-Null
Move-Item housing-watcher.yml .github\workflows\ -Force -ErrorAction SilentlyContinue
git remote set-url origin https://github.com/YOUR-USERNAME/housing-bot.git
git rm --cached --ignore-unmatch seen_listings.json seen_listings_plaza.json seen_listings_roomspot.json
git add -A
git commit -m "Housing bot: Telegram, auto-apply, fast mode"
git push -u origin main
```

A browser window may ask you to sign in to GitHub. That's normal.
If `git commit` says *Please tell me who you are*, run this once, then commit again:

```powershell
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

## 6. Test it

On your repo page open the **Actions** tab (if asked, click **I understand my workflows, go ahead and enable them**).
Click **Housing watcher** on the left → **Run workflow** → choose a mode → green **Run workflow**:

1. `test-telegram`: you should get ✅ *Your housing bot can reach you.*
2. `check-plaza-login`: logs in to Plaza **without applying** and sends you what it sees:
   your preferences, and which listings it would apply to.

After that, nothing else to do. The bot starts by itself every 5 minutes and then keeps
checking every minute. The first time, you get an overview per site ("👋 Now watching…").

**What you'll get on Telegram**

- ✅ **Applied on Plaza**: it applied for you, with the listing and your place in line if Plaza shows it
- 🏢 / 🏠 **New on Plaza / Roomspot**: a new listing it didn't apply to (doesn't match your preferences, or Roomspot)
- ❌ it tried but Plaza refused, so apply yourself via the button
- ⚠️ login or site problems · 🟢 one "still watching" message per day

---

## Your settings

On GitHub open `scraper.py`, click ✏️, and change the **YOUR SETTINGS** part at the top, then **Commit changes**:

```python
CITIES = ["Enschede"]          # add "Deventer" etc. to include other cities ([] = all)
AUTO_APPLY = True              # False = only notify
ONLY_PREFERENCE_MATCHES = True # only apply to green-house listings
HIGH_FLOOR_FROM = 6            # "high floor" = 6th floor and up
BIG_FROM_M2 = 22               # "big" = 22 m² or more
MAX_APPLICATIONS_PER_CHECK = None   # e.g. 2 to limit how many it applies to at once
```

Which listings count as a match comes from **your preferences on the Plaza website**
(region, type, rent). Change them there and the bot follows automatically.

Priority when several listings appear at once: **big + high floor → high floor → the rest**,
and within each group bigger first, then higher.

To pause the bot: Actions → Housing watcher → **⋯ → Disable workflow**.

## Troubleshooting

| Problem | Fix |
|---|---|
| `chat not found` | Open your bot in Telegram and press **Start**. Check the chat ID secret. |
| `Unauthorized` | Telegram token is wrong. Copy it again from BotFather into the secret. |
| ⚠️ "username or password is wrong" | Fix the `PLAZA_` secrets. The bot waits 30+ min between login attempts so it never locks your account. |
| ⚠️ "two-step verification" | The bot can't do that. Turn it off for Plaza or use notify-only (`AUTO_APPLY = False`). |
| Lots of **Cancelled** runs in the Actions tab | Normal: each run lasts ~9 min, and runs that would overlap are skipped. |
| "Save seen listings" fails with *permission denied* | Settings → Actions → General → Workflow permissions → **Read and write** → Save. |
| Daily 🟢 message stopped | Open Actions. If GitHub paused the workflow, click **Enable workflow**. |
| You changed files on your PC and `git push` is rejected | Run `git pull` first (the bot saves small updates to GitHub). |

## Security, honestly

- Your Plaza login is only in GitHub Secrets. It's never in the code, the logs or the saved files.
  The public logs only show counts ("1 new, 1 applied"), never addresses or your details.
- Use a Plaza password you don't use anywhere else.
- If anything leaks: change your Plaza password and update the secret; revoke the Telegram
  token with BotFather (`/revoke`).
- Plaza says applying happens through its website and doesn't mention bots. The bot uses the
  website's own apply function, but Plaza could still object. Your call.
- Fast mode uses GitHub's free service harder than it's meant for. If GitHub objects, the same
  code runs on a small server (see below).

## Running it somewhere else (optional)

On your PC or a server: `pip install -r requirements.txt`, copy `env.example` to `.env`,
fill it in, then `python scraper.py` (checks every 60 s until stopped).

## Adding another website

Sites on the same platform as Plaza and Roomspot only need a new block in `SITES` in
`scraper.py`. Send the site's address to Claude to add it.
