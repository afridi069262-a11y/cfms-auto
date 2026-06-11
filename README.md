# CMS Auto Runner — Web Interface

Punjab Prosecution fast_runner.py ka web interface.

## Features
- Browser se directly login (username + password)
- Ya manual XSRF + session cookie paste
- Prosecutor list API se auto-load + select
- Tab-separated case data paste karke Run
- Real-time live logs (Server-Sent Events)
- Stats: Total / Success / Skip / Invalid

---

## Free Deployment — Render.com

### Step 1: GitHub pe upload karo
1. GitHub account banao (free): https://github.com
2. New repository banao: `cms-auto-runner`
3. In sab files ko upload karo:
   - `app.py`
   - `fast_runner.py`
   - `requirements.txt`
   - `render.yaml`
   - `Procfile`
   - `templates/index.html`

### Step 2: Render pe deploy karo
1. https://render.com pe signup karo (free)
2. "New Web Service" → GitHub repo connect karo
3. Settings:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120`
   - **Plan:** Free
4. Deploy!

5. URL milega: `https://cms-auto-runner.onrender.com`

---

## Local Chalane ke liye

```bash
pip install flask requests gunicorn
python app.py
# Browser mein: http://localhost:5000
```

---

## Istemal

1. **Login Tab** — username/password ya manual cookies
2. **Prosecutor** select karo
3. **Run Tab** — data paste karo, Run karo
4. Logs real-time dikhenge

### Input Format (Tab separated):
```
Sr  [Extra]  FIR_No  Year  Offence      Station     Date       Decision
1   200      22      2024  379 PPC      Rang Mehal  01-01-24   Acquitted
```

### Notes:
- Session ~2 ghante valid rehti hai
- Expire hone par dobara login
