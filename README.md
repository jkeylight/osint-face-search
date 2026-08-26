# OSINT Face Search Tool

Reverse Image Search + Local Face Verification

A powerful OSINT tool that aggregates results from multiple search engines and verifies them locally using face recognition.

## Features

- **Multi-Engine Search**: Google Lens, Yandex, Bing Visual Search
- **Local Face Verification**: InsightFace (99.86% accuracy)
- **Smart Preprocessing**: Multi-region extraction + augmentation
- **Adaptive Thresholds**: Quality-based dynamic filtering
- **Result Deduplication**: pHash-based near-duplicate removal
- **Dark Theme UI**: Professional desktop interface
- **Audit Trail**: SHA-256 hashing, timestamped logs
- **Export**: CSV, JSON, evidence packages

## Setup (Windows)

### 1. Install Python 3.10+

Download from: https://www.python.org/downloads/

Make sure to check "Add Python to PATH" during installation.

### 2. Install Dependencies

Open Command Prompt and navigate to the project folder:

```cmd
cd C:\Users\norma\OneDrive\Desktop\NJ-SECURE MEDIA VAULT\osint-face-search
pip install -r requirements.txt
```

### 3. Install Playwright Browsers

```cmd
playwright install chromium
```

### 4. Run the Application

```cmd
python run.py
```

The app will open in your browser at http://localhost:8000

## Usage

1. **Upload Image**: Drag & drop or click to upload a face photo
2. **Click Search**: Tool queries Google Lens, Yandex, and Bing
3. **View Results**: Browse verified matches with confidence scores
4. **Compare**: Click any result to see side-by-side comparison
5. **Feedback**: Mark results as correct/incorrect to improve accuracy

## Project Structure

```
osint-face-search/
├── app/
│   ├── main.py           # FastAPI server
│   ├── config.py         # Settings
│   └── database.py       # SQLite operations
├── engine/
│   ├── face_engine.py    # InsightFace integration
│   └── preprocessor.py   # Multi-region extraction
├── scrapers/
│   ├── base.py           # Abstract adapter
│   ├── google_lens.py    # Google Lens scraper
│   ├── yandex.py         # Yandex scraper
│   └── bing.py           # Bing scraper
├── utils/
│   └── hashing.py        # SHA-256, pHash
├── static/
│   ├── index.html        # UI
│   ├── style.css         # Dark theme
│   └── app.js            # Frontend logic
├── uploads/              # Uploaded images
├── cache/                # Engine response cache
├── data/                 # SQLite database
├── requirements.txt
└── run.py                # Entry point
```

## Tech Stack

| Component | Technology |
|-----------|------------|
| Face Recognition | InsightFace (ArcFace) |
| Face Detection | SCRFD |
| Web Scraping | Playwright |
| API | FastAPI |
| Database | SQLite |
| UI | Vanilla HTML/CSS/JS |

## Cost

**$0/month** - All open-source tools, runs locally.

## Privacy

All processing happens on your machine. No data is sent to external servers except the search engines you query (Google, Yandex, Bing).

## Troubleshooting

### "No module named 'insightface'"
```cmd
pip install insightface onnxruntime
```

### "Playwright not installed"
```cmd
playwright install chromium
```

### "CUDA out of memory"
The tool uses CPU by default. If you have a GPU, install CUDA-enabled onnxruntime:
```cmd
pip install onnxruntime-gpu
```

### Slow performance
- First run downloads the InsightFace model (~300MB)
- Subsequent runs will be faster
- Consider using a GPU for better performance
