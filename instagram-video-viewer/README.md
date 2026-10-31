# Instagram Video Viewer

A Django app for searching accessible Instagram profile posts and browsing recent video posts and Reels in a responsive gallery. Profile collections and video metadata are stored in the configured database (PostgreSQL when `DATABASE_URL` is set, SQLite otherwise). Media files are not stored by the app.

## Requirements

- Python 3.10 or later
- A network connection for Instagram requests and remote thumbnails
- PostgreSQL is optional; SQLite is the default when `DATABASE_URL` is not set
- `gallery-dl` (included in `requirements.txt`) for the alternate page

## Setup

From this directory:

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # Windows: copy .env.example .env
python manage.py migrate
python manage.py runserver
```

Open http://127.0.0.1:8000. Locally, start the refresh worker in a second terminal:

```bash
source .venv/bin/activate
python manage.py run_collection_worker --workers 2
```

Search requests return quickly and create queued refresh jobs. The worker fetches profile metadata in a bounded thread pool; the collection page polls the job UUID until it succeeds or fails. Keep the worker running to process refreshes. Increase concurrency cautiously because Instagram can rate-limit requests.

After changing models, run `python manage.py makemigrations` and `python manage.py migrate`.

### PostgreSQL (optional)

PostgreSQL 15 is installed and configured for this local project. A local `instaview` database and role were created, and its connection string is stored only in the ignored `.env` file. The app uses it when `DATABASE_URL` is present. The project uses `db.sqlite3` automatically when that variable is unset or blank. On another machine, install PostgreSQL and set a connection string such as:

```dotenv
DATABASE_URL=postgresql://instaview:your-password@127.0.0.1:5432/instaview
```

The Python PostgreSQL driver and URL parser are in `requirements.txt`. `python manage.py migrate` applies the schema to whichever database is configured. The migration attaches preexisting video records to their profile collection.

## Configuration

Set values in `.env` (never commit real credentials):

```dotenv
DJANGO_SECRET_KEY=replace-with-a-long-random-value
DJANGO_DEBUG=true
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=                         # omit or leave blank to use SQLite
# Optional session belonging to an account authorized to see the requested profile:
INSTAGRAM_SESSION_USERNAME=
INSTALOADER_SESSIONFILE=
GALLERY_DL_INSTAGRAM_COOKIES=
YOUTUBE_CLIENT_ID=
YOUTUBE_CLIENT_SECRET=
YOUTUBE_REDIRECT_URI=http://127.0.0.1:8000/youtube/callback/
```

Without an optional session, requests are anonymous and can only return content Instagram makes accessible. If you configure a session file, create it yourself using Instaloader with your own account and keep it private. The app does not collect passwords or log in automatically. Use `DJANGO_DEBUG=false` and a proper secret key/host list outside local development.

The `/gallery-dl/` page uses gallery-dl 1.32.18, accepts a profile name or Instagram profile/Reel URL, and inspects up to 24 recent posts. If Instagram requires a session, `GALLERY_DL_INSTAGRAM_COOKIES` may point to a cookie file from an account authorized to access the profile. Keep that file private. The package remains subject to Instagram changes and access controls.

### YouTube publishing setup

1. In Google Cloud Console, create an OAuth client for a web application and enable the YouTube Data API v3.
2. Add `http://127.0.0.1:8000/youtube/callback/` as an authorized redirect URI (or set the matching `YOUTUBE_REDIRECT_URI` in `.env`).
3. Put the OAuth client ID and secret in `.env`, then restart Django.
4. Click **Connect YouTube**, authorize the YouTube channel, then use **Publish to YouTube** on a video card.

The app requests only the `youtube.upload` scope. Uploads require a separate ownership/permission confirmation and an explicit submit. Visibility defaults to **Published (Public)**; Private and Unlisted remain available. YouTube automatically classifies eligible square or vertical videos up to three minutes as Shorts; there is no separate Short/Standard selector in this app. The app temporarily streams the selected video through a temporary file (up to 512 MB), uploads it through YouTube's resumable upload API, then deletes the temporary file. It never uploads automatically after connecting. Google's OAuth consent and app-verification requirements may apply, especially outside local testing. See Google's [Shorts guidance](https://support.google.com/youtube/answer/15424877) and [video upload guide](https://developers.google.com/youtube/data/guides/uploading_a_video).

The development callback permits HTTP only when both the configured URI and incoming callback use a local loopback host and `DJANGO_DEBUG=true`. Deployed callbacks must use HTTPS.

## What it does

- Accepts an Instagram username or a Reel/post URL. A link opens the selected accessible Reel in an inline player, then shows videos from that profile below it.
- Includes a separate `/gallery-dl/` page powered by gallery-dl as a second extraction path. It reads metadata and remote media URLs without saving video files.
- Fetches up to 24 recent profile videos, inspecting at most 60 profile posts per request. Successful searches are cached for 20 minutes to speed up repeat searches. This is a bounded recent set, not a guarantee of every video ever posted.
- Shows cached metadata in pages of 12, with thumbnails and links that open the original Instagram post.
- Saves profile collections and each video's metadata in the database. Use **Collections** to revisit a profile, browse its stored videos, or queue a refresh.
- Refreshes run in a database-backed queue processed by `run_collection_worker` using a bounded thread pool. Job UUIDs can be polled until completion; request handlers never wait for Instagram extraction.
- Records each search, job status, and result count. Existing video metadata remains available between refreshes.
- Exposes a Django REST Framework API under `/api/v1/` for collections, their videos, refresh jobs, and job status polling. Anonymous requests are throttled.
- Handles private/inaccessible profiles, login requirements, missing profiles, rate limits, connection errors, and other Instaloader failures with user-facing messages.

## Access and download limits

Instaloader is an unofficial client that depends on Instagram's interfaces and access rules. Instagram may change those interfaces, require login, restrict a profile, return incomplete results, or rate-limit requests. A public profile is not a guarantee that every post or video is retrievable. This app inspects a bounded number of recent posts and does not bypass private-account restrictions, bot protections, or rate limits.

Video download links are revealed only after the user confirms they own or are authorized to download the media and downloading is permitted. These links point to Instagram's returned media URL; Instagram may not provide one, and the URL may expire or fail. The confirmation is an honor statement, not a way for the app to verify rights. The app does not proxy or store downloaded media.

## Data and privacy

Searches and video metadata are stored in the configured database. Thumbnail images are loaded directly from Instagram's CDN by the browser; availability and URLs may expire. Search history is shared by users of this local installation because this MVP has no account system.

## REST API

- `GET /api/v1/collections/` — list collections.
- `POST /api/v1/collections/` — queue a lookup. JSON body: `{"username":"instagram"}` or `{"url":"https://www.instagram.com/reel/.../"}`. Returns HTTP 202 with collection and job IDs.
- `GET /api/v1/collections/{uuid}/` — collection metadata.
- `GET /api/v1/collections/{uuid}/videos/` — paginated saved video metadata.
- `POST /api/v1/collections/{uuid}/refresh/` — queue a refresh (HTTP 202).
- `GET /api/v1/jobs/{uuid}/` — poll `queued`, `running`, `succeeded`, or `failed` status.

The API and web app use the same database queue. Locally, run `python manage.py run_collection_worker`. On Vercel, the job status endpoint claims and processes a queued job inside a serverless function when the browser polls it, so no terminal worker is needed. Vercel functions have a maximum execution time; unusually slow Instagram requests can time out, after which the UI reports a retryable failure. Set `DATABASE_URL` in Vercel to the same persistent PostgreSQL database used by the web app; do not rely on SQLite across serverless instances.
