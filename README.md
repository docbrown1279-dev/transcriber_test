# transcriber_test

A tiny **offline speech-to-text** web app. Upload an audio file (or try the
bundled demo clip) and get a transcript back — no API keys and no network
calls. Audio is normalized with `ffmpeg` and transcribed by
[PocketSphinx](https://github.com/cmusphinx/pocketsphinx) using its bundled
English model.

## Stack

- **Backend:** Python + Flask (`app.py`)
- **Transcription:** PocketSphinx (offline, bundled acoustic/language model)
- **Audio decoding:** ffmpeg (converts any input to 16 kHz mono PCM)
- **Frontend:** static HTML/CSS/JS (drag-and-drop upload)

## Requirements

System packages: `ffmpeg`, `espeak-ng` (used to synthesize test audio),
plus build tooling to compile PocketSphinx (`build-essential`, `cmake`,
`bison`, `flex`, `python3-dev`, `python3-venv`).

## Setup

```bash
bash .cursor/install.sh   # installs system deps + creates .venv
```

Or manually:

```bash
sudo apt-get install -y ffmpeg espeak-ng build-essential cmake bison flex python3-dev python3-venv
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Run

```bash
. .venv/bin/activate
python app.py
# open http://localhost:5000
```

Set `PORT` to change the port (defaults to `5000`).

## Try it

- Click **"Try a demo sample"** in the UI, or
- Drag in any `wav/mp3/m4a/ogg/flac/webm` file.

### From the command line

```bash
# Transcribe the bundled sample
curl -s -F "audio=@samples/go-forward.wav" http://localhost:5000/transcribe
# -> {"transcript":"go forward ten meters"}

# Generate your own test clip with espeak-ng
espeak-ng "go forward ten meters" -w /tmp/clip.wav
curl -s -F "audio=@/tmp/clip.wav" http://localhost:5000/transcribe
```

> Note: PocketSphinx is a lightweight offline recognizer. It is most accurate
> on clear human speech (like the bundled `samples/go-forward.wav`); heavily
> synthesized or noisy audio may transcribe less accurately.

## Endpoints

| Method | Path                 | Description                          |
| ------ | -------------------- | ------------------------------------ |
| GET    | `/`                  | Web UI                               |
| POST   | `/transcribe`        | Transcribe an uploaded `audio` file  |
| POST   | `/transcribe-sample` | Transcribe the bundled demo clip     |
| GET    | `/healthz`           | Health check (`{"status":"ok"}`)     |
