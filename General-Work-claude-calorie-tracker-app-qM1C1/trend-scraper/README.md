# Trend Scraper

Automatically tracks what's going viral on Reddit and Google Trends,
scores topics by how fast they're spreading, and serves the results
through a simple web API.

---

## ⚡ Quickstart — pick one option

### Option A · Docker (easiest — one command, nothing else to install)

> Requires: [Docker Desktop](https://www.docker.com/products/docker-desktop/)

```bash
# 1. Download the project
git clone <repo-url>
cd trend-scraper

# 2. Start everything
docker compose up
```

That's it. Docker handles the database, the API, and the data collector automatically.

Open your browser: **http://localhost:8000/docs**

To stop: press `Ctrl + C`
To run in the background: `docker compose up -d`
To see logs: `docker compose logs -f`

---

### Option B · Installer script (no Docker)

> Requires: [Python 3.11+](https://python.org) and [PostgreSQL](https://postgresql.org)

```bash
# 1. Download the project
git clone <repo-url>
cd trend-scraper

# 2. Run the installer
chmod +x install.sh
./install.sh
```

The script sets everything up and tells you exactly what to do next.

---

## 🔑 Optional: add Reddit credentials

The app works without credentials, but adding them gives you higher
rate limits and more reliable data.

1. Go to **reddit.com/prefs/apps** and create a free "script" app
2. Open the `.env` file and fill in:

```env
REDDIT_CLIENT_ID=your_id_here
REDDIT_CLIENT_SECRET=your_secret_here
```

---

## 🌐 What the API gives you

Once running, open **http://localhost:8000/docs** to explore everything interactively.

| URL | What it returns |
|-----|----------------|
| `http://localhost:8000/trends` | All collected trends |
| `http://localhost:8000/trends/top` | The hottest trends right now |
| `http://localhost:8000/trends?source=reddit` | Reddit trends only |
| `http://localhost:8000/trends?source=google` | Google trends only |
| `http://localhost:8000/health` | Is the system running? |

Data updates every 15 minutes automatically.

---

## 🗂 How it works (plain English)

```
┌──────────────────────────────────────────────────────┐
│  Every 15 minutes the collector runs:                │
│                                                      │
│  Reddit + Google  →  clean it  →  score it  →  save │
│                                                      │
│  The API reads from the database and shows results.  │
└──────────────────────────────────────────────────────┘
```

1. **Collector** — fetches top Reddit posts and Google trending searches
2. **Cleaner** — strips links, emoji, and noise from titles
3. **Scorer** — ranks topics by how fast they're gaining mentions
4. **API** — lets you query the results from any browser or app

---

## 🛠 Project layout (for developers)

```
trend-scraper/
├── ingestion/       # Fetches data from Reddit, Google, etc.
├── processing/      # Cleans and normalises raw data
├── scoring/         # Calculates trend scores
├── storage/         # Saves everything to PostgreSQL
├── api/             # The web API (FastAPI)
├── workers/         # Background scheduler
├── config/          # Settings / environment variables
├── tests/           # Automated test suite (94 tests)
├── Dockerfile
├── docker-compose.yml
└── install.sh
```

### Run the tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

No database needed — tests use an in-memory SQLite database.

### Add a new data source

1. Create `ingestion/my_source.py`, subclass `BaseIngester`, implement `fetch / parse / normalize`
2. Register it in `workers/scheduler.py` → `_build_ingesters()`
3. Done — no other files need to change

### Swap the scoring algorithm

Implement the `ScoringStrategy` protocol and pass it to `score_items()`.
The default uses velocity + time-decay. You can swap in an ML model without touching anything else.

---

## ⚙️ Configuration

All settings live in `.env`. Defaults work out of the box.

| Setting | Default | What it does |
|---------|---------|-------------|
| `DATABASE_URL` | (postgres local) | Where data is stored |
| `REDDIT_CLIENT_ID` | (empty) | Reddit API credentials |
| `REDDIT_SUBREDDIT` | `all` | Which subreddit to watch |
| `GOOGLE_TRENDS_GEO` | `US` | Country for Google Trends |
| `SCHEDULER_INTERVAL_SECONDS` | `900` | How often data is collected |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

---

## 📈 Scaling path

| Now | Next step |
|-----|-----------|
| Single process | `uvicorn --workers 4` |
| Sleep-loop scheduler | Celery + Redis |
| One database | Read replicas + PgBouncer |
| No cache | Redis cache on `/trends/top` |
| Local deploy | Docker → Kubernetes |

---

## 💡 Ideas for what to build with this

- **Trend alerts** — get a Slack/email ping when a topic spikes
- **Dashboard** — visualise score history as a chart
- **Newsletter** — auto-generate a "this week's top trends" digest
- **Niche tracker** — point it at specific subreddits (crypto, sports, tech)
- **Public API** — expose it with rate limiting and charge for access
