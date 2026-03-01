# Paper Trail

Narrative provenance tracker: one click on a Bluesky post traces how that narrative originated and mutated across Reddit and Bluesky, with a ready-to-post reply and full paper trail.

## Exact commands to run the backend

From the project root (directory containing `main.py`, `schemas.py`, `config.py`):

```bash
# 1. Create and activate virtualenv (Python 3.10+)
python -m venv .venv
.venv\Scripts\activate
# On macOS/Linux:  source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy env and set your keys
copy .env.example .env
# Edit .env: set REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, OPENAI_API_KEY

# 4. Run the server (from project root so imports resolve)
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Backend runs at **http://127.0.0.1:8000**. Check: **http://127.0.0.1:8000/health** (should return `{"status":"ok"}`).

## Exact steps to load the Chrome extension

1. Open Chrome and go to **chrome://extensions/**.
2. Enable **Developer mode** (toggle top-right).
3. Click **Load unpacked**.
4. Select the **`extension`** folder inside this repo (the folder that contains `manifest.json` and `content.js`).
5. Leave the backend running on **http://127.0.0.1:8000**; the extension sends Trace requests there.

## Usage

1. Open [bsky.app](https://bsky.app) and log in.
2. Find a post you want to trace.
3. Click the **Trace** button in the post’s action bar (injected by the extension).
4. Wait for the inline panel below the post: origin card, mutation timeline, narrative diff, and **Copy reply**.

## Requirements

- Python 3.10+
- Reddit app (script type, read-only) at [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps)
- OpenAI API key
- Chrome (for the extension)
