# Speechify TTS API Integration (Python)

Last updated: 2025-11-09.

> Practical, copy‑pasteable reference for converting text to speech with Speechify in Python (including streaming, SSML/emotion, voice management, limits, and error handling).

---

## Quick Links (Official)

- **Overview & Quickstart** – Speechify API docs. citeturn1view0turn18view0
- **API Reference – Audio (speech & stream)**. citeturn5view0turn6view0
- **API Reference – Voices (list, create, sample download)**. citeturn21view0turn19search0turn19search1
- **Models, Language Support, Streaming, SSML, Emotion, Speech Marks**. citeturn12view0turn19search3turn10view0turn15view0turn16view0turn17view0
- **API Limits**. citeturn9view0
- **Official Python SDK (pip)** – GitHub repo & usage. citeturn14view0
- **Pricing (public site)** – Free tier & $10 per 1M characters (confirm in console for current pricing). citeturn0search14turn0search4

---

## What you can build

- **Non‑streaming TTS**: Convert text/SSML to audio (`wav`, `mp3`, `ogg`, `aac`, `pcm`). citeturn5view0
- **Streaming TTS**: Low‑latency, chunked HTTP audio for longer text (up to 20k chars). citeturn6view0turn10view0
- **Voices**: Use system voices or your **personal cloned voices**; list & select by `id`. citeturn21view0
- **Controls**: SSML (rate/pitch/volume), **emotion** via `<speechify:style emotion="...">`, **speech marks** (word timings). citeturn15view0turn16view0turn17view0

---

## Core Endpoints

- **Synthesize (non‑streaming)**: `POST` <https://api.sws.speechify.com/v1/audio/speech>

  Returns Base64 `audio_data`, `audio_format`, `speech_marks`. Pass `voice_id`, optional `audio_format`, `language`, `model`. citeturn5view0

- **Synthesize (streaming)**: `POST` <https://api.sws.speechify.com/v1/audio/stream>

  Set header `accept: audio/mpeg|audio/ogg|audio/aac`. Response is audio bytes via HTTP chunked transfer. citeturn6view0

- **List voices**: `GET` <https://api.sws.speechify.com/v1/voices> → returns system & personal voices; each has `id`, `display_name`, `type` (`shared|personal`). citeturn21view0turn13search3
- **Create personal (cloned) voice**: `POST /v1/voices` (multipart with `sample` and `consent`). citeturn19search0
- **Download personal voice sample**: `GET /v1/voices/:id/sample`. citeturn19search1

**Auth:** All calls use `Authorization: Bearer <API_KEY or ACCESS_TOKEN>`. Manage API keys in the console. citeturn3view0turn18view0

---

## Models & Languages

- **Models:** `simba-english` (default) and `simba-multilingual` (experimental). Older `simba-base` & `simba-turbo` are deprecated; prefer `simba-english` or `simba-multilingual`. citeturn12view0turn5view0turn6view0
- **Languages:** Provide `language` (e.g., `en-US`, `fr-FR`) if the input is a single known language; otherwise omit and Speechify will detect. citeturn19search3

---

## Limits & Pricing

- **Character limits:** `speech` up to **2,000** chars; `stream` up to **20,000** chars (SSML counts). citeturn9view0
- **Rate limits:** ~**200 rpm**, **10 rps** (account‑level). citeturn9view0
- **Pricing (marketing pages):** Free tier & **$10 / 1M characters** pay‑as‑you‑go; verify in console for your plan. citeturn0search14turn0search4

---

## Setup (Python)

```bash
# 1) install the official sdk
pip install speechify-api

# (optional) for streaming via requests
pip install requests

# 2) set your api key (mac/linux)
export SPEECHIFY_API_KEY="your_api_key"

#    (windows powershell)
setx SPEECHIFY_API_KEY "your_api_key"
```

SDK & install guidance: citeturn14view0

---

## Quickstart: Non‑Streaming TTS (save to file)

