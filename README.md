# en_ch-subtitle-translation-automation
Python-based AI automation tool for translating English subtitles into Chinese using ChatGPT and DeepSeek APIs.

# Subtitle Translation Toolkit

Overview
--------
This project was developed collaboratively by volunteers at Saddleback Church to automate English-to-Chinese subtitle translation workflows.
This project is a toolkit for processing sermon video subtitles. It includes scripts to extract English subtitles from video/audio, merge and split segments, perform multi-stage Chinese translation (literal + adaptive), adjust formatting for readability, and upload/download subtitles to/from YouTube. The workflow is split into steps `Step1` through `Step10` so you can run or debug each stage independently.
My contributions included:
- Modifying Python scripts for subtitle translation automation
- Running the translation pipeline and successfully publishing translated subtitles to YouTube
- Improving translation consistency and quality
- Testing and reviewing subtitle outputs

Features
--------
- Extract and transcribe audio to English subtitles (Whisper / OpenAI)
- Merge and fix timestamps for subtitle segments
- Split merged subtitles into multiple Parts for batch processing
- Multi-stage Chinese translation (literal and meaning/adaptive versions)
- Automatic line-breaking and splitting for long Chinese subtitles
- Upload and download subtitles to/from YouTube using OAuth
- Logging, caching and concurrent processing to speed up large jobs

Requirements
------------
- Python 3.10+
- ffmpeg installed locally (used by pydub for audio conversion)
- Typical Python packages (install via pip):
  - openai (or the DeepSeek SDK if you use DeepSeek)
  - pydub
  - yt-dlp
  - google-auth, google-auth-oauthlib, google-api-python-client
  - other imports as used in the individual scripts

Security and Credentials
------------------------
- Do NOT commit real API keys or OAuth tokens to the repository. This project has had hardcoded keys replaced with placeholders (`xxxx`).
- Google OAuth client secret and token paths are configurable through environment variables:
  - `GOOGLE_CLIENT_SECRET_FILE` — path to your `client_secret.json` (required for interactive OAuth)
  - `GOOGLE_OAUTH_TOKEN_FILE` — path to save the OAuth token (default: `token.json`)
- A `.gitignore` file is included to ignore `token.json`, `client_secret*.json`, `.env`, and media output files.
- If secrets were previously committed to Git history, you must rotate/revoke them on the provider dashboard (Google/OpenAI/DeepSeek) and remove them from Git history using tools like `git filter-repo` or BFG.

Recommended Configuration
-------------------------
1. Store credentials locally and set environment variables. Example:
   - Windows PowerShell: `setx GOOGLE_CLIENT_SECRET_FILE "C:\path\to\client_secret.json"`
   - macOS/Linux: `export GOOGLE_CLIENT_SECRET_FILE=/path/to/client_secret.json`
2. Provide API keys via environment variables (do not hardcode). Example:
   - `OPENAI_API_KEY` for OpenAI
   - `DEEPSEEK_API_KEY` for DeepSeek (if used)

Files and Purpose
-----------------
- `main.py` — Main menu / orchestration for steps 1..10.
- `Step1_GetVideoSubtitle.py` — Download/select video, convert to audio, transcribe to SBV.
- `Step2_MergeSegments.py` — Merge and optimize English segments and timestamps.
- `Step2_1_DownloadYouTubeSubtitle.py` — Download existing SBV subtitles from YouTube.
- `Step3_SplitParts.py` — Split the merged English SBV into `PartN-Step3.sbv` files.
- `Step4_1stTranslate.py` — First translation round (literal + English included).
- `Step5_1Translate.py` — Second translation round (literal + meaning/adaptive versions).
- `Step6_Split.py` — Split/line-break Chinese subtitles for readability.
- `Step7_UploadParts.py` — Upload chosen Part subtitle files to YouTube via OAuth.
- `Step8_FinalDownloadUpload.py` — Download Parts from YouTube, merge, and upload final file.
- `Step9_MergeAllParts.py` — Merge Part translations into final combined files.
- `Step10_MoveOldFiles.py` — Archive old data into `OldFiles`.
- `common_utils.py` — Utilities for SBV/SRT parsing, time formatting, replacement rules, and OAuth helper.
- `.gitignore` — Ignore tokens, client secret files, media outputs and caches.
- `client_secret.example.json` — Example Google OAuth client secret JSON template.

Quick Start
-----------
1. Install dependencies (pip install the required packages).
2. Place your Google `client_secret.json` in a safe location and set `GOOGLE_CLIENT_SECRET_FILE`.
3. Run `python main.py` and choose steps from the menu.

Notes
-----
- If `ffmpeg` is not found when running Step 1, install ffmpeg and ensure it is on your PATH or update the script to point to the ffmpeg binary.
- Watch API usage limits and billing when calling OpenAI or other paid services.
- Before making the repository public, ensure no secrets remain in commits and that any leaked keys were revoked.

Contributing and Extensions
---------------------------
- You can add other translation providers or improve concurrency by editing the respective `Step*.py` modules.
- Consider keeping an example configuration file (e.g. `configuration.example`) and adding instructions for secure local setup.

License
-------
- Copyright notes are present in the file headers (2023-24). Add a LICENSE file if you intend to open-source this project.

Next Steps I Can Help With
--------------------------
- Scan the repository for potential secret leaks and list file locations (no secret values returned).  
- Convert remaining hardcoded keys to environment variable lookups across all files.  
- Provide commands and guidance to remove sensitive data from Git history using BFG or `git filter-repo`.

Choose one or tell me which task you want me to do next.
