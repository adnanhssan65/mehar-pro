from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional
from pathlib import Path
import yt_dlp
import re
import shutil
import subprocess
import os
import sys
import uuid
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

try:
    from PIL import Image
except ImportError:
    pass

app = FastAPI()

# Global states
progress_state = {} # Use dict for multi-user support in public version
cancel_tasks = set()

class ScanRequest(BaseModel): urls: List[str]; count: int = 5000
class DownloadRequest(BaseModel): selectedUrls: List[str]; quality: str; saveMode: str; task_id: str
class UniversalRequest(BaseModel): url: str; formatType: str; quality: str; task_id: str
class YTDocRequest(BaseModel): document_text: str; mode: str; quality: str; task_id: str

# PUBLIC PATHS (Server Based)
BASE_DIR = Path("./downloads")
BASE_DIR.mkdir(parents=True, exist_ok=True)
if not (BASE_DIR / "temp").exists(): (BASE_DIR / "temp").mkdir()

app.mount("/files", StaticFiles(directory=str(BASE_DIR)), name="files")

@app.get("/progress/{task_id}")
def get_progress(task_id: str):
    return JSONResponse(progress_state.get(task_id, {"is_active": False, "status": "Idle"}))

@app.get("/stop/{task_id}")
def stop_task(task_id: str):
    cancel_tasks.add(task_id)
    return {"status": "stopping"}