```python
import os
import base64
from speechify import Speechify
from speechify.core.api_error import ApiError

# Authenticate (SDK can also read SPEECHIFY_API_KEY env var)
client = Speechify(token=os.environ.get("SPEECHIFY_API_KEY"))

def tts_to_file(text: str, voice_id: str, out_path: str, audio_format: str = "mp3"):
    """Convert text/SSML to speech and save to a file."""
    try:
        print("Requesting synthesis...")
        resp = client.tts.audio.speech(
            input=text,
            voice_id=voice_id,
            audio_format=audio_format,   # mp3|wav|ogg|aac|pcm
            # language="en-US",        # optional; set if single known language
            # model="simba-english",   # optional; see docs for options
        )
        print("Decoding audio...")
        audio_bytes = base64.b64decode(resp["audio_data"])  # Base64 → bytes
        with open(out_path, "wb") as f:
            f.write(audio_bytes)
        print(f"saved: {out_path}")
        return out_path
    except ApiError as e:
        # The SDK raises ApiError for non-2xx; print details for debugging
        print(f"api error: status={e.status_code}; body={e.body}")
        raise
    except Exception as e:
        print(f"unexpected error: {e}")
        raise

if __name__ == "__main__":
    # 1) pick a voice id (see list-voices snippet below)
    VOICE_ID = "george"  # example system voice id; replace with your choice
    # 2) plain text example (you can also pass SSML)
    tts_to_file("hello from speechify!", VOICE_ID, "hello.mp3")
```

Endpoint & response fields (Base64 `audio_data`, formats) from API reference. citeturn5view0
SDK usage & ApiError handling from official repo. citeturn14view0

---

## Streaming TTS (low‑latency HTTP chunks)

Use the streaming endpoint when you want playback to start immediately or for longer inputs.
Key differences: audio bytes only (no metadata), `accept` header must be an audio mime. citeturn6view0turn10view0

```python
import os
import requests

API_KEY = os.environ.get("SPEECHIFY_API_KEY")
URL = "https://api.sws.speechify.com/v1/audio/stream"

def stream_to_mp3(text: str, voice_id: str, out_path: str = "stream.mp3"):
    """Streams MP3 bytes and writes them incrementally to disk."""
    headers = {
        "authorization": f"Bearer {API_KEY}",
        "accept": "audio/mpeg",
        "content-type": "application/json",
    }
    payload = {"input": text, "voice_id": voice_id}
    print("starting stream...")
    with requests.post(URL, json=payload, headers=headers, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
    print(f"saved: {out_path}")
    return out_path

if __name__ == "__main__":
    stream_to_mp3("this starts playing as it downloads.", "george")
```

Streaming endpoint & required headers. citeturn6view0

> **Note**: Real‑time playback while downloading requires decoding MP3 frames to PCM; for production, use a player/decoder that supports streaming MP3, or stream `audio/aac`/`audio/ogg` depending on your stack. Specs & limits are in the streaming docs. citeturn10view0

---

## Voice Management

### List available voices (system + personal)

```python
from speechify import Speechify

client = Speechify(token=os.environ.get("SPEECHIFY_API_KEY"))
voices = client.tts.voices.list()
for v in voices:
    print(v["id"], ":", v.get("display_name"), "/", v.get("type"))  # "shared" or "personal"
```

Returns voice objects with `id`, `display_name`, `type`, `preview_audio`, `tags`, and supported models/languages. citeturn21view0

### Create a personal (cloned) voice (server‑side only)

> Requires user consent payload and an audio sample; see docs for fields and compliance. citeturn19search0

### Download a sample of a personal voice

> `GET /v1/voices/:id/sample` to fetch an example clip for QA. citeturn19search1
>
> Changelog: delete personal voice via `DELETE /v1/voices/{id}`. citeturn19search4

---

## SSML & Emotion Examples

You can pass **plain text** _or_ **SSML** in the `input` parameter. Emotion is controlled via the `speechify:style` SSML tag. citeturn15view0turn16view0

