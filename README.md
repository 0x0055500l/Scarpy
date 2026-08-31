# Web Discovery Agent

Autonomous agent for web discovery and structured extraction, using Playwright and LLMs.

## Features
- Deterministic execution when possible.
- AI-driven discovery and extraction when needed.
- Action -> Observe -> Verify -> Recovery loop.

## Setup

1. Copy `.env.example` to `.env` and fill in your keys.
2. Run with Docker Compose:
   ```bash
   docker-compose up -d --build
   ```

## Development
Create a virtual environment and install dependencies:
```bash
python -m venv venv
source venv/bin/activate  # Or venv\Scripts\activate on Windows
pip install -r requirements-dev.txt
```

Run tests:
```bash
pytest
```
