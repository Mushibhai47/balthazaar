# Milestone 2: Keywords & Web Traffic Engine - Setup Guide

## Overview

M2 implements an automated keyword research system that collects data from multiple sources:
- ✅ **OpenAI ChatGPT** - AI-powered keyword insights (IMPLEMENTED)
- ✅ **Google Gemini** - Alternative AI insights (IMPLEMENTED)
- ✅ **YouTube** - Video platform trends (IMPLEMENTED)
- ⏳ **Google Ads** - Paid search data (pending developer token)
- ⏳ **TikTok** - Social media trends (free, will implement next)
- ⏳ **Instagram** - Hashtag insights (free, will implement next)
- ⏳ **Ubersuggest** - SEO data (free scraping, will implement next)

## Architecture

**Async Processing:** Celery + Redis handle background tasks without blocking the Flask server.

**Data Flow:**
1. User clicks "Run Now" on a query
2. Flask creates a Report with status="pending"
3. Celery task queued in Redis
4. Background worker collects data from each source
5. Results stored incrementally in Report.data (JSON)
6. Status updates to "complete" or "failed"

## Prerequisites

### Required Software

1. **Redis** - Message broker for Celery
   - Windows: Download from https://github.com/microsoftarchive/redis/releases
   - Or use Docker: `docker run -d -p 6379:6379 redis:alpine`

2. **Python Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

## Installation Steps

### 1. Install Redis

**Option A: Native Windows**
```bash
# Download Redis from https://github.com/microsoftarchive/redis/releases
# Extract and run:
redis-server.exe
```

**Option B: Docker (Recommended)**
```bash
docker run -d -p 6379:6379 --name balthazaar-redis redis:alpine
```

### 2. Install Python Dependencies

```bash
cd c:/Users/musha/Desktop/Test_Task/balthazaar
pip install -r requirements.txt
```

### 3. Set Up API Credentials

We have a helper script to securely store API keys:

**OpenAI (Already Configured):**
```bash
python setup_credentials.py openai sk-proj-YOUR_API_KEY_HERE
```

**Google Gemini (When Ready):**
```bash
python setup_credentials.py gemini AIza-YOUR_API_KEY_HERE
```

**YouTube (When Ready):**
```bash
python setup_credentials.py youtube AIza-YOUR_API_KEY_HERE
```

**List Configured Credentials:**
```bash
python setup_credentials.py list
```

### 4. Run the Application

You need **3 terminal windows** running simultaneously:

**Terminal 1: Flask Server**
```bash
cd c:/Users/musha/Desktop/Test_Task/balthazaar
python main.py
```

**Terminal 2: Redis Server** (if not using Docker)
```bash
redis-server
```

**Terminal 3: Celery Worker**
```bash
cd c:/Users/musha/Desktop/Test_Task/balthazaar
celery -A tasks worker --loglevel=info --pool=solo
```

Note: `--pool=solo` is required for Windows compatibility.

## Usage

### Running a Keyword Report

1. Go to a client's page
2. Find their query (keywords + countries)
3. Click **"Run Now"** button
4. Report status updates in real-time:
   - `pending` → Task queued
   - `running` → Collecting data
   - `complete` → Success
   - `failed` → Error occurred

### Monitoring Progress

The system stores progress information in the Report.data JSON field:

```json
{
  "version": "2.0",
  "keywords": {
    "openai": {
      "keyword1": {
        "search_volume": 10000,
        "competition": "MEDIUM",
        "estimated_cpc": 2.50,
        "intent": "commercial"
      }
    }
  },
  "metadata": {
    "progress": 100,
    "sources_succeeded": ["openai"],
    "sources_failed": [],
    "errors": {}
  }
}
```

## API Endpoints

### Check Report Status
```
GET /api/reports/<report_id>/status
```

