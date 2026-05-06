from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse
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
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

try:
    from PIL import Image
except ImportError:
    pass # Managed by pip install Pillow

app = FastAPI()

# Global states
progress_state = {}
cancel_tasks = set()

class ScanRequest(BaseModel): urls: List[str]; count: int = 5000
class DownloadRequest(BaseModel): selectedUrls: List[str]; quality: str; saveMode: str; task_id: str
class UniversalRequest(BaseModel): url: str; formatType: str; quality: str; task_id: str
class YTDocRequest(BaseModel): document_text: str; mode: str; quality: str; task_id: str

# PUBLIC PATHS (Server Based - For Render Cloud)
BASE_DIR = Path("./downloads")
BASE_DIR.mkdir(parents=True, exist_ok=True)
if not (BASE_DIR / "temp").exists(): (BASE_DIR / "temp").mkdir()

app.mount("/files", StaticFiles(directory=str(BASE_DIR)), name="files")

@app.get("/health")
def health(): return {"ok": True, "server": "running"}

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
    <html lang="en" data-theme="light">
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=0" />
      <title>Mehar Pro Downloader</title>
      <style>
        /* Sleek Premium Theme Variables */
        :root {
            --bg-gradient: linear-gradient(135deg, #f0f4f8, #d9e2ec);
            --glass-bg: rgba(255, 255, 255, 0.9);
            --glass-border: rgba(255, 255, 255, 1);
            --text-main: #1e293b;
            --text-muted: #64748b;
            --input-bg: #ffffff;
            --box-shadow: 0 8px 30px rgba(0, 0, 0, 0.04);
            --accent-color: #0ea5e9;
            --btn-gradient: linear-gradient(135deg, #0ea5e9, #2563eb);
            --status-bg: #f8fafc;
            --gold: #d4af37;
        }

        /* Pure Black Dark Theme */
        [data-theme="dark"] {
            --bg-gradient: linear-gradient(135deg, #000000, #111111);
            --glass-bg: rgba(20, 20, 20, 0.85);
            --glass-border: rgba(255, 255, 255, 0.1);
            --text-main: #f0f0f0;
            --text-muted: #aaaaaa;
            --input-bg: rgba(10, 10, 10, 0.8);
            --box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.8);
            --accent-color: #00f3ff;
            --btn-gradient: linear-gradient(135deg, #00c6ff, #0072ff);
            --status-bg: rgba(15, 15, 15, 0.9);
        }

        @keyframes slideDown { from { opacity: 0; transform: translateY(-15px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes fadeIn { from { opacity: 0; transform: scale(0.98); } to { opacity: 1; transform: scale(1); } }
        
        body { 
            margin: 0; font-family: 'Inter', 'Segoe UI', sans-serif; 
            background: var(--bg-gradient); background-attachment: fixed; 
            color: var(--text-main); padding: 15px; transition: background 0.4s ease;
        }
        
        /* Minimalist Header */
        .header { 
            display: flex; justify-content: space-between; align-items: center; 
            background: var(--glass-bg); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
            border: 1px solid var(--glass-border); border-radius: 16px; padding: 16px 20px; 
            margin-bottom: 25px; box-shadow: var(--box-shadow); animation: slideDown 0.5s ease-out;
        }
        .header-title-container { display: flex; flex-direction: column; }
        .header h2 { margin: 0; font-size: 24px; font-weight: 900; color: var(--text-main); letter-spacing: -0.5px; }
        .header-subtitle { font-size: 10px; color: var(--gold); margin-top: 0px; letter-spacing: 2px; text-transform: uppercase; font-weight: 700; }
        
        .header-actions { display: flex; gap: 12px; align-items: center; }
        .owner-tag { 
            font-size: 10px; font-weight: 700; background: linear-gradient(135deg, #111, #333); 
            color: var(--gold); padding: 6px 12px; border-radius: 20px; 
            border: 1px solid var(--glass-border);
        }
        .gear-btn { 
            background: var(--input-bg); border: 1px solid var(--glass-border); color: var(--accent-color);
            width: 36px; height: 36px; border-radius: 50%; display: flex; justify-content: center; align-items: center;
            font-size: 18px; cursor: pointer; box-shadow: var(--box-shadow); transition: all 0.3s;
        }
        .gear-btn:hover { transform: rotate(45deg); filter: brightness(1.2); }

        /* Sleek Tabs */
        .tabs { display: flex; flex-wrap: wrap; gap: 6px; justify-content: center; margin-bottom: 25px; }
        .tab-btn { 
            background: var(--glass-bg); border: 1px solid var(--glass-border); 
            color: var(--text-muted); padding: 10px 16px; border-radius: 12px; cursor: pointer; 
            font-weight: 600; transition: all 0.3s; flex: 1; min-width: 100px; text-align: center; font-size: 13px;
        }
        .tab-btn:hover { color: var(--text-main); background: rgba(255,255,255,0.2); }
        .tab-btn.active { 
            background: linear-gradient(135deg, #111, #222); color: var(--gold);
            border-color: #111; box-shadow: var(--box-shadow); font-weight: 700;
        }
        [data-theme="dark"] .tab-btn.active { background: linear-gradient(135deg, #333, #555); color: #fff; border-color: #555;}
        
        /* Glass Content Containers */
        .tab-content { 
            display: none; background: var(--glass-bg); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
            border: 1px solid var(--glass-border); border-radius: 20px; padding: 25px; 
            box-shadow: var(--box-shadow); animation: fadeIn 0.4s ease-out; 
        }
        .tab-content.active { display: block; }
        
        .tab-content h3 { color: var(--text-main); margin-top:0; margin-bottom: 4px; font-size: 18px; font-weight: 700;}
        .tab-subtitle { font-size: 11px; color: var(--text-muted); font-weight: 500; margin-bottom: 20px; padding-bottom: 12px; border-bottom: 1px solid var(--glass-border);}

        /* Form Elements */
        textarea { 
            width: 100%; min-height: 100px; border-radius: 12px; border: 1px solid var(--glass-border); 
            background: var(--input-bg); color: var(--text-main); padding: 16px; box-sizing: border-box; margin: 10px 0; 
            font-family: monospace; font-size: 12px; transition: all 0.3s; box-shadow: inset 0 2px 4px rgba(0,0,0,0.02);
        }
        textarea:focus, input:focus, select:focus { border-color: var(--accent-color); outline: none; }
        
        .controls { display: flex; gap: 10px; margin-bottom: 15px; flex-direction: column; }
        .path-container { display: flex; width: 100%; }
        .path-container input { 
            flex: 1; padding: 14px 16px; border-radius: 12px; border: 1px solid var(--glass-border); 
            background: var(--input-bg); color: var(--text-main); min-width: 0; font-weight: 500; font-size: 13px;
        }
        select { 
            width: 100%; padding: 14px 16px; border-radius: 12px; background: var(--input-bg); 
            color: var(--text-main); border: 1px solid var(--glass-border); cursor: pointer; font-weight: 600; font-size: 13px;
        }
        
        /* Status Box */
        .status-box { 
            background: var(--status-bg); padding: 16px; border-radius: 12px; margin: 20px 0 15px 0; 
            border-left: 4px solid var(--accent-color); word-wrap: break-word; font-size: 13px;
        }
        .live-progress { color: var(--accent-color); font-weight: 700; margin-top: 6px; font-size: 13px; }

        /* Buttons */
        .action-btns { display: flex; flex-wrap: wrap; gap: 10px; }
        button.action { 
            flex: 1; min-width: 130px; border: 0; padding: 14px; border-radius: 12px; cursor: pointer; color: white; 
            font-weight: 700; transition: all 0.2s; text-transform: uppercase; font-size: 11px; letter-spacing: 1px;
        }
        button.action:hover { transform: translateY(-2px); filter: brightness(1.1); box-shadow: 0 6px 15px rgba(0,0,0,0.1); }
        
        .btn-scan { background: #475569; }
        .btn-import { background: linear-gradient(135deg, var(--gold), #b8860b); color: #fff; }
        .btn-clear { background: #94a3b8; }
        .btn-download { background: var(--btn-gradient); }
        .btn-yt { background: #f43f5e; }
        .btn-stop { background: #ef4444; display: none; width: 100%; margin-bottom: 15px; font-size: 12px;}
        
        /* Download Link Style */
        .download-link { display: inline-block; margin-top: 10px; padding: 10px 20px; background: #22c55e; color: white; border-radius: 8px; text-decoration: none; font-weight: 800; text-align:center; width:calc(100% - 40px); }
        .download-link:hover { background: #16a34a; }

        /* Help Modal */
        .modal-overlay {
            display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.6); backdrop-filter: blur(5px);
            z-index: 1000; justify-content: center; align-items: center; opacity: 0; transition: opacity 0.3s;
        }
        .modal-content {
            background: var(--glass-bg); padding: 25px; border-radius: 20px;
            max-width: 85%; max-height: 80vh; overflow-y: auto; color: var(--text-main);
            border: 1px solid var(--glass-border); box-shadow: 0 20px 50px rgba(0,0,0,0.2);
            transform: scale(0.95); transition: transform 0.3s;
        }
        .modal-content h3 { margin-top: 0; color: var(--accent-color); font-size: 18px;}
        
        /* Settings Toggle */
        .setting-item { display: flex; justify-content: space-between; align-items: center; margin: 15px 0; font-size: 13px;}
        .switch { position: relative; display: inline-block; width: 40px; height: 20px; }
        .switch input { opacity: 0; width: 0; height: 0; }
        .slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #94a3b8; transition: .4s; border-radius: 34px; }
        .slider:before { position: absolute; content: ""; height: 16px; width: 16px; left: 2px; bottom: 2px; background-color: white; transition: .4s; border-radius: 50%; }
        input:checked + .slider { background-color: var(--accent-color); }
        input:checked + .slider:before { transform: translateX(20px); }

        .footer { text-align: center; color: var(--text-muted); margin-top: 30px; font-size: 11px; font-weight: 500;}
        .history-item { background: var(--input-bg); padding: 10px; border-radius: 8px; margin-bottom: 8px; font-size: 11px; border-left: 3px solid var(--accent-color); color: var(--text-main);}
      </style>
    </head>
    <body>

      <div class="header">
        <div class="header-title-container">
            <h2>Mehar Pro</h2>
            <span class="header-subtitle">DOWNLOADER</span>
        </div>
        <div class="header-actions">
            <span class="owner-tag">Owner: Adnan</span>
            <button class="gear-btn" onclick="openModal('settingsModal')" title="Settings">⚙️</button>
        </div>
      </div>

      <div class="tabs">
        <button class="tab-btn active" onclick="openTab(event, 'tab-tiktok')">📱 TikTok</button>
        <button class="tab-btn" onclick="openTab(event, 'tab-universal')">🌍 Universal</button>
        <button class="tab-btn" onclick="openTab(event, 'tab-yt')">✂️ YouTube AI</button>
        <button class="tab-btn" onclick="openTab(event, 'tab-mp3')">🎵 MP3</button>
        <button class="tab-btn" onclick="openTab(event, 'tab-thumbnail')">🖼️ Thumbnails</button>
        <button class="tab-btn" onclick="openTab(event, 'tab-img-convert')">🔄 Img Convert</button>
        <button class="tab-btn" onclick="openTab(event, 'tab-pdf')">📄 Img to PDF</button>
        <button class="tab-btn" onclick="openTab(event, 'tab-history')">🕒 History</button>
      </div>

      <div id="tab-tiktok" class="tab-content active">
        <h3>TikTok Batch Downloader</h3>
        <div class="tab-subtitle">Cloud Extraction Engine</div>
        <textarea id="urls" placeholder="Paste URLs here or Import TXT..."></textarea>
        <div class="controls">
          <select id="quality"><option value="worst">Fast (Lowest MP4)</option><option value="best" selected>Original (Best MP4)</option><option value="audio_only">🎵 Audio (MP3)</option></select>
          <select id="saveMode"><option value="zip">Save: Single ZIP (Recommended)</option></select>
        </div>
        <div class="status-box"><div id="status1">Ready.</div><div id="prog1" class="live-progress"></div></div>
        <button class="action btn-stop" id="stopBtn1" onclick="stopDownload()">🛑 Force Stop</button>
        <div class="action-btns">
          <button class="action btn-scan" onclick="scan()">🔍 Scan</button>
          <button class="action btn-import" onclick="triggerFileImport('urls')">📁 Import TXT</button>
          <button class="action btn-clear" onclick="clearUrls()">🗑️ Clear</button>
          <button class="action btn-download" id="downloadBtn" onclick="download('video')">🚀 Download</button>
        </div>
        <div id="grid" style="margin-top:15px; display:grid; gap:8px;"></div>
      </div>

      <div id="tab-universal" class="tab-content">
        <h3>Universal Downloader</h3>
        <div class="tab-subtitle">Any Platform Video/Audio Extractor</div>
        <div class="controls"><input type="text" id="uniUrl" placeholder="Paste single link here..."></div>
        <div class="controls">
          <select id="uniType"><option value="video">🎥 Video Download</option><option value="audio">🎵 Audio (MP3)</option></select>
          <select id="uniQuality"><option value="best">Highest Quality</option><option value="worst">Low Quality / Fast</option></select>
        </div>
        <div class="status-box"><div id="status2">Ready.</div><div id="prog2" class="live-progress"></div></div>
        <button class="action btn-stop" id="stopBtn2" onclick="stopDownload()">🛑 Force Stop</button>
        <button class="action btn-download" id="uniBtn" onclick="startUniversal()" style="width: 100%;">🚀 Download Now</button>
      </div>

      <div id="tab-yt" class="tab-content">
        <h3 style="color: #ff416c;">YouTube AI Shorts</h3>
        <div class="tab-subtitle">Exact Frame-Accurate Slicing & Auto-Merge</div>
        <textarea id="ytDoc" placeholder="Paste AI Document text with exact timestamps here..."></textarea>
        <div class="controls">
          <select id="ytQuality"><option value="720p">📺 HD 720p</option><option value="1080p" selected>🌟 Full HD 1080p</option></select>
        </div>
        <div class="status-box"><div id="status3">Ready.</div><div id="prog3" class="live-progress"></div></div>
        <button class="action btn-stop" id="stopBtn3" onclick="stopDownload()">🛑 Force Stop</button>
        <div class="action-btns">
            <button class="action btn-import" onclick="triggerFileImport('ytDoc')">📁 Import Doc</button>
            <button class="action btn-yt" id="ytBtn" onclick="startYtShorts()">🚀 Fast Extract</button>
        </div>
      </div>

      <div id="tab-mp3" class="tab-content">
        <h3>Offline MP3 Converter</h3>
        <div class="tab-subtitle">Upload Video Files to Convert to MP3</div>
        <div class="controls" style="margin-top: 8px;">
          <input type="file" id="mp3UploadFiles" multiple accept="video/*,audio/*" style="display:none;" onchange="handleMp3UploadSelect(event)">
          <div class="action-btns" style="width: 100%;">
              <button class="action btn-import" onclick="document.getElementById('mp3UploadFiles').click()">📁 Select Files</button>
              <button class="action btn-download" onclick="uploadAndConvertMp3()">⚡ Convert Files</button>
          </div>
          <div id="selectedFilesText" style="font-size:11px; color:var(--text-muted); margin-top:5px;">No files selected.</div>
        </div>
        <div class="status-box"><div id="status4">Ready.</div></div>
      </div>

      <div id="tab-thumbnail" class="tab-content">
        <h3>Thumbnail Grabber</h3>
        <div class="tab-subtitle">Download max-res YouTube covers instantly.</div>
        <div class="controls"><input type="text" id="thumbUrl" placeholder="https://youtube.com/watch?..."></div>
        <button class="action btn-download" onclick="getThumb()" style="width:100%;">🖼️ Fetch HD Thumbnail</button>
        <div class="status-box" style="margin-top:20px; display:none;" id="thumbResult"></div>
      </div>

      <div id="tab-img-convert" class="tab-content">
        <h3>Image Format Converter</h3>
        <div class="tab-subtitle">Convert images to PNG, JPG, WEBP.</div>
        <div class="controls">
          <input type="file" id="imgUploads" multiple accept="image/*" style="display:none;" onchange="handleImgSelect(event)">
          <div class="action-btns" style="width: 100%;">
              <button class="action btn-import" onclick="document.getElementById('imgUploads').click()">📸 Select Images</button>
          </div>
          <div id="imgFilesText" style="font-size:11px; color:var(--text-muted); margin-top:5px; margin-bottom:10px;">No images selected.</div>
          <label style="font-size:12px; font-weight:bold;">Convert To:</label>
          <select id="imgTargetFormat"><option value="PNG">PNG</option><option value="JPEG">JPG / JPEG</option><option value="WEBP">WEBP</option></select>
        </div>
        <button class="action btn-download" onclick="convertImages()" style="width:100%;">🔄 Convert Now</button>
        <div class="status-box"><div id="statusImg">Ready.</div></div>
      </div>

      <div id="tab-pdf" class="tab-content">
        <h3>Image to PDF</h3>
        <div class="tab-subtitle">Combine multiple images into one PDF document.</div>
        <div class="controls">
          <input type="file" id="pdfUploads" multiple accept="image/*" style="display:none;" onchange="handlePdfSelect(event)">
          <div class="action-btns" style="width: 100%;">
              <button class="action btn-import" onclick="document.getElementById('pdfUploads').click()">📄 Select Images (Order matters)</button>
          </div>
          <div id="pdfFilesText" style="font-size:11px; color:var(--text-muted); margin-top:5px; margin-bottom:10px;">No images selected.</div>
        </div>
        <button class="action btn-download" onclick="imagesToPdf()" style="width:100%;">📑 Generate PDF</button>
        <div class="status-box"><div id="statusPdf">Ready.</div></div>
      </div>

      <div id="tab-history" class="tab-content">
        <h3>Recent Downloads</h3>
        <div class="tab-subtitle">Your latest successful tasks</div>
        <div id="historyList" style="max-height: 300px; overflow-y: auto;">
            <div class="history-item">No history yet.</div>
        </div>
        <button class="action btn-clear" onclick="clearHistory()" style="margin-top:15px; width:100%;">🗑️ Clear History</button>
      </div>

      <div id="settingsModal" class="modal-overlay">
          <div class="modal-content">
              <h3>⚙️ Premium Settings</h3>
              <div class="setting-item">
                  <span><b>Dark Mode</b><br><span style="font-size:10px; color:var(--text-muted);">Toggle interface theme</span></span>
                  <label class="switch"><input type="checkbox" id="themeToggle" onchange="applyThemeToggle()"><span class="slider"></span></label>
              </div>
              <div class="setting-item">
                  <span><b>Auto-Clear Inputs</b><br><span style="font-size:10px; color:var(--text-muted);">Clear links/text after success</span></span>
                  <label class="switch"><input type="checkbox" id="autoClearToggle" checked><span class="slider"></span></label>
              </div>
              <div class="action-btns" style="margin-top: 25px;">
                  <button class="action btn-clear" onclick="closeModal('settingsModal')">Close</button>
              </div>
          </div>
      </div>

      <input type="file" id="fileInput" accept=".txt" style="display:none;" onchange="handleFileSelect(event)">

      <div class="footer">
        Mehar Pro Downloader | Support: +92 343 6873471
      </div>

      <script>
        let currentTaskId = "";
        let results = [];
        let progressInterval = null;
        let activeTargetId = 'urls';

        function openTab(evt, tabId) {
            document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
            document.getElementById(tabId).classList.add('active');
            evt.currentTarget.classList.add('active');
        }

        function openModal(id) { document.getElementById(id).style.display = 'flex'; setTimeout(()=> { document.getElementById(id).style.opacity = '1'; }, 10); }
        function closeModal(id) { document.getElementById(id).style.opacity = '0'; setTimeout(()=> document.getElementById(id).style.display = 'none', 300); }

        function applyThemeToggle() {
            const html = document.documentElement;
            if(document.getElementById('themeToggle').checked) { html.setAttribute('data-theme', 'dark'); localStorage.setItem('mehar_theme', 'dark'); } 
            else { html.setAttribute('data-theme', 'light'); localStorage.setItem('mehar_theme', 'light'); }
        }
        window.onload = () => {
            let theme = localStorage.getItem('mehar_theme');
            if(theme === 'dark') { document.documentElement.setAttribute('data-theme', 'dark'); document.getElementById('themeToggle').checked = true; }
        }

        function addHistory(task) {
            let hist = JSON.parse(localStorage.getItem('mehar_hist') || '[]');
            let date = new Date(); let min = date.getMinutes() < 10 ? '0'+date.getMinutes() : date.getMinutes();
            hist.unshift(`[${date.getHours()}:${min}] ${task}`);
            if(hist.length > 20) hist.pop();
            localStorage.setItem('mehar_hist', JSON.stringify(hist)); renderHistory();
        }
        function renderHistory() {
            let hist = JSON.parse(localStorage.getItem('mehar_hist') || '[]');
            let div = document.getElementById('historyList');
            if(hist.length === 0) { div.innerHTML = '<div class="history-item">No history yet.</div>'; return; }
            div.innerHTML = hist.map(h => `<div class="history-item">${h}</div>`).join('');
        }
        function clearHistory() { localStorage.removeItem('mehar_hist'); renderHistory(); }
        renderHistory();

        function triggerFileImport(targetId) { activeTargetId = targetId; document.getElementById('fileInput').click(); }
        function handleFileSelect(event) {
            const file = event.target.files[0]; if (!file) return;
            const reader = new FileReader();
            reader.onload = function(e) {
                const area = document.getElementById(activeTargetId);
                if(activeTargetId === 'urls') area.value = [...new Set(e.target.result.split('\\n').map(l => l.trim()).filter(Boolean))].join('\\n');
                else area.value = e.target.result;
            };
            reader.readAsText(file); event.target.value = ''; 
        }

        async function stopDownload() { await fetch('/stop/'+currentTaskId); }

        async function poll(tid, sid, bid, stp){
            let inter = setInterval(async ()=>{
                let r = await fetch('/progress/'+tid); let d = await r.json();
                if(d.is_active){ document.getElementById(sid).innerText = d.status; document.getElementById(bid).style.display='none'; if(stp)document.getElementById(stp).style.display='block'; }
                else { clearInterval(inter); document.getElementById(bid).style.display='inline-block'; if(stp)document.getElementById(stp).style.display='none'; }
            }, 1500);
        }

        async function scan() {
          const rawUrls = document.getElementById('urls').value.split('\\n').map(s => s.trim()).filter(Boolean);
          if(rawUrls.length === 0) return;
          const uniqueUrls = [...new Set(rawUrls)]; document.getElementById('urls').value = uniqueUrls.join('\\n'); 
          document.getElementById('status1').innerText = 'Scanning...';
          const res = await fetch('/scan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ urls: uniqueUrls, count: 5000 }) });
          const data = await res.json(); results = data.results || [];
          const grid = document.getElementById('grid'); grid.innerHTML = '';
          results.forEach((v, i) => { grid.innerHTML += `<div style="background:var(--input-bg); padding:10px; border-radius:8px; margin-bottom:5px;"><label style="color:var(--gold); font-weight:bold;"><input type="checkbox" checked id="c${i}"> Select</label><div style="font-size:11px; word-break:break-all; opacity:0.8; margin-top:5px;">${v.url}</div></div>`; });
          document.getElementById('status1').innerText = `Scan complete. ${results.length} URLs ready.`;
        }
        function clearUrls() { document.getElementById('urls').value = ''; document.getElementById('grid').innerHTML = ''; results = []; }

        async function download(mode) {
          const selected = []; results.forEach((v, i) => { const el = document.getElementById('c'+i); if(el && el.checked) selected.push(v.url); });
          if(selected.length === 0) return;
          currentTaskId = "tk_"+Date.now(); document.getElementById('status1').innerText = 'Engine Started...';
          poll(currentTaskId, 'prog1', 'downloadBtn', 'stopBtn1');
          
          try {
            const res = await fetch('/download', {
              method: 'POST', headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ selectedUrls: selected, quality: document.getElementById('quality').value, saveMode: 'zip', task_id: currentTaskId })
            });
            const data = await res.json();
            if(data.status === "error") document.getElementById('status1').innerHTML = `❌ Error: ${data.error}`;
            else { 
                document.getElementById('status1').innerHTML = `✅ Complete! <br><a href="/files/${data.location}" class="download-link" download>📥 DOWNLOAD ZIP</a>`;
                addHistory(`TikTok Batch: ${selected.length} items`);
                if(document.getElementById('autoClearToggle').checked) clearUrls();
            }
          } catch(err) {}
        }

        async function startUniversal() {
            const url = document.getElementById('uniUrl').value.trim(); if(!url) return;
            currentTaskId = "un_"+Date.now(); document.getElementById('status2').innerText = 'Starting Engine...';
            poll(currentTaskId, 'prog2', 'uniBtn', 'stopBtn2');
            try {
                const res = await fetch('/universal-download', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url: url, formatType: document.getElementById('uniType').value, quality: document.getElementById('uniQuality').value, task_id: currentTaskId })
                });
                const data = await res.json();
                if(data.status === "error") document.getElementById('status2').innerHTML = `❌ Error`;
                else { 
                    document.getElementById('status2').innerHTML = `✅ Complete! <br><a href="/files/${data.location}" class="download-link" download>📥 DOWNLOAD FILE</a>`;
                    addHistory("Universal Extract");
                    if(document.getElementById('autoClearToggle').checked) document.getElementById('uniUrl').value = '';
                }
            } catch(e) {}
        }

        async function startYtShorts() {
            const docText = document.getElementById('ytDoc').value.trim(); if(!docText) return;
            currentTaskId = "yt_"+Date.now(); document.getElementById('status3').innerText = 'Analyzing...';
            poll(currentTaskId, 'prog3', 'ytBtn', 'stopBtn3');
            try {
                const res = await fetch('/process-yt-document', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ document_text: docText, mode: 'zip', quality: document.getElementById('ytQuality').value, task_id: currentTaskId })
                });
                const data = await res.json();
                if(data.status === "error") document.getElementById('status3').innerHTML = `❌ Error: ${data.message}`;
                else { 
                    document.getElementById('status3').innerHTML = `✅ Extracted! <br><a href="/files/${data.location}" class="download-link" download>📥 DOWNLOAD ZIP</a>`;
                    addHistory("YouTube AI Shorts");
                    if(document.getElementById('autoClearToggle').checked) document.getElementById('ytDoc').value = '';
                }
            } catch(e) {}
        }

        function getThumb() {
            let url = document.getElementById('thumbUrl').value;
            let match = url.match(/(?:youtu\.be\\/|youtube\.com\\/(?:[^\\/]+\\/.+\\/|(?:v|e(?:mbed)?)\\/|.*[?&]v=)|youtu\.be\\/)([^"&?\\/\\s]{11})/);
            let resBox = document.getElementById('thumbResult');
            if(match && match[1]) {
                let imgUrl = `https://img.youtube.com/vi/${match[1]}/maxresdefault.jpg`;
                resBox.style.display = 'block';
                resBox.innerHTML = `✅ Found HD Cover:<br><br><img src="${imgUrl}" style="width:100%; border-radius:8px; margin-bottom:10px;"><a href="${imgUrl}" target="_blank" class="download-link">📥 OPEN FULL IMAGE</a>`;
                addHistory("Thumbnail Fetched");
            } else { alert("Please paste a valid YouTube link."); }
        }

        function handleMp3UploadSelect(event) {
            const files = event.target.files;
            document.getElementById('selectedFilesText').innerText = files.length > 0 ? `${files.length} file(s) selected.` : 'No files selected.';
        }
        async function uploadAndConvertMp3() {
            const fileInput = document.getElementById('mp3UploadFiles'); const statusBox = document.getElementById('status4');
            if (!fileInput.files.length) return;
            statusBox.innerHTML = "Uploading & Converting... ⏳";
            const formData = new FormData(); for (const file of fileInput.files) formData.append('files', file);
            try {
                const res = await fetch('/convert-mp3-upload', { method: 'POST', body: formData });
                const data = await res.json();
                if(data.status === "error") statusBox.innerHTML = `❌ Error`;
                else {
                    statusBox.innerHTML = `✅ Complete! <br><a href="/files/${data.location}" class="download-link" download>📥 DOWNLOAD MP3 ZIP</a>`;
                    addHistory("MP3 Files Converted");
                }
                fileInput.value = ''; document.getElementById('selectedFilesText').innerText = 'No files selected.';
            } catch(e) {}
        }

        function handleImgSelect(event) {
            const files = event.target.files;
            document.getElementById('imgFilesText').innerText = files.length > 0 ? `${files.length} image(s) selected.` : 'No images selected.';
        }
        async function convertImages() {
            const fileInput = document.getElementById('imgUploads'); const statusBox = document.getElementById('statusImg');
            if (!fileInput.files.length) return;
            statusBox.innerHTML = "Converting Images... ⏳";
            const formData = new FormData();
            for (const file of fileInput.files) formData.append('files', file);
            formData.append('target_format', document.getElementById('imgTargetFormat').value);
            try {
                const res = await fetch('/convert-image-format', { method: 'POST', body: formData });
                const data = await res.json();
                if(data.status==="error") statusBox.innerHTML = `❌ Error: ${data.message}`;
                else {
                    statusBox.innerHTML = `✅ Converted! <br><a href="/files/${data.location}" class="download-link" download>📥 DOWNLOAD IMAGES ZIP</a>`;
                    addHistory("Image Format Converted");
                }
                fileInput.value = ''; document.getElementById('imgFilesText').innerText = 'No images selected.';
            } catch(e) { statusBox.innerHTML = `❌ Error`; }
        }

        function handlePdfSelect(event) {
            const files = event.target.files;
            document.getElementById('pdfFilesText').innerText = files.length > 0 ? `${files.length} image(s) selected.` : 'No images selected.';
        }
        async function imagesToPdf() {
            const fileInput = document.getElementById('pdfUploads'); const statusBox = document.getElementById('statusPdf');
            if (!fileInput.files.length) return;
            statusBox.innerHTML = "Generating PDF... ⏳";
            const formData = new FormData();
            for (const file of fileInput.files) formData.append('files', file);
            try {
                const res = await fetch('/images-to-pdf', { method: 'POST', body: formData });
                const data = await res.json();
                if(data.status==="error") statusBox.innerHTML = `❌ Error: ${data.message}`;
                else {
                    statusBox.innerHTML = `✅ PDF Generated! <br><a href="/files/${data.location}" class="download-link" download>📥 DOWNLOAD PDF</a>`;
                    addHistory("Images merged to PDF");
                }
                fileInput.value = ''; document.getElementById('pdfFilesText').innerText = 'No images selected.';
            } catch(e) { statusBox.innerHTML = `❌ Error`; }
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
            if temp_file.exists(): temp_file.unlink()
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

