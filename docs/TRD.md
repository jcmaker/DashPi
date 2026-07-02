# TRD — DashPi

## System Architecture
- Raspberry Pi (recording + processing)
- FastAPI server (local)
- Mobile app (client)

## Components
- recorder.py (loop recording)
- clip_agent.py (clip extraction)
- reasoning_agent.py (LLM summary)
- api_server.py (FastAPI endpoints)

## Communication
- Bluetooth: trigger only
- WiFi Hotspot: API communication

## Tech Stack
- Python
- FastAPI
- OpenCV
- Picamera2
- Ollama (LLM)

## API Endpoints
- POST /trigger
- GET /status
- GET /result

## Storage
- /videos/raw
- /videos/clips
- /results

## Constraints
- Offline-first
- Limited compute on Pi