```python
ssml = """
<speak>
  hello there.
  <prosody rate="slow" pitch="high">this part is slower and higher.</prosody>
  <speechify:style emotion="cheerful">and this feels cheerful!</speechify:style>
  <break time="500ms"/>
</speak>
"""

resp = client.tts.audio.speech(
    input=ssml,
    voice_id="george",
    audio_format="mp3",
)
```

Supported tags & parameters documented here. citeturn15view0

---

## Speech Marks (word timing)

Every non‑streaming synthesis returns `speech_marks` (word/phrase timings). Useful for karaoke‑style highlighting, analytics, or precise seeking. citeturn5view0turn17view0

```python
data = client.tts.audio.speech(input="hello world", voice_id="george")
marks = data.get("speech_marks", {})
for sentence in marks.get("chunks", []):
    for word in sentence.get("chunks", []):
        print(word["value"], word["start_time"], word["end_time"])  # ms
```

---

## Best Practices

- **Set `audio_format` explicitly** to avoid future default changes. citeturn5view0
- **Provide `language`** when your input is a single known language; omit for mixed texts. citeturn19search3
- **Chunk long inputs**: `speech` ≤ 2,000 chars; `stream` ≤ 20,000 chars (SSML counts). Split at sentence boundaries. citeturn9view0
- **Cache results** keyed by `(voice_id, hash(input), audio_format, model)` to avoid repeat charges.
- **Handle rate limits** (429) with exponential backoff; the SDK already retries certain transient errors; you can tune `max_retries` and timeouts. citeturn14view0
- **Secure your key**: Keep API keys server‑side; never ship them in front‑end code. citeturn3view0
- **Compliance**: For **voice cloning**, collect consent and keep records; pass `consent` JSON when creating a personal voice. citeturn19search0

---

## Troubleshooting

- **401 Unauthorized** → Missing/invalid `Authorization` header or expired token. citeturn3view0
- **400/413** → Over character limits or bad SSML (escape special XML chars). citeturn9view0turn15view0
- **429 Too Many Requests** → Respect RPM/RPS limits; add retries/backoff. citeturn9view0turn14view0
- **Streaming stops early** → On synthesis error the connection may close without a JSON body (HTTP chunking limitation). citeturn10view0

---

## HTTP (cURL) Examples

```bash
# non-streaming: synthesize to mp3 (Base64 in JSON)
curl -X POST https://api.sws.speechify.com/v1/audio/speech   -H "authorization: Bearer $SPEECHIFY_API_KEY"   -H "content-type: application/json"   -d '{
        "input":"Hello world",
        "voice_id":"george",
        "audio_format":"mp3"
      }'

# streaming: write mp3 bytes to file
curl -X POST https://api.sws.speechify.com/v1/audio/stream   -H "authorization: Bearer $SPEECHIFY_API_KEY"   -H "content-type: application/json"   -H "accept: audio/mpeg"   -d '{"input":"Hello streaming", "voice_id":"george"}'   --output stream.mp3

# list voices
curl -X GET https://api.sws.speechify.com/v1/voices   -H "authorization: Bearer $SPEECHIFY_API_KEY"
```

---

## Appendix: Selecting a `voice_id`

- Use `GET /v1/voices` and pick by `display_name`/`tags`. System voices are `type: "shared"`; your clones are `type: "personal"`. citeturn21view0

## Appendix: Plans & Pricing

- Marketing pages advertise **Free** (starter) and **Pay‑As‑You‑Go** starting at **$10 / 1M characters**. Always confirm current pricing/quotas inside your **Speechify Console**. citeturn0search14turn0search4

---

## References

- Docs Overview & Quickstart. citeturn1view0turn18view0
- API Reference – Audio (Speech & Stream). citeturn5view0turn6view0
- API Reference – Voices (List/Create/Sample). citeturn21view0turn19search0turn19search1
- Models & Language Support. citeturn12view0turn19search3
- Streaming feature. citeturn10view0
- SSML & Emotion Control. citeturn15view0turn16view0
- Speech Marks. citeturn17view0
- Python SDK README. citeturn14view0
