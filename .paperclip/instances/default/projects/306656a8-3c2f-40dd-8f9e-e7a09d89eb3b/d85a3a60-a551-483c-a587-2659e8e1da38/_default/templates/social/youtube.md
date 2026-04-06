# YouTube — Post Template (Shorts / News Clips)

**Title limit:** 100 chars
**Description limit:** 5000 chars (first 200 chars show in search results)
**Video:** Must be uploaded manually — this script generates metadata only
**Format:** Shorts (< 60s vertical) for breaking news; standard (1–5 min) for explainers

---

## Template — YouTube Shorts (Breaking News)

**Title:**
```
{Headline — max 100 chars, no clickbait, accurate}
```

**Description:**
```
{Summary — 2–4 sentences explaining the story}

Fonte: {Source}
Leggi di più: {article_url}

---
Orbita — Notizie di Spazio & Aeronautica
Iscriviti alla newsletter: [link in bio]

Tags: space, spazio, aerospace, nasa, esa, spacex, astronomia, aeronautica,
      notizie spazio, scienza, tecnologia spaziale, orbita
```

---

## Example

**Title:**
```
SpaceX: Starship completa il primo volo orbitale completo con successo
```

**Description:**
```
Starship, il razzo più grande mai costruito, ha completato il suo primo volo 
orbitale senza perdita del veicolo. La capsula è ammarata nell'Oceano Indiano 
dopo circa 65 minuti di volo. Un passo fondamentale verso la colonizzazione di Marte.

Fonte: SpaceFlightNow
Leggi di più: https://spaceflightnow.example/starship-orbital

---
Orbita — Notizie di Spazio & Aeronautica
Iscriviti alla newsletter: [link in bio]
```

**Tags:** `space, spazio, starship, spacex, volo orbitale, razzo, marte, nasa, orbita, notizie spazio`

---

## Template — Standard Video (Explainer)

**Title:**
```
{Topic}: {Key insight or question} | Orbita
```

**Description:**
```
In questo video esploriamo {topic}.

{Paragraph 1: what happened / what is this about}

{Paragraph 2: why it matters / scientific or industry context}

{Paragraph 3: what's next / future implications}

Fonti:
- {Source 1}: {url_1}
- {Source 2}: {url_2}

---
Orbita — Notizie di Spazio & Aeronautica
🔔 Iscriviti per non perdere le ultime notizie: [subscribe link]
📧 Newsletter: [link in bio]

Capitoli:
0:00 Introduzione
0:30 {Section 1}
1:15 {Section 2}
2:00 {Section 3}
```

---

## Rules

- **Title**: factual, no ALL CAPS, no "SHOCKING" or "YOU WON'T BELIEVE" — space news sells itself
- **Description**: first 200 chars appear in search — put the most important info there
- **Tags**: set in `config/social_platforms.json` under `default_tags`; add article-specific keywords
- **Category**: 28 (Science & Technology) — already set in config
- **Privacy**: `public` by default
- Video upload is **manual** — YouTube Data API OAuth flow requires interactive auth that is not yet automated
- Shorts format: vertical 9:16, max 60s, add automatic captions via YouTube Studio after upload
- Best upload times: 14:00 or 18:00 (Europe/Rome)
