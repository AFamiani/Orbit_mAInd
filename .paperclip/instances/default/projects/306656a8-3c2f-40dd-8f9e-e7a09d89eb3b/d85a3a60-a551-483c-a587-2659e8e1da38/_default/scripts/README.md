# Orbita — Scripts

This directory contains the automation scripts for the Orbita social media pipeline.

| Script | Purpose |
|---|---|
| `news_aggregator.py` | Fetches and ranks space/aerospace news from configured RSS sources, outputs a ranked digest JSON |
| `social_poster.py` | Reads a digest JSON and cross-posts formatted content to X, LinkedIn, Instagram, TikTok, and YouTube |

---

## social_poster.py — Environment Variables

All credentials are read from environment variables. **Never commit credentials to the repository.**

Set them in your shell profile, a `.env` file (loaded with `python-dotenv`), or your CI/CD secrets manager.

### X / Twitter

| Variable | Description | Where to get it |
|---|---|---|
| `TWITTER_API_KEY` | OAuth 1.0a Consumer Key | [developer.twitter.com](https://developer.twitter.com) → Project → App → Keys and Tokens |
| `TWITTER_API_SECRET` | OAuth 1.0a Consumer Secret | Same page as above |
| `TWITTER_ACCESS_TOKEN` | OAuth 1.0a Access Token (for the posting account) | Same page → "Access Token and Secret" |
| `TWITTER_ACCESS_TOKEN_SECRET` | OAuth 1.0a Access Token Secret | Same page |
| `TWITTER_BEARER_TOKEN` | App-only Bearer Token (for read operations) | Same page → "Bearer Token" |

**Required permissions:** Read + Write (not Read-only). The app must be attached to a project with the "Free" or "Basic" tier at minimum to post tweets via API v2.

---

### LinkedIn

| Variable | Description | Where to get it |
|---|---|---|
| `LINKEDIN_ACCESS_TOKEN` | OAuth 2.0 Access Token for your Organization | [linkedin.com/developers](https://www.linkedin.com/developers) → Create App → Auth tab → OAuth 2.0 Tools |
| `LINKEDIN_ORGANIZATION_ID` | Numeric ID of your LinkedIn Company Page | Your company page URL: `linkedin.com/company/{id}` — or via `GET /v2/organizationalEntityAcls` |

**Required OAuth scopes:** `w_member_social`, `w_organization_social`, `r_organization_social`

**Notes:**
- Access tokens expire after 60 days — set up a refresh token flow or rotate manually
- The organization must have the "Marketing Developer Platform" product enabled on your app
- Find your Organization ID: visit your company page, click "Admin tools" → "Share an update", the URL will contain `?organizationId=XXXXXXX`

---

### Instagram (Meta Graph API)

| Variable | Description | Where to get it |
|---|---|---|
| `INSTAGRAM_ACCESS_TOKEN` | Long-lived Page Access Token with Instagram permissions | [developers.facebook.com](https://developers.facebook.com) → App → Explore Products → Instagram Graph API |
| `INSTAGRAM_ACCOUNT_ID` | Instagram Business Account ID (not the username) | `GET /me/accounts` then `GET /{page-id}?fields=instagram_business_account` |

**Required permissions:** `instagram_basic`, `instagram_content_publish`, `pages_read_engagement`

**How to obtain a long-lived token:**
1. Create a Meta App at [developers.facebook.com](https://developers.facebook.com)
2. Add "Instagram Graph API" product
3. Use Graph API Explorer to generate a User Token with the required permissions
4. Exchange it for a long-lived token: `GET /oauth/access_token?grant_type=fb_exchange_token&...`
5. Long-lived tokens last ~60 days; store them securely and rotate before expiry

**Notes:**
- Instagram account must be a **Business or Creator** account linked to a Facebook Page
- Posting requires an image URL that is publicly accessible (HTTP 200, not behind auth)
- The script uses NASA APOD image automatically when available if no `--image-url` is passed

---

### TikTok

| Variable | Description | Where to get it |
|---|---|---|
| `TIKTOK_ACCESS_TOKEN` | OAuth 2.0 Access Token | [developers.tiktok.com](https://developers.tiktok.com) → App → Content Posting API |
| `TIKTOK_OPEN_ID` | The unique ID of the TikTok user account | Returned in the OAuth callback as `open_id` |

**Required scopes:** `video.publish`, `video.upload`

**How to obtain credentials:**
1. Register a TikTok Developer account at [developers.tiktok.com](https://developers.tiktok.com)
2. Create an app and apply for the **Content Posting API** (requires app review)
3. Implement the OAuth 2.0 PKCE flow to get user authorization
4. Exchange the auth code for `access_token` and `open_id`
5. Access tokens expire after 24 hours — implement token refresh with `refresh_token`

**Notes:**
- Content Posting API requires TikTok app review approval — allow 1–2 weeks
- Videos must be uploaded as a URL accessible by TikTok servers (`PULL_FROM_URL` mode)
- Captions are limited to 150 chars for the `title` field in the API payload (despite 2200 display chars)

---

### YouTube (Google Data API v3)

| Variable | Description | Where to get it |
|---|---|---|
| `YOUTUBE_CLIENT_SECRETS_FILE` | Path to the OAuth 2.0 client secrets JSON file | [console.cloud.google.com](https://console.cloud.google.com) → APIs & Services → Credentials → Create OAuth Client ID |
| `YOUTUBE_CHANNEL_ID` | YouTube Channel ID | YouTube Studio → Settings → Channel → Advanced → Channel ID |

**How to obtain credentials:**
1. Go to [console.cloud.google.com](https://console.cloud.google.com) and create a project
2. Enable the **YouTube Data API v3**
3. Create an **OAuth 2.0 Client ID** (type: Desktop app or Web app)
4. Download the JSON file and set `YOUTUBE_CLIENT_SECRETS_FILE` to its path
5. On first run, a browser will open for OAuth consent — the token is cached locally after that

**Required scopes:** `https://www.googleapis.com/auth/youtube.upload`

**Notes:**
- YouTube video upload is **not yet automated** in `social_poster.py` — the script outputs metadata only
- Video uploads via API require `google-api-python-client` and `google-auth-oauthlib`
- `pip install google-api-python-client google-auth-oauthlib`
- The free YouTube Data API quota is 10,000 units/day; a video upload costs 1,600 units

---

## news_aggregator.py — Environment Variables

| Variable | Description |
|---|---|
| `NASA_API_KEY` | NASA Open APIs key — get free at [api.nasa.gov](https://api.nasa.gov) (used for APOD and other data) |

---

## Quick Start

```bash
# 1. Install dependencies
pip install requests python-dateutil tweepy

# 2. Set credentials (example using .env pattern)
export TWITTER_API_KEY="your_key_here"
export TWITTER_API_SECRET="your_secret_here"
# ... set remaining vars ...

# 3. Run news aggregator to produce a digest
python scripts/news_aggregator.py --output json > digest.json

# 4. Dry-run social posting (no live posts)
python scripts/social_poster.py --digest digest.json --dry-run

# 5. Post to specific platforms
python scripts/social_poster.py --digest digest.json --platforms twitter linkedin

# 6. Post to all enabled platforms
python scripts/social_poster.py --digest digest.json

# 7. Check analytics
python scripts/social_poster.py --fetch-analytics --analytics-days 7
```

## Enabling Platforms

Platforms are disabled by default in `config/social_platforms.json`. To enable one:

```json
"twitter": {
  "enabled": true,
  ...
}
```

Set `enabled: true` only after the corresponding credentials are in place and tested with `--dry-run`.
