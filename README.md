# Universal File to CSV Converter Web App

A web application that allows users to upload files (`.mbox`, `.json`, `.jsonl`, `.xlsx`, `.xml`, `.tsv`, `.txt`) and convert them into structured CSV files for download.

---

## Features
- **Drag & Drop Web UI**: Clean interface styled with Tailwind CSS.
- **Real-Time Progress Streaming**: Tracks percentage and status for multi-gigabyte files (e.g., Gmail `.mbox` exports).
- **Format Auto-Detection**: Supports MBOX, JSON, Excel, XML, and TSV files.
- **Production & Hosting Ready**: Pre-configured with Docker, Docker Compose, Procfile, and Waitress/Gunicorn.

---

## 1. How to Run Locally

### Install Dependencies
```bash
pip install -r requirements.txt
```

### Start Local Web Server
```bash
python wsgi.py
```
Open your browser and navigate to `http://localhost:5000`.

---

## 2. How to Host on Cloud Platforms

### Option A: Hosting on Render (Free / Easy)
1. Push this repository to GitHub.
2. Log in to [Render](https://render.com) and click **New +** -> **Web Service**.
3. Connect your repository.
4. Render will automatically detect `Procfile` or `Dockerfile`.
5. Click **Create Web Service**. Your app is live!

### Option B: Hosting with Docker / Docker Compose
On any VPS (DigitalOcean, AWS EC2, Linode):
```bash
docker-compose up -d --build
```
Your app will be live on `http://YOUR_SERVER_IP:5000`.

### Option C: Hosting on Railway / Fly.io
Simply deploy the repo using Railway CLI or `fly launch`. The included `Dockerfile` and `Procfile` handle containerization automatically.