Returns:
```json
{
  "id": 1,
  "status": "complete",
  "progress": 100,
  "sources_succeeded": 1,
  "sources_failed": 0,
  "errors": {},
  "generated_at": "2026-02-28T10:00:00"
}
```

## Adding New Data Sources

To add a new collector (e.g., Google Gemini):

1. **Create collector class:**
   ```python
   # sources/gemini_keywords.py
   from sources.base import BaseKeywordCollector
   from typing import Dict, List, Any
   import google.generativeai as genai

   class GeminiCollector(BaseKeywordCollector):
       def __init__(self, credentials: Dict[str, Any]):
           super().__init__(credentials)
           genai.configure(api_key=credentials.get("api_key"))
           self.model = genai.GenerativeModel('gemini-pro')

       def collect(self, keywords: List[str], countries: List[str]) -> Dict[str, Any]:
           # Implement collection logic
           pass
   ```

2. **Register in tasks.py:**
   ```python
   collectors_config = [
       {"name": "openai", "module": "sources.openai_keywords", "class": "OpenAICollector"},
       {"name": "google_gemini", "module": "sources.gemini_keywords", "class": "GeminiCollector"},  # Add this
   ]
   ```

3. **Add credentials:**
   ```bash
   python setup_credentials.py gemini YOUR_API_KEY
   ```

## Troubleshooting

### Redis Connection Error
```
Error: Redis connection failed
```
**Fix:** Make sure Redis is running (`redis-server` or Docker container)

### Celery Worker Not Starting
```
Error: No module named 'celery_app'
```
**Fix:** Make sure you're in the balthazaar directory when running celery command

### Report Stuck in "Pending"
**Fix:** Check that Celery worker is running in Terminal 3

### API Key Errors
```
Error: OpenAI API key not found
```
**Fix:** Run `python setup_credentials.py openai YOUR_KEY`

## Next Steps

### Phase 3: Add High-Value Sources
- [ ] Google Gemini collector
- [ ] YouTube API collector
- [ ] Google Ads API (complex setup)

### Phase 4: Add Free Sources
- [ ] TikTok (unofficial API)
- [ ] Instagram (scraping)
- [ ] Ubersuggest (scraping)

### Phase 5: Aggregation
- [ ] Combine data from all sources
- [ ] Calculate aggregated insights
- [ ] UI improvements (real-time progress bars)

## Security Notes

- API keys are encrypted in database using Fernet encryption
- Encryption key stored in environment variable `ENCRYPTION_KEY`
- For production, generate secure key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- Never commit API keys to git

## File Structure

```
balthazaar/
├── celery_app.py              # Celery initialization
├── tasks.py                   # Background task definitions
├── setup_credentials.py       # Helper script for API keys
├── config.py                  # Configuration (Celery, Redis, encryption)
├── sources/
│   ├── __init__.py
│   ├── base.py                # Abstract base collector class
│   ├── openai_keywords.py     # OpenAI ChatGPT collector
│   └── [more collectors...]
└── database/
    └── models.py              # APICredential model added
```

## Testing

Test the OpenAI collector manually:
```python
from sources.openai_keywords import OpenAICollector

creds = {"api_key": "sk-proj-YOUR_KEY"}
collector = OpenAICollector(creds)
result = collector.safe_collect(["digital marketing"], ["United States"])
print(result)
```

## Status

**✅ Phase 1 Complete:** Foundation (Celery + Redis + secure credentials)
**✅ Phase 2 Complete:** First source (OpenAI ChatGPT)
**✅ Phase 3 Complete:** High-value sources (Google Gemini + YouTube)
**⏳ Phase 4 Next:** Free sources (TikTok, Instagram, Ubersuggest)

**Current Capabilities:**
- Async task processing ✓
- Encrypted credential storage ✓
- OpenAI keyword insights ✓
- Google Gemini AI insights ✓
- YouTube video trends & engagement data ✓
- Real-time status API ✓
- Error handling & retries ✓
- 3 active data sources collecting simultaneously ✓
