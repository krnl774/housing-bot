# Housing bot (Plaza + Roomspot → Telegram, with Plaza auto-apply)

Checks Plaza and Roomspot about once a minute and sends new Enschede listings to Telegram.
On Plaza it can also apply automatically for listings that match your Plaza preferences
(the green house), in your priority order (big rooms on high floors first).

- Runs free on **GitHub Actions**, so no laptop, Raspberry Pi or server needed
- Your Plaza login lives only in encrypted GitHub Secrets. Without it the bot just notifies
- Logs show counts only, never addresses or personal details
- Daily "still watching" message; warnings on login or site problems

**Setup: see [SETUP.md](SETUP.md).**

| File | What it is |
|---|---|
| `scraper.py` | The bot. Settings and websites are at the top. |
| `.github/workflows/housing-watcher.yml` | Tells GitHub when and how to run the bot |
| `state/` | Listings already handled (written by the bot) |
| `env.example` | Template for running on your own PC/server |
| `deploy.md`, `setup_vps.sh`, `ecosystem.config.js`, `run_scraper.sh` | Old server setup (PM2), only if you move off GitHub |

Based on [ramzxy/Plaza-Apartment-scraper](https://github.com/ramzxy/Plaza-Apartment-scraper). Personal use only.
