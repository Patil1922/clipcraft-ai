# ClipCraft AI — MVP

A local-first prototype that accepts uploaded videos or YouTube URLs, transcribes speech with Faster-Whisper, ranks candidate moments using a transparent heuristic, and renders 9:16 MP4 clips with FFmpeg.

## What works now
- Upload MP4/MOV/MKV/WEBM/AVI files.
- Submit a YouTube URL (yt-dlp; use only where downloading is permitted).
- Speech transcription (Faster-Whisper).
- Candidate clip windows ranked by speech density and hook-word frequency.
- Vertical 1080×1920 MP4 rendering and download.
- Progress/status dashboard.

## Important limitations
- The score is a heuristic, not a trained virality prediction.
- Crop is centered; face tracking is not implemented.
- The UI offers Hindi + English caption mode, but this MVP does not yet translate or burn bilingual subtitles. It currently transcribes speech for moment detection.
- Jobs and metadata are held in memory; restarting the server clears job history.
- No login, cloud storage, queue, or production security yet. Do not expose this server publicly as-is.

## Requirements
- Python 3.10+
- FFmpeg and ffprobe installed and available on PATH
- For YouTube URLs, yt-dlp may require updates and access allowed by YouTube.
- A machine with enough CPU/RAM/disk for video processing.

## Run on Windows
1. Install FFmpeg and add its `bin` folder to PATH.
2. Install Python 3.10+.
3. Open this project folder in Terminal:
   ```powershell
   py -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   uvicorn app:app --host 127.0.0.1 --port 8000
   ```
4. Open http://127.0.0.1:8000

## Run on Ubuntu VPS
```bash
sudo apt update
sudo apt install -y ffmpeg python3-venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```
For remote access, put it behind HTTPS and authentication before allowing public use.

## Next development milestones
1. Bilingual subtitle generation (original-language transcript + English/Hindi translation).
2. Word-level animated captions and subtitle style presets.
3. Face-aware vertical reframing.
4. Persistent database, job queue, user accounts and cloud storage.
5. Better highlight ranking with configurable clip lengths and human review.


## Public VPS deployment (HTTPS + login)
1. Point a domain/subdomain DNS A record to your VPS public IPv4 address.
2. Install Docker Engine and the Docker Compose plugin on Ubuntu.
3. Copy this project folder to the VPS.
4. Run `cp .env.example .env` and edit `.env`: set DOMAIN and a strong CLIPCRAFT_PASSWORD.
5. Allow inbound TCP ports 80 and 443 in the VPS firewall/cloud security group.
6. Run `docker compose up -d --build`.
7. Open `https://YOUR_DOMAIN` on your phone and sign in with the configured username/password.

Caddy obtains and renews HTTPS certificates automatically once DNS points to the VPS and ports 80/443 are reachable.
Keep `.env` private. This remains an MVP: add per-user quotas, persistent job storage, upload limits, cleanup policies and a proper job queue before accepting public users.