@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <!doctype html>
    <html lang="en" data-theme="dark">
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=0" />
      <title>Mehar Pro - Public Workspace</title>
      <style>
        :root {
            --bg-body: #0f172a; --bg-panel: #1e293b; --border-color: #334155;
            --text-main: #f8fafc; --text-muted: #94a3b8; --accent: #38bdf8;
            --input-bg: #0b1120; --shadow: 0 10px 25px -3px rgba(0,0,0,0.5);
        }
        [data-theme="light"] {
            --bg-body: #f8fafc; --bg-panel: #ffffff; --border-color: #e2e8f0;
            --text-main: #0f172a; --text-muted: #64748b; --accent: #3b82f6;
            --input-bg: #f1f5f9; --shadow: 0 4px 6px -1px rgba(0,0,0,0.1);
        }
        body { margin: 0; font-family: 'Inter', sans-serif; background: var(--bg-body); color: var(--text-main); padding: 20px; transition: 0.3s; padding-bottom: 60px; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 25px; padding-bottom: 15px; border-bottom: 1px solid var(--border-color); }
        .header h1 { margin: 0; font-size: 24px; font-weight: 900; }
        .theme-btn { background: var(--bg-panel); border: 1px solid var(--border-color); color: var(--text-main); width: 40px; height: 40px; border-radius: 12px; cursor: pointer; }
        
        .dashboard-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 15px; }
        .tool-card { background: var(--bg-panel); border: 1px solid var(--border-color); border-radius: 16px; padding: 20px 10px; text-align: center; cursor: pointer; transition: 0.3s; box-shadow: var(--shadow); display: flex; flex-direction: column; align-items: center; gap: 8px; }
        .tool-card:hover { transform: translateY(-4px); border-color: var(--accent); }
        .tool-icon { font-size: 30px; }
        .tool-title { font-size: 13px; font-weight: 700; }

        .tool-view { display: none; animation: fadeIn 0.3s ease; }
        .tool-view.active { display: block; }
        .back-nav { display: inline-flex; align-items: center; gap: 8px; font-size: 12px; font-weight: 700; color: var(--accent); cursor: pointer; margin-bottom: 20px; background: var(--bg-panel); padding: 10px 15px; border-radius: 12px; border: 1px solid var(--border-color); }
        .tool-container { background: var(--bg-panel); border: 1px solid var(--border-color); border-radius: 20px; padding: 20px; box-shadow: var(--shadow); }
        
        textarea, input[type="text"], select { width: 100%; border-radius: 12px; border: 1px solid var(--border-color); background: var(--input-bg); color: var(--text-main); padding: 12px; box-sizing: border-box; font-size: 13px; margin-bottom: 15px; font-weight: 500; }
        label { display: block; font-size: 12px; font-weight: 700; margin-bottom: 5px; }
        
        .btn-group { display: flex; flex-wrap: wrap; gap: 10px; }
        button.btn { flex: 1; min-width: 120px; border: none; padding: 14px; border-radius: 12px; cursor: pointer; font-weight: 700; font-size: 12px; transition: 0.2s; }
        .btn-primary { background: var(--accent); color: white; }
        .btn-secondary { background: var(--input-bg); color: var(--text-main); border: 1px solid var(--border-color); }
        .btn-danger { background: #ef4444; color: white; display: none; width: 100%; margin-top: 10px; }

        .status-box { background: var(--input-bg); padding: 15px; border-radius: 12px; margin-top: 20px; border-left: 4px solid var(--accent); font-size: 12px; word-wrap: break-word; }
        .download-link { display: inline-block; margin-top: 10px; padding: 10px 20px; background: #22c55e; color: white; border-radius: 8px; text-decoration: none; font-weight: 800; }
        
        .toast { position: fixed; top: 20px; left: 50%; transform: translateX(-50%) translateY(-100px); background: var(--text-main); color: var(--bg-body); padding: 12px 24px; border-radius: 30px; font-size: 12px; font-weight: 700; z-index: 9999; transition: 0.4s; }
        .toast.show { transform: translateX(-50%) translateY(0); }
        .file-wrapper { border: 2px dashed var(--border-color); border-radius: 16px; padding: 25px; text-align: center; cursor: pointer; background: var(--input-bg); margin-bottom: 15px; }
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
      </style>
    </head>
    <body>
      <div id="toast" class="toast">Action Completed!</div>
      <div class="header">
        <div><h1>Mehar Pro.</h1><span style="font-size:10px; color:var(--text-muted); font-weight:700; letter-spacing:1px;">PUBLIC SAAS</span></div>
        <button class="theme-btn" onclick="toggleTheme()">🌓</button>
      </div>

      <div id="view-dashboard" class="dashboard-grid">
        <div class="tool-card" onclick="showTool('tool-tiktok')"><div class="tool-icon">📱</div><div class="tool-title">TikTok Bulk</div></div>
        <div class="tool-card" onclick="showTool('tool-yt')"><div class="tool-icon">✂️</div><div class="tool-title">AI Shorts</div></div>
        <div class="tool-card" onclick="showTool('tool-universal')"><div class="tool-icon">🌍</div><div class="tool-title">Universal</div></div>
        <div class="tool-card" onclick="showTool('tool-mp3')"><div class="tool-icon">🎵</div><div class="tool-title">MP3 Audio</div></div>
        <div class="tool-card" onclick="showTool('tool-thumbnail')"><div class="tool-icon">🖼️</div><div class="tool-title">Thumbnails</div></div>
        <div class="tool-card" onclick="showTool('tool-img-convert')"><div class="tool-icon">🔄</div><div class="tool-title">Img Convert</div></div>
        <div class="tool-card" onclick="showTool('tool-pdf')"><div class="tool-icon">📄</div><div class="tool-title">Img to PDF</div></div>
      </div>

      <div id="tools-container">
        <div id="tool-tiktok" class="tool-view">
          <div class="back-nav" onclick="goHome()">🔙 Back Home</div>
          <div class="tool-container">
            <h3>TikTok Bulk Downloader</h3>
            <textarea id="urls" placeholder="Paste links line by line..."></textarea>
            <label>Quality</label>
            <select id="quality"><option value="worst">Fast (Low)</option><option value="best" selected>Original (HD)</option><option value="audio_only">MP3 Audio</option></select>
            <button class="btn btn-primary" id="btn-tiktok" onclick="runTikTok()">🚀 Start Download</button>
            <button class="btn btn-danger" id="stop-tiktok" onclick="stopTask()">🛑 Stop</button>
            <div class="status-box" id="stat-tiktok">Ready.</div>
          </div>
        </div>

        <div id="tool-yt" class="tool-view">
          <div class="back-nav" onclick="goHome()">🔙 Back Home</div>
          <div class="tool-container">
            <h3>YouTube AI Shorts</h3>
            <textarea id="ytDoc" placeholder="Paste script with timestamps..."></textarea>
            <label>Quality</label>
            <select id="ytQual"><option value="720p">720p</option><option value="1080p" selected>1080p</option></select>
            <button class="btn btn-primary" id="btn-yt" onclick="runYT()">✂️ Extract & Merge</button>
            <button class="btn btn-danger" id="stop-yt" onclick="stopTask()">🛑 Stop</button>
            <div class="status-box" id="stat-yt">Ready.</div>
          </div>
        </div>

        <div id="tool-universal" class="tool-view">
          <div class="back-nav" onclick="goHome()">🔙 Back Home</div>
          <div class="tool-container">
            <h3>Universal Downloader</h3>
            <input type="text" id="uniUrl" placeholder="https://...">
            <label>Type</label>
            <select id="uniType"><option value="video">Video</option><option value="audio">Audio (MP3)</option></select>
            <button class="btn btn-primary" id="btn-uni" onclick="runUni()">🚀 Download</button>
            <div class="status-box" id="stat-uni">Ready.</div>
          </div>
        </div>

        <div id="tool-mp3" class="tool-view">
          <div class="back-nav" onclick="goHome()">🔙 Back Home</div>
          <div class="tool-container">
            <h3>MP3 Converter</h3>
            <input type="file" id="mp3Files" multiple accept="video/*" style="display:none;" onchange="updateFileText('mp3Files','mp3Text')">
            <div class="file-wrapper" onclick="document.getElementById('mp3Files').click()"><p id="mp3Text">Click to select videos</p></div>
            <button class="btn btn-primary" id="btn-mp3" onclick="runMP3()">⚡ Convert to MP3</button>
            <div class="status-box" id="stat-mp3">Ready.</div>
          </div>
        </div>

        <div id="tool-thumbnail" class="tool-view">
          <div class="back-nav" onclick="goHome()">🔙 Back Home</div>
          <div class="tool-container">
            <h3>Thumbnail Grabber</h3>
            <input type="text" id="tUrl" placeholder="YouTube Link...">
            <button class="btn btn-primary" onclick="getT()">🖼️ Get HD Cover</button>
            <div class="status-box" id="stat-t" style="display:none;"></div>
          </div>
        </div>

        <div id="tool-img-convert" class="tool-view">
          <div class="back-nav" onclick="goHome()">🔙 Back Home</div>
          <div class="tool-container">
            <h3>Image Converter</h3>
            <input type="file" id="imgFiles" multiple accept="image/*" style="display:none;" onchange="updateFileText('imgFiles','imgText')">
            <div class="file-wrapper" onclick="document.getElementById('imgFiles').click()"><p id="imgText">Select Images</p></div>
            <label>To Format</label>
            <select id="imgFmt"><option value="PNG">PNG</option><option value="JPEG">JPG</option><option value="WEBP">WEBP</option></select>
            <button class="btn btn-primary" id="btn-img" onclick="runImg()">🔄 Convert Now</button>
            <div class="status-box" id="stat-img">Ready.</div>
          </div>
        </div>

        <div id="tool-pdf" class="tool-view">
          <div class="back-nav" onclick="goHome()">🔙 Back Home</div>
          <div class="tool-container">
            <h3>Image to PDF</h3>
            <input type="file" id="pdfFiles" multiple accept="image/*" style="display:none;" onchange="updateFileText('pdfFiles','pdfText')">
            <div class="file-wrapper" onclick="document.getElementById('pdfFiles').click()"><p id="pdfText">Select Images</p></div>
            <button class="btn btn-primary" id="btn-pdf" onclick="runPDF()">📑 Create PDF</button>
            <div class="status-box" id="stat-pdf">Ready.</div>
          </div>
        </div>
      </div>

      <script>
        let currentTaskId = "";
        function showTool(id){ document.getElementById('view-dashboard').style.display='none'; document.getElementById(id).classList.add('active'); window.scrollTo(0,0); }
        function goHome(){ document.querySelectorAll('.tool-view').forEach(v=>v.classList.remove('active')); document.getElementById('view-dashboard').style.display='grid'; }
        function toggleTheme(){ let t = document.documentElement.getAttribute('data-theme')==='dark'?'light':'dark'; document.documentElement.setAttribute('data-theme', t); }
        function toast(m){ let x=document.getElementById('toast'); x.innerText=m; x.classList.add('show'); setTimeout(()=>x.classList.remove('show'), 3000); }
        function updateFileText(id, tid){ let f=document.getElementById(id).files; document.getElementById(tid).innerText = f.length + " files selected"; }

        async function poll(tid, sid, bid, stp){
            let inter = setInterval(async ()=>{
                let r = await fetch('/progress/'+tid); let d = await r.json();
                if(d.is_active){ document.getElementById(sid).innerText = d.status; document.getElementById(bid).style.display='none'; if(stp)document.getElementById(stp).style.display='block'; }
                else { clearInterval(inter); document.getElementById(bid).style.display='block'; if(stp)document.getElementById(stp).style.display='none'; }
            }, 1500);
        }

        async function runTikTok(){
            let urls = document.getElementById('urls').value.split('\\n').filter(Boolean); if(!urls.length) return;
            currentTaskId = "tk_"+Date.now(); document.getElementById('stat-tiktok').innerText = "Initializing...";
            let res = await fetch('/download', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({selectedUrls:urls, quality:document.getElementById('quality').value, saveMode:'zip', task_id:currentTaskId}) });
            let d = await res.json();
            if(d.status==='done') { document.getElementById('stat-tiktok').innerHTML = `✅ Complete! <br><a href="/files/${d.location}" class="download-link" download>📥 DOWNLOAD ZIP</a>`; toast("Success!"); }
            else poll(currentTaskId, 'stat-tiktok', 'btn-tiktok', 'stop-tiktok');
        }

        async function runYT(){
            let txt = document.getElementById('ytDoc').value; if(!txt) return;
            currentTaskId = "yt_"+Date.now();
            let res = await fetch('/process-yt-document', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({document_text:txt, mode:'zip', quality:document.getElementById('ytQual').value, task_id:currentTaskId}) });
            poll(currentTaskId, 'stat-yt', 'btn-yt', 'stop-yt');
            let d = await res.json(); 
            if(d.status==='done') document.getElementById('stat-yt').innerHTML = `✅ Done! <br><a href="/files/${d.location}" class="download-link" download>📥 DOWNLOAD SHORTS</a>`;
        }

        async function runUni(){
            let u = document.getElementById('uniUrl').value; if(!u) return;
            currentTaskId = "un_"+Date.now();
            let res = await fetch('/universal-download', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({url:u, formatType:document.getElementById('uniType').value, quality:'best', task_id:currentTaskId}) });
            poll(currentTaskId, 'stat-uni', 'btn-uni', '');
            let d = await res.json();
            if(d.status==='done') document.getElementById('stat-uni').innerHTML = `✅ Ready! <br><a href="/files/${d.location}" class="download-link" download>📥 DOWNLOAD MEDIA</a>`;
        }

        async function stopTask(){ await fetch('/stop/'+currentTaskId); }

        function getT(){
            let u = document.getElementById('tUrl').value;
            let m = u.match(/(?:v=|\\/)([0-9A-Za-z_-]{11})/);
            if(m){ let img = `https://img.youtube.com/vi/${m[1]}/maxresdefault.jpg`; document.getElementById('stat-t').style.display='block'; document.getElementById('stat-t').innerHTML=`<img src="${img}" style="width:100%; border-radius:10px;"><br><a href="${img}" target="_blank" class="download-link">📥 OPEN FULL HD</a>`; }
        }
        
        async function runImg(){
            let f = document.getElementById('imgFiles').files; if(!f.length) return;
            let fd = new FormData(); for(let x of f) fd.append('files', x); fd.append('target_format', document.getElementById('imgFmt').value);
            document.getElementById('stat-img').innerText = "Processing...";
            let res = await fetch('/convert-image-format', {method:'POST', body:fd});
            let d = await res.json(); document.getElementById('stat-img').innerHTML = `✅ Converted! <br><a href="/files/${d.location}" class="download-link" download>📥 DOWNLOAD ALL</a>`;
        }

        async function runPDF(){
            let f = document.getElementById('pdfFiles').files; if(!f.length) return;
            let fd = new FormData(); for(let x of f) fd.append('files', x);
            document.getElementById('stat-pdf').innerText = "Generating PDF...";
            let res = await fetch('/images-to-pdf', {method:'POST', body:fd});
            let d = await res.json(); document.getElementById('stat-pdf').innerHTML = `✅ PDF Ready! <br><a href="/files/${d.location}" class="download-link" download>📥 DOWNLOAD PDF</a>`;
        }

        async function runMP3(){
            let f = document.getElementById('mp3Files').files; if(!f.length) return;
            let fd = new FormData(); for(let x of f) fd.append('files', x);
            document.getElementById('stat-mp3').innerText = "Converting... takes time for large files.";
            let res = await fetch('/convert-mp3-upload', {method:'POST', body:fd});
            let d = await res.json(); document.getElementById('stat-mp3').innerHTML = `✅ MP3 Ready! <br><a href="/files/${d.location}" class="download-link" download>📥 DOWNLOAD ZIP</a>`;
        }
      </script>
    </body>
    </html>
    """
# --- BACKEND LOGIC (Part 2) ---

def my_hook(d, task_id):
    if task_id in cancel_tasks:
        raise Exception("Download Cancelled")

def download_single_video(url: str, folder: Path, quality: str, name: str, task_id: str):
    if task_id in cancel_tasks: return False
    ydl_opts = {
        'outtmpl': str(folder / f'{name}.%(ext)s'),
        'quiet': True, 'no_warnings': True, 'ignoreerrors': True, 'nopart': True,
        'progress_hooks': [lambda d: my_hook(d, task_id)]
    }
    if quality == "audio_only":
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}]
    else:
        ydl_opts['merge_output_format'] = 'mp4'
        ydl_opts['format'] = 'worst[ext=mp4]/worst' if quality == "worst" else 'best[ext=mp4]/bestvideo+bestaudio/best'
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl: ydl.download([url])
        return True
    except: return False

@app.post("/scan")
async def scan(req: ScanRequest):
    seen = set(); cleaned = []
    for u in req.urls:
        val = u.strip()
        if val and val not in seen: seen.add(val); cleaned.append(val)
    return {"results": [{"url": u} for u in cleaned[:req.count]]}

@app.post("/download")
def download(req: DownloadRequest):
    tid = req.task_id
    progress_state[tid] = {"is_active": True, "total": len(req.selectedUrls), "completed": 0, "status": "Starting..."}
    folder_name = f"tiktok_{uuid.uuid4().hex[:6]}"
    folder_path = BASE_DIR / "temp" / folder_name
    folder_path.mkdir(parents=True, exist_ok=True)
    
    try:
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(download_single_video, url, folder_path, req.quality, f"Vid_{i:02d}", tid): url for i, url in enumerate(req.selectedUrls, 1)}
            for future in as_completed(futures):
                if tid in cancel_tasks: return JSONResponse({"status": "error", "error": "Cancelled"})
                progress_state[tid]["completed"] += 1
                progress_state[tid]["status"] = f"Downloading... ({progress_state[tid]['completed']}/{progress_state[tid]['total']})"
        
        # Create ZIP for user to download
        shutil.make_archive(str(BASE_DIR / "temp" / folder_name), 'zip', str(folder_path))
        
        progress_state[tid]["is_active"] = False
        return JSONResponse({"status": "done", "location": f"temp/{folder_name}.zip"})
    except Exception as e:
        progress_state[tid]["is_active"] = False
        return JSONResponse({"status": "error", "error": str(e)})

@app.post("/universal-download")
def universal_download(req: UniversalRequest):
    tid = req.task_id
    progress_state[tid] = {"is_active": True, "total": 1, "completed": 0, "status": "Grabbing Media..."}
    folder_name = f"uni_{uuid.uuid4().hex[:6]}"
    folder_path = BASE_DIR / "temp" / folder_name
    folder_path.mkdir(parents=True, exist_ok=True)
    
    ydl_opts = {
        'outtmpl': str(folder_path / 'Media_%(title)s.%(ext)s'),
        'quiet': True, 'no_warnings': True,
        'progress_hooks': [lambda d: my_hook(d, tid)]
    }
    if req.formatType == "audio":
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}]
    else:
        ydl_opts['merge_output_format'] = 'mp4'
        ydl_opts['format'] = 'worst[ext=mp4]/worst' if req.quality == "worst" else 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
        
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl: ydl.download([req.url])
        shutil.make_archive(str(BASE_DIR / "temp" / folder_name), 'zip', str(folder_path))
        
        progress_state[tid]["is_active"] = False
        return JSONResponse({"status": "done", "location": f"temp/{folder_name}.zip"})
    except Exception as e:
        progress_state[tid]["is_active"] = False
        return JSONResponse({"status": "error", "error": str(e)})

def time_to_sec(t_str):
    parts = t_str.split(':')
    if len(parts) == 2: return int(parts[0]) * 60 + int(parts[1])
    elif len(parts) == 3: return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    return 0

@app.post("/process-yt-document")
def process_yt_document(req: YTDocRequest):
    tid = req.task_id
    text = req.document_text
    url_match = re.search(r'https?://(?:www\.)?youtube\.com/watch\?v=[\w-]+|https?://youtu\.be/[\w-]+', text)
    if not url_match: return JSONResponse({"status": "error", "message": "YouTube URL missing!"})
    yt_url = url_match.group(0)

    folder_name = f"shorts_{uuid.uuid4().hex[:6]}"
    folder_path = BASE_DIR / "temp" / folder_name
    folder_path.mkdir(parents=True, exist_ok=True)
    temp_p = folder_path / "parts"
    temp_p.mkdir(exist_ok=True)
    
    progress_state[tid] = {"is_active": True, "total": 100, "completed": 0, "status": "Parsing..."}

    main_clips_text = re.split(r'(?:\.|\-){20,}', text)
    final_clips_data = []

    for main_clip in main_clips_text:
        sub_clips_text = re.split(r'(?:\.|\-){3,19}|\(?add\)?', main_clip, flags=re.IGNORECASE)
        curr_segs = []
        for sub in sub_clips_text:
            times = re.findall(r'\b\d{1,2}:\d{2}(?::\d{2})?\b', sub)
            if len(times) >= 2:
                s_val, e_val = time_to_sec(times[0]), time_to_sec(times[-1])
                if e_val > s_val: curr_segs.append((float(s_val), float(e_val)))
        if curr_segs: final_clips_data.append(curr_segs)

    if not final_clips_data:
        progress_state[tid]["is_active"] = False
        return JSONResponse({"status": "error", "message": "No valid timestamps found!"})

    fmt = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]'
    if req.quality == "720p": fmt = 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]'
    elif req.quality == "1080p": fmt = 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]'

    progress_state[tid]["total"] = len(final_clips_data)
    progress_state[tid]["completed"] = 0
    total_extracted = 0
    
    for i, segments in enumerate(final_clips_data, 1):
        if tid in cancel_tasks: break
        part_files = []
        for j, (start, end) in enumerate(segments, 1):
            progress_state[tid]["status"] = f"Extracting Clip {i} (Part {j}/{len(segments)})..."
            out_part = temp_p / f"c_{i}_p_{j}.mp4"
            cmd = [sys.executable, '-m', 'yt_dlp', '-f', fmt, '--download-sections', f"*{start}-{end}", '--force-keyframes-at-cuts', '--quiet', '--no-warnings', '-o', str(out_part), yt_url]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if out_part.exists(): part_files.append(out_part)
        
        if len(part_files) > 0:
            total_extracted += 1
            progress_state[tid]["status"] = f"Merging Clip {i}..."
            final_output = folder_path / f"Viral_Short_{i:02d}.mp4"
            if len(part_files) == 1: shutil.move(str(part_files[0]), str(final_output))
            elif len(part_files) > 1:
                list_txt = temp_p / f"list_{i}.txt"
                with open(list_txt, "w") as f:
                    for pf in part_files: f.write(f"file '{pf.name}'\n")
                subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', str(list_txt), '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '22', '-c:a', 'aac', str(final_output)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        progress_state[tid]["completed"] += 1

    try: shutil.rmtree(temp_p)
    except: pass

    if total_extracted == 0:
        progress_state[tid]["is_active"] = False
        return JSONResponse({"status": "error", "message": "Extraction Failed."})

    shutil.make_archive(str(BASE_DIR / "temp" / folder_name), 'zip', str(folder_path))
    progress_state[tid]["is_active"] = False
    return JSONResponse({"status": "done", "location": f"temp/{folder_name}.zip"})

@app.post("/convert-mp3-upload")
async def convert_mp3_upload(files: List[UploadFile] = File(...)):
    folder_name = f"mp3_{uuid.uuid4().hex[:6]}"
    mp3_dir = BASE_DIR / "temp" / folder_name
    mp3_dir.mkdir(parents=True, exist_ok=True)
    converted = 0
    try:
        for file in files:
            temp_file = mp3_dir / file.filename
            with open(temp_file, "wb") as buffer: shutil.copyfileobj(file.file, buffer)
            out_file = mp3_dir / f"{Path(file.filename).stem}_Audio.mp3"
            subprocess.run(['ffmpeg', '-y', '-i', str(temp_file), '-q:a', '0', '-map', 'a', str(out_file)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if temp_file.exists(): temp_file.unlink() # remove original video to save space in zip
            converted += 1
            
        shutil.make_archive(str(BASE_DIR / "temp" / folder_name), 'zip', str(mp3_dir))
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)})

    return JSONResponse({"status": "done", "location": f"temp/{folder_name}.zip"})

@app.post("/convert-image-format")
async def convert_image_format(files: List[UploadFile] = File(...), target_format: str = Form(...)):
    if 'PIL' not in sys.modules: return JSONResponse({"status": "error", "message": "Pillow not installed."})
    folder_name = f"img_{uuid.uuid4().hex[:6]}"
    out_dir = BASE_DIR / "temp" / folder_name
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = target_format.lower()
    if ext == 'jpeg': ext = 'jpg'
    
    for file in files:
        try:
            img = Image.open(file.file)
            if target_format in ['JPEG', 'JPG'] and img.mode in ("RGBA", "P"): img = img.convert("RGB")
            out_file = out_dir / f"{Path(file.filename).stem}_Converted.{ext}"
            img.save(str(out_file), format=target_format)
        except: pass
        
    shutil.make_archive(str(BASE_DIR / "temp" / folder_name), 'zip', str(out_dir))
    return JSONResponse({"status": "done", "location": f"temp/{folder_name}.zip"})

@app.post("/images-to-pdf")
async def images_to_pdf(files: List[UploadFile] = File(...)):
    if 'PIL' not in sys.modules: return JSONResponse({"status": "error", "message": "Pillow not installed."})
    if not files: return JSONResponse({"status": "error", "message": "No images provided."})
    
    folder_name = f"pdf_{uuid.uuid4().hex[:6]}"
    out_dir = BASE_DIR / "temp" / folder_name
    out_dir.mkdir(parents=True, exist_ok=True)
    
    img_list = []
    try:
        first_img = Image.open(files[0].file).convert('RGB')
        for file in files[1:]:
            img = Image.open(file.file).convert('RGB')
            img_list.append(img)
            
        out_file = out_dir / "Document_MeharPro.pdf"
        first_img.save(str(out_file), save_all=True, append_images=img_list)
        return JSONResponse({"status": "done", "location": f"temp/{folder_name}/Document_MeharPro.pdf"})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)})
