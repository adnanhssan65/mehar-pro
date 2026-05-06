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
progress_state = {"is_active": False, "total": 0, "completed": 0, "status": "Idle"}
cancel_download = False 

class ScanRequest(BaseModel): urls: List[str]; count: int = 5000
class DownloadRequest(BaseModel): selectedUrls: List[str]; folderPath: str; quality: str; saveMode: str
class ConvertRequest(BaseModel): folderPath: str; singleFilePath: Optional[str] = None
class UniversalRequest(BaseModel): url: str; folderPath: str; formatType: str; quality: str
class YTDocRequest(BaseModel): document_text: str; save_path: str; mode: str; quality: str

def scan_media(path_to_scan: str):
    pass # Disabled for Cloud (No Termux needed)

# PUBLIC CLOUD STORAGE PATH
BASE_DIR = Path("./downloads")
BASE_DIR.mkdir(parents=True, exist_ok=True)
if not (BASE_DIR / "temp").exists(): (BASE_DIR / "temp").mkdir()

# Serve files to internet
app.mount("/files", StaticFiles(directory=str(BASE_DIR)), name="files")

@app.get("/health")
def health(): return {"ok": True, "server": "running"}

@app.get("/progress")
def get_progress(): return JSONResponse(progress_state)

@app.get("/stop")
def stop_download():
    global cancel_download, progress_state
    cancel_download = True
    progress_state["status"] = "Stopping Engine... Please wait."
    return {"status": "cancelled"}

@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <!doctype html>
    <html lang="en" data-theme="light">
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=0" />
      <title>Mehar Pro Dashboard</title>
      <style>
        /* Sleek Premium Public SaaS Theme */
        :root {
            --bg-body: #f8fafc;
            --bg-panel: #ffffff;
            --border-color: #e2e8f0;
            --text-main: #0f172a;
            --text-muted: #64748b;
            --accent-primary: #3b82f6;
            --shadow-sm: 0 1px 3px rgba(0,0,0,0.05);
            --shadow-md: 0 4px 6px -1px rgba(0,0,0,0.1);
            --shadow-lg: 0 10px 15px -3px rgba(0,0,0,0.1);
            --input-bg: #f1f5f9;
        }

        /* PURE BLACK DARK MODE (Fixed Blue Issue) */
        [data-theme="dark"] {
            --bg-body: #000000;
            --bg-panel: #111111;
            --border-color: #222222;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --accent-primary: #38bdf8;
            --shadow-sm: 0 1px 3px rgba(0,0,0,0.3);
            --shadow-md: 0 4px 6px -1px rgba(0,0,0,0.4);
            --shadow-lg: 0 10px 25px -3px rgba(0,0,0,0.5);
            --input-bg: #1a1a1a;
        }

        @keyframes slideDown { from { opacity: 0; transform: translateY(-15px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes fadeIn { from { opacity: 0; transform: scale(0.98); } to { opacity: 1; transform: scale(1); } }
        
        body { 
            margin: 0; font-family: 'Inter', 'Segoe UI', sans-serif; 
            background: var(--bg-body); color: var(--text-main); 
            padding: 20px; transition: background 0.3s ease;
            padding-bottom: 80px;
        }
        
        /* Header */
        .header { 
            display: flex; justify-content: space-between; align-items: center; 
            margin-bottom: 30px; padding-bottom: 20px; border-bottom: 1px solid var(--border-color);
        }
        .header-brand { display: flex; flex-direction: column; }
        .header h1 { margin: 0; font-size: 26px; font-weight: 900; letter-spacing: -0.5px; color: var(--text-main); }
        .header-sub { font-size: 11px; color: var(--text-muted); font-weight: 600; letter-spacing: 1px; text-transform: uppercase;}
        
        .theme-btn { 
            background: var(--bg-panel); border: 1px solid var(--border-color); color: var(--text-main);
            width: 40px; height: 40px; border-radius: 12px; font-size: 18px; cursor: pointer; 
            box-shadow: var(--shadow-sm); transition: all 0.2s; display: flex; justify-content: center; align-items: center;
        }
        .theme-btn:hover { transform: scale(1.05); box-shadow: var(--shadow-md); color: var(--accent-primary); }

        /* Dashboard Grid */
        .dashboard-grid { 
            display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); 
            gap: 15px; animation: fadeIn 0.4s ease-out;
        }
        
        .tool-card {
            background: var(--bg-panel); border: 1px solid var(--border-color); border-radius: 16px;
            padding: 20px 10px; text-align: center; cursor: pointer; transition: all 0.3s;
            box-shadow: var(--shadow-sm); display: flex; flex-direction: column; align-items: center; gap: 8px;
        }
        .tool-card:hover { transform: translateY(-4px); box-shadow: var(--shadow-lg); border-color: var(--accent-primary); }
        .tool-icon { font-size: 32px; margin-bottom: 5px; }
        .tool-title { font-size: 13px; font-weight: 700; color: var(--text-main); }
        .tool-desc { font-size: 10px; color: var(--text-muted); font-weight: 500; }

        /* Tool View (Inner Page) */
        .tool-view { display: none; animation: fadeIn 0.3s ease-out; }
        .tool-view.active { display: block; }
        
        .back-nav { 
            display: inline-flex; align-items: center; gap: 8px; font-size: 12px; font-weight: 700; 
            color: var(--text-main); cursor: pointer; margin-bottom: 20px; transition: 0.2s;
            background: var(--bg-panel); padding: 10px 15px; border-radius: 12px; border: 1px solid var(--border-color);
            box-shadow: var(--shadow-sm);
        }
        .back-nav:hover { color: var(--accent-primary); border-color: var(--accent-primary); }

        .tool-header { margin-bottom: 20px; padding-left: 5px;}
        .tool-header h2 { margin: 0 0 5px 0; font-size: 20px; color: var(--text-main); }
        .tool-header p { margin: 0; font-size: 12px; color: var(--text-muted); font-weight: 500;}

        .tool-container {
            background: var(--bg-panel); border: 1px solid var(--border-color);
            border-radius: 20px; padding: 20px; box-shadow: var(--shadow-md);
        }

        /* Inputs & Controls */
        textarea, input[type="text"] { 
            width: 100%; border-radius: 12px; border: 1px solid var(--border-color); 
            background: var(--input-bg); color: var(--text-main); padding: 15px; box-sizing: border-box; 
            font-size: 12px; transition: all 0.2s; font-family: inherit; font-weight: 500;
        }
        textarea { min-height: 120px; resize: vertical; }
        textarea:focus, input:focus, select:focus { border-color: var(--accent-primary); outline: none; }
        
        .input-group { margin-bottom: 15px; }
        .input-group label { display: block; font-size: 12px; font-weight: 700; margin-bottom: 8px; color: var(--text-main); }
        
        select { 
            width: 100%; padding: 14px; border-radius: 12px; background: var(--input-bg); 
            color: var(--text-main); border: 1px solid var(--border-color); cursor: pointer; font-weight: 600; font-size: 12px;
        }
        
        .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 15px;}
        @media (max-width: 500px) { .grid-2 { grid-template-columns: 1fr; } }

        /* Buttons */
        .btn-group { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 15px; }
        button.btn { 
            flex: 1; min-width: 120px; border: none; padding: 14px; border-radius: 12px; cursor: pointer; 
            font-weight: 700; transition: all 0.2s; font-size: 12px; letter-spacing: 0.5px;
        }
        button.btn:hover { transform: translateY(-2px); box-shadow: var(--shadow-md); filter: brightness(1.1); }
        button.btn:active { transform: translateY(0); }
        
        .btn-primary { background: var(--accent-primary); color: white; }
        .btn-secondary { background: var(--input-bg); color: var(--text-main); border: 1px solid var(--border-color); }
        .btn-danger { background: #ef4444; color: white; display: none; width: 100%; margin-top: 15px;}
        .download-link-btn { display: inline-block; background: #22c55e; color: white; padding: 12px 20px; border-radius: 8px; text-decoration: none; font-weight: bold; margin-top: 10px; text-align: center; width: calc(100% - 40px); }

        /* Status & Toast */
        .status-box { 
            background: var(--input-bg); padding: 15px; border-radius: 12px; margin-top: 20px; 
            border-left: 4px solid var(--accent-primary); font-size: 12px; font-weight: 600;
            word-wrap: break-word;
        }
        .progress-text { color: var(--accent-primary); font-weight: 800; margin-top: 5px; font-size: 12px; }

        .toast {
            position: fixed; top: 20px; left: 50%; transform: translateX(-50%) translateY(-100px);
            background: var(--text-main); color: var(--bg-body); padding: 12px 24px; border-radius: 30px; 
            font-size: 12px; font-weight: 700; box-shadow: var(--shadow-lg); z-index: 9999; 
            opacity: 0; transition: all 0.4s;
        }
        .toast.show { transform: translateX(-50%) translateY(0); opacity: 1; }

        .file-upload-wrapper { border: 2px dashed var(--border-color); border-radius: 16px; padding: 25px 15px; text-align: center; cursor: pointer; transition: 0.3s; background: var(--input-bg); }
        .file-upload-wrapper:hover { border-color: var(--accent-primary); }
        .file-upload-wrapper p { margin: 10px 0 0 0; font-size: 12px; color: var(--text-muted); font-weight: 600; }
        
        .footer { text-align: center; color: var(--text-muted); margin-top: 40px; font-size: 11px; font-weight: 500;}
      </style>
    </head>
    <body>
      
      <div id="toast" class="toast">Action Completed!</div>

      <div class="header">
        <div class="header-brand">
            <h1>Mehar Pro.</h1>
            <span class="header-sub">Public Workspace</span>
        </div>
        <button class="theme-btn" onclick="toggleTheme()" title="Toggle Theme">🌓</button>
      </div>

      <div id="view-dashboard" class="dashboard-grid">
        <div class="tool-card" onclick="openTool('tool-tiktok')">
            <div class="tool-icon">📱</div>
            <div class="tool-title">TikTok Bulk</div>
            <div class="tool-desc">Batch download videos</div>
        </div>
        <div class="tool-card" onclick="openTool('tool-yt')">
            <div class="tool-icon">✂️</div>
            <div class="tool-title">AI Shorts</div>
            <div class="tool-desc">Specific time extraction</div>
        </div>
        <div class="tool-card" onclick="openTool('tool-universal')">
            <div class="tool-icon">🌍</div>
            <div class="tool-title">Universal</div>
            <div class="tool-desc">Any link downloader</div>
        </div>
        <div class="tool-card" onclick="openTool('tool-mp3')">
            <div class="tool-icon">🎵</div>
            <div class="tool-title">MP3 Audio</div>
            <div class="tool-desc">Convert files to MP3</div>
        </div>
        <div class="tool-card" onclick="openTool('tool-thumbnail')">
            <div class="tool-icon">🖼️</div>
            <div class="tool-title">Thumbnails</div>
            <div class="tool-desc">HD YouTube covers</div>
        </div>
        <div class="tool-card" onclick="openTool('tool-img-convert')">
            <div class="tool-icon">🔄</div>
            <div class="tool-title">Img Converter</div>
            <div class="tool-desc">PNG, JPG, WEBP formats</div>
        </div>
        <div class="tool-card" onclick="openTool('tool-pdf')">
            <div class="tool-icon">📄</div>
            <div class="tool-title">Image to PDF</div>
            <div class="tool-desc">Combine images into PDF</div>
        </div>
        <div class="tool-card" onclick="openTool('tool-settings')">
            <div class="tool-icon">⚙️</div>
            <div class="tool-title">Settings</div>
            <div class="tool-desc">Paths & History</div>
        </div>
      </div>

      <div id="tools-container">
          
          <div id="tool-tiktok" class="tool-view">
              <div class="back-nav" onclick="goHome()">🔙 Back to Home</div>
              <div class="tool-header"><h2>TikTok Bulk Downloader</h2><p>Paste multiple links to batch download.</p></div>
              <div class="tool-container">
                  <div class="input-group">
                      <textarea id="urls" placeholder="Paste links here..."></textarea>
                  </div>
                  <div class="grid-2">
                      <div class="input-group">
                          <label>Quality</label>
                          <select id="quality"><option value="worst">Fast (Low)</option><option value="best" selected>Original (HD)</option><option value="audio_only">Audio (MP3)</option></select>
                      </div>
                      <div class="input-group">
                          <label>Save Mode</label>
                          <select id="saveMode"><option value="separate">Separate Files</option><option value="zip">Single ZIP</option></select>
                      </div>
                  </div>
                  <div class="btn-group">
                      <button class="btn btn-secondary" onclick="triggerFileImport('urls')">📁 Import TXT</button>
                      <button class="btn btn-secondary" onclick="scan()">🔍 Scan URLs</button>
                      <button class="btn btn-primary" id="downloadBtn" onclick="download('video')">🚀 Download</button>
                  </div>
                  <button class="btn btn-danger" id="stopBtn1" onclick="stopDownload()">🛑 Force Stop</button>
                  <div class="status-box"><div id="status1">Ready.</div><div id="prog1" class="progress-text"></div></div>
                  <div id="grid" style="margin-top:15px; display:grid; gap:8px;"></div>
              </div>
          </div>

          <div id="tool-universal" class="tool-view">
              <div class="back-nav" onclick="goHome()">🔙 Back to Home</div>
              <div class="tool-header"><h2>Universal Downloader</h2><p>Extract media from almost any platform.</p></div>
              <div class="tool-container">
                  <div class="input-group">
                      <label>Media Link</label>
                      <input type="text" id="uniUrl" placeholder="https://...">
                  </div>
                  <div class="grid-2">
                      <div class="input-group">
                          <label>Format</label>
                          <select id="uniType"><option value="video">Video</option><option value="audio">Audio (MP3)</option></select>
                      </div>
                      <div class="input-group">
                          <label>Quality</label>
                          <select id="uniQuality"><option value="best">Best Quality</option><option value="worst">Fastest</option></select>
                      </div>
                  </div>
                  <div class="btn-group">
                      <button class="btn btn-primary" id="uniBtn" onclick="startUniversal()" style="width:100%;">🚀 Download Media</button>
                  </div>
                  <button class="btn btn-danger" id="stopBtn2" onclick="stopDownload()">🛑 Force Stop</button>
                  <div class="status-box"><div id="status2">Ready.</div><div id="prog2" class="progress-text"></div></div>
              </div>
          </div>

          <div id="tool-yt" class="tool-view">
              <div class="back-nav" onclick="goHome()">🔙 Back to Home</div>
              <div class="tool-header"><h2>YouTube AI Shorts</h2><p>Frame-accurate clipping and auto-merging.</p></div>
              <div class="tool-container">
                  <div class="input-group">
                      <label>AI Script / Prompt</label>
                      <textarea id="ytDoc" placeholder="Paste script with link and exact timestamps..."></textarea>
                  </div>
                  <div class="grid-2">
                      <div class="input-group">
                          <label>Video Quality</label>
                          <select id="ytQuality"><option value="720p">720p HD</option><option value="1080p" selected>1080p FHD</option></select>
                      </div>
                      <div class="input-group">
                          <label>Export Format</label>
                          <select id="ytSaveMode"><option value="folder">Normal Folder</option><option value="zip">ZIP Archive</option></select>
                      </div>
                  </div>
                  <div class="btn-group">
                      <button class="btn btn-secondary" onclick="triggerFileImport('ytDoc')">📄 Import Doc</button>
                      <button class="btn btn-primary" id="ytBtn" onclick="startYtShorts()">✂️ Extract & Merge</button>
                  </div>
                  <button class="btn btn-danger" id="stopBtn3" onclick="stopDownload()">🛑 Force Stop</button>
                  <div class="status-box"><div id="status3">Ready.</div><div id="prog3" class="progress-text"></div></div>
              </div>
          </div>

          <div id="tool-mp3" class="tool-view">
              <div class="back-nav" onclick="goHome()">🔙 Back to Home</div>
              <div class="tool-header"><h2>MP3 Converter</h2><p>Local high-speed audio extraction.</p></div>
              <div class="tool-container">
                  <div class="input-group">
                      <label>1. Convert Selected Files</label>
                      <input type="file" id="mp3UploadFiles" multiple accept="video/*,audio/*" style="display:none;" onchange="handleMp3UploadSelect(event)">
                      <div class="file-upload-wrapper" onclick="document.getElementById('mp3UploadFiles').click()">
                          <div style="font-size:24px;">📁</div>
                          <p id="selectedFilesText">Tap to select video files</p>
                      </div>
                      <button class="btn btn-primary" onclick="uploadAndConvertMp3()" style="width:100%; margin-top:10px;">⚡ Convert to MP3</button>
                  </div>
                  
                  <div style="margin: 20px 0; border-top: 1px dashed var(--border-color);"></div>
                  
                  <div class="input-group">
                      <label>2. Bulk Folder Path (Advanced)</label>
                      <input type="text" id="convFolder" value="/storage/emulated/0/Mehar Pro Downloader/TikTok">
                      <button class="btn btn-secondary" onclick="convertMp3BulkFolder()" style="width:100%; margin-top:10px;">🔄 Convert Directory</button>
                  </div>
                  <div class="status-box"><div id="status4">Ready.</div></div>
              </div>
          </div>

          <div id="tool-thumbnail" class="tool-view">
              <div class="back-nav" onclick="goHome()">🔙 Back to Home</div>
              <div class="tool-header"><h2>Thumbnail Grabber</h2><p>Download max-res YouTube covers instantly.</p></div>
              <div class="tool-container">
                  <div class="input-group">
                      <label>YouTube Link</label>
                      <input type="text" id="thumbUrl" placeholder="https://youtube.com/watch?...">
                  </div>
                  <button class="btn btn-primary" onclick="getThumb()" style="width:100%;">🖼️ Fetch HD Thumbnail</button>
                  <div class="status-box" style="margin-top:20px; display:none;" id="thumbResult"></div>
              </div>
          </div>

          <div id="tool-img-convert" class="tool-view">
              <div class="back-nav" onclick="goHome()">🔙 Back to Home</div>
              <div class="tool-header"><h2>Image Format Converter</h2><p>Convert images locally (PNG, JPG, WEBP).</p></div>
              <div class="tool-container">
                  <div class="input-group">
                      <label>Select Images</label>
                      <input type="file" id="imgUploads" multiple accept="image/*" style="display:none;" onchange="handleImgSelect(event)">
                      <div class="file-upload-wrapper" onclick="document.getElementById('imgUploads').click()">
                          <div style="font-size:24px;">📸</div>
                          <p id="imgFilesText">Tap to select images</p>
                      </div>
                  </div>
                  <div class="input-group">
                      <label>Convert To</label>
                      <select id="imgTargetFormat">
                          <option value="PNG">PNG</option>
                          <option value="JPEG">JPG / JPEG</option>
                          <option value="WEBP">WEBP</option>
                      </select>
                  </div>
                  <button class="btn btn-primary" onclick="convertImages()" style="width:100%;">🔄 Convert Now</button>
                  <div class="status-box"><div id="statusImg">Ready.</div></div>
              </div>
          </div>

          <div id="tool-pdf" class="tool-view">
              <div class="back-nav" onclick="goHome()">🔙 Back to Home</div>
              <div class="tool-header"><h2>Image to PDF</h2><p>Combine multiple images into one PDF document.</p></div>
              <div class="tool-container">
                  <div class="input-group">
                      <label>Select Images (Order matters)</label>
                      <input type="file" id="pdfUploads" multiple accept="image/*" style="display:none;" onchange="handlePdfSelect(event)">
                      <div class="file-upload-wrapper" onclick="document.getElementById('pdfUploads').click()">
                          <div style="font-size:24px;">📄</div>
                          <p id="pdfFilesText">Tap to select images</p>
                      </div>
                  </div>
                  <button class="btn btn-primary" onclick="imagesToPdf()" style="width:100%;">📑 Generate PDF</button>
                  <div class="status-box"><div id="statusPdf">Ready.</div></div>
              </div>
          </div>

          <div id="tool-settings" class="tool-view">
              <div class="back-nav" onclick="goHome()">🔙 Back to Home</div>
              <div class="tool-header"><h2>System Settings</h2><p>Configure paths and view recent activity.</p></div>
              
              <div class="tool-container" style="margin-bottom:20px;">
                  <div class="input-group">
                      <label>Master Default Path</label>
                      <input type="text" id="masterPathInput" value="./downloads">
                      <button class="btn btn-secondary" onclick="saveSettings()" style="margin-top:10px; width:100%;">💾 Save Path</button>
                  </div>
              </div>

              <div class="tool-container">
                  <h3 style="font-size:16px; margin-top:0;">🕒 Recent History</h3>
                  <div id="historyList" style="max-height: 200px; overflow-y: auto; font-size:12px; margin-bottom:15px;">
                      <div style="color:var(--text-muted);">No history yet.</div>
                  </div>
                  <button class="btn btn-secondary" onclick="clearHistory()" style="width:100%;">🗑️ Clear History</button>
              </div>
          </div>

      </div>

      <input type="file" id="fileInput" accept=".txt" style="display:none;" onchange="handleFileSelect(event)">

      <div class="footer">
        Mehar Pro Workspace<br>Support: +92 343 6873471
      </div>

      <script>
        let results = [];
        let progressInterval = null;
        let activeTargetId = '';

        // UI Routing
        function goHome() {
            document.querySelectorAll('.tool-view').forEach(el => el.classList.remove('active'));
            document.getElementById('view-dashboard').style.display = 'grid';
            window.scrollTo(0,0);
        }
        function openTool(id) {
            document.getElementById('view-dashboard').style.display = 'none';
            document.querySelectorAll('.tool-view').forEach(el => el.classList.remove('active'));
            document.getElementById(id).classList.add('active');
            window.scrollTo(0,0);
        }

        // Theme
        function toggleTheme() {
            const html = document.documentElement;
            const newTheme = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
            html.setAttribute('data-theme', newTheme);
            localStorage.setItem('mehar_theme', newTheme);
        }
        if(localStorage.getItem('mehar_theme') === 'dark') document.documentElement.setAttribute('data-theme', 'dark');

        // Toast
        function showToast(msg) {
            const t = document.getElementById('toast');
            t.innerHTML = `✅ ${msg}`; t.className = 'toast show';
            setTimeout(() => t.className = 'toast', 3000);
        }

        // Settings & History
        function saveSettings() {
            let base = document.getElementById('masterPathInput').value.trim();
            if(base.endsWith('/')) base = base.slice(0, -1);
            localStorage.setItem('mehar_base_path', base);
            document.getElementById('folderPath').value = base + "/TikTok";
            document.getElementById('uniFolderPath').value = base + "/Universal";
            document.getElementById('ytFolderPath').value = base + "/YT_Shorts";
            document.getElementById('convFolder').value = base + "/TikTok";
            showToast("Paths Updated");
        }
        window.onload = () => {
            let savedBase = localStorage.getItem('mehar_base_path');
            if(savedBase) {
                document.getElementById('masterPathInput').value = savedBase;
            }
        }

        function addHistory(task) {
            let hist = JSON.parse(localStorage.getItem('mehar_hist') || '[]');
            let date = new Date(); let min = date.getMinutes().toString().padStart(2, '0');
            hist.unshift(`[${date.getHours()}:${min}] ${task}`);
            if(hist.length > 20) hist.pop();
            localStorage.setItem('mehar_hist', JSON.stringify(hist)); renderHistory();
        }
        function renderHistory() {
            let hist = JSON.parse(localStorage.getItem('mehar_hist') || '[]');
            let div = document.getElementById('historyList');
            if(hist.length === 0) { div.innerHTML = '<div style="color:var(--text-muted);">No history yet.</div>'; return; }
            div.innerHTML = hist.map(h => `<div style="padding:8px 10px; background:var(--input-bg); border-radius:8px; margin-bottom:8px; border-left:3px solid var(--accent-primary);">${h}</div>`).join('');
        }
        function clearHistory() { localStorage.removeItem('mehar_hist'); renderHistory(); showToast("History Cleared"); }
        renderHistory();

        // Utilities
        function triggerFileImport(targetId) { activeTargetId = targetId; document.getElementById('fileInput').click(); }
        function handleFileSelect(event) {
            const file = event.target.files[0]; if (!file) return;
            const reader = new FileReader();
            reader.onload = e => {
                const area = document.getElementById(activeTargetId);
                if(activeTargetId === 'urls') area.value = [...new Set(e.target.result.split('\\n').map(l => l.trim()).filter(Boolean))].join('\\n');
                else area.value = e.target.result;
                showToast("File Imported");
            };
            reader.readAsText(file); event.target.value = ''; 
        }

        // Common API handler for status
        async function stopDownload() {
            document.querySelectorAll('[id^="status"]').forEach(el => el.innerText = 'Stopping Engine...');
            await fetch('/stop');
        }
        function startProgress(progId, stopBtnId, mainBtns) {
            if(progressInterval) clearInterval(progressInterval);
            document.getElementById(stopBtnId).style.display = 'block';
            mainBtns.forEach(btn => document.getElementById(btn).style.display = 'none');
            progressInterval = setInterval(async () => {
                try {
                    const res = await fetch('/progress'); const data = await res.json();
                    if(data.is_active) document.getElementById(progId).innerText = data.status;
                    else {
                        document.getElementById(progId).innerText = ""; clearInterval(progressInterval);
                        document.getElementById(stopBtnId).style.display = 'none';
                        mainBtns.forEach(btn => document.getElementById(btn).style.display = 'flex');
                    }
                } catch(e) {}
            }, 1000);
        }

        // Thumbnail Grabber
        function getThumb() {
            let url = document.getElementById('thumbUrl').value;
            let match = url.match(/(?:youtu\.be\/|youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})/);
            let resBox = document.getElementById('thumbResult');
            if(match && match[1]) {
                let imgUrl = `https://img.youtube.com/vi/${match[1]}/maxresdefault.jpg`;
                resBox.style.display = 'block';
                resBox.innerHTML = `✅ Found HD Cover:<br><br><img src="${imgUrl}" style="width:100%; border-radius:8px; margin-bottom:10px;"><a href="${imgUrl}" target="_blank" style="color:var(--accent-primary); font-weight:bold; text-decoration:none;">📥 Open Full Image to Save</a>`;
                showToast("Thumbnail Grabbed"); addHistory("Thumbnail Fetched");
            } else { alert("Please paste a valid YouTube link."); }
        }

        // Image Converter
        function handleImgSelect(event) {
            const files = event.target.files;
            document.getElementById('imgFilesText').innerText = files.length > 0 ? `${files.length} image(s) selected.` : 'Tap to select images';
        }
        async function convertImages() {
            const fileInput = document.getElementById('imgUploads');
            const statusBox = document.getElementById('statusImg');
            if (!fileInput.files.length) return;
            statusBox.innerHTML = "Converting Images... ⏳";
            const formData = new FormData();
            for (const file of fileInput.files) formData.append('files', file);
            formData.append('target_format', document.getElementById('imgTargetFormat').value);
            
            try {
                const res = await fetch('/convert-image-format', { method: 'POST', body: formData });
                const data = await res.json();
                statusBox.innerHTML = data.status === "error" ? `❌ Error: ${data.message}` : `<br>✅ Done!<br>${data.location}`;
                if(data.status==="done") { showToast("Images Converted"); addHistory("Image Format Converted"); }
                fileInput.value = ''; document.getElementById('imgFilesText').innerText = 'Tap to select images';
            } catch(e) { statusBox.innerHTML = `❌ Error: ${e.message}`; }
        }

        // Image to PDF
        function handlePdfSelect(event) {
            const files = event.target.files;
            document.getElementById('pdfFilesText').innerText = files.length > 0 ? `${files.length} image(s) selected.` : 'Tap to select images';
        }
        async function imagesToPdf() {
            const fileInput = document.getElementById('pdfUploads');
            const statusBox = document.getElementById('statusPdf');
            if (!fileInput.files.length) return;
            statusBox.innerHTML = "Generating PDF... ⏳";
            const formData = new FormData();
            for (const file of fileInput.files) formData.append('files', file);
            
            try {
                const res = await fetch('/images-to-pdf', { method: 'POST', body: formData });
                const data = await res.json();
                statusBox.innerHTML = data.status === "error" ? `❌ Error: ${data.message}` : `<br>✅ Done!<br>${data.location}`;
                if(data.status==="done") { showToast("PDF Generated"); addHistory("Images merged to PDF"); }
                fileInput.value = ''; document.getElementById('pdfFilesText').innerText = 'Tap to select images';
            } catch(e) { statusBox.innerHTML = `❌ Error: ${e.message}`; }
        }

        // TikTok Bulk
        async function scan() {
          const rawUrls = document.getElementById('urls').value.split('\\n').map(s => s.trim()).filter(Boolean);
          if(rawUrls.length === 0) return;
          const uniqueUrls = [...new Set(rawUrls)]; document.getElementById('urls').value = uniqueUrls.join('\\n'); 
          document.getElementById('status1').innerText = 'Scanning...';
          const res = await fetch('/scan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ urls: uniqueUrls, count: 5000 }) });
          const data = await res.json(); results = data.results || [];
          const grid = document.getElementById('grid'); grid.innerHTML = '';
          results.forEach((v, i) => { grid.innerHTML += `<div style="background:var(--input-bg); padding:10px; border-radius:8px; border:1px solid var(--border-color);"><label style="font-weight:600; font-size:12px; cursor:pointer;"><input type="checkbox" checked id="c${i}" style="margin-right:8px;">Include</label><div style="font-size:10px; color:var(--text-muted); margin-top:5px; word-break:break-all;">${v.url}</div></div>`; });
          document.getElementById('status1').innerText = `Scanned ${results.length} URLs.`;
        }
        function clearUrls() { document.getElementById('urls').value = ''; document.getElementById('grid').innerHTML = ''; results = []; document.getElementById('status1').innerText = 'Ready.'; }
        async function download(mode) {
          const selected = []; results.forEach((v, i) => { const el = document.getElementById('c'+i); if(el && el.checked) selected.push(v.url); });
          if(selected.length === 0) return;
          document.getElementById('status1').innerText = 'Engine Started...';
          startProgress('prog1', 'stopBtn1', ['downloadBtn']);
          try {
            const res = await fetch('/download', {
              method: 'POST', headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ selectedUrls: selected, folderPath: 'temp', quality: document.getElementById('quality').value, saveMode: document.getElementById('saveMode').value })
            });
            const data = await res.json();
            if(data.status === "error") document.getElementById('status1').innerHTML = `❌ Error: ${data.error}`;
            else { document.getElementById('status1').innerHTML = `✅ Complete!<br>${data.location}`; showToast("TikTok Batch Done"); addHistory(`TikTok Batch: ${selected.length} items`); }
          } catch(err) { document.getElementById('status1').innerHTML = '❌ Error'; }
        }

        // Universal
        async function startUniversal() {
            const url = document.getElementById('uniUrl').value.trim(); if(!url) return;
            document.getElementById('status2').innerText = 'Starting Engine...';
            startProgress('prog2', 'stopBtn2', ['uniBtn']);
            try {
                const res = await fetch('/universal-download', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url: url, folderPath: 'temp', formatType: document.getElementById('uniType').value, quality: document.getElementById('uniQuality').value })
                });
                const data = await res.json();
                if(data.status === "error") document.getElementById('status2').innerHTML = `❌ Error: ${data.error}`;
                else { document.getElementById('status2').innerHTML = `✅ Complete!<br>${data.location}`; showToast("Media Downloaded"); addHistory("Universal Extract"); }
            } catch(e) { document.getElementById('status2').innerHTML = '❌ Error'; }
        }

        // YT Shorts
        async function startYtShorts() {
            const docText = document.getElementById('ytDoc').value.trim(); if(!docText) return;
            document.getElementById('status3').innerText = 'Analyzing Script...';
            startProgress('prog3', 'stopBtn3', ['ytBtn']);
            try {
                const res = await fetch('/process-yt-document', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ document_text: docText, save_path: 'temp', mode: document.getElementById('ytSaveMode').value, quality: document.getElementById('ytQuality').value })
                });
                const data = await res.json();
                if(data.status === "error") document.getElementById('status3').innerHTML = `❌ Error: ${data.message}`;
                else { document.getElementById('status3').innerHTML = `✅ Sliced!<br>${data.location}`; showToast("Shorts Extracted"); addHistory("YT Shorts Maker"); }
            } catch(e) { document.getElementById('status3').innerHTML = '❌ Error'; }
        }

        // MP3 Methods
        function handleMp3UploadSelect(event) {
            const files = event.target.files;
            document.getElementById('selectedFilesText').innerText = files.length > 0 ? `${files.length} file(s) ready.` : 'Tap to select video files';
        }
        async function uploadAndConvertMp3() {
            const fileInput = document.getElementById('mp3UploadFiles'); const statusBox = document.getElementById('status4');
            if (!fileInput.files.length) return;
            statusBox.innerHTML = "Converting to MP3... ⏳";
            const formData = new FormData(); for (const file of fileInput.files) formData.append('files', file);
            try {
                const res = await fetch('/convert-mp3-upload', { method: 'POST', body: formData });
                const data = await res.json();
                statusBox.innerHTML = data.status === "error" ? `❌ Error: ${data.message}` : `<br>✅ Done!<br>${data.location}`;
                if(data.status === "done") { showToast("MP3 Extraction Done"); addHistory("MP3 Files Converted"); }
                fileInput.value = ''; document.getElementById('selectedFilesText').innerText = 'Tap to select video files';
            } catch(e) { statusBox.innerHTML = `❌ Error`; }
        }
        async function convertMp3BulkFolder() {
            document.getElementById('status4').innerHTML = "❌ Cloud Limit: Bulk local folder conversion only works on mobile Termux. Upload files instead!";
        }
      </script>
    </body>
    </html>
    """
# --- BACKEND LOGIC (Part 2) ---

def get_safe_default_path(subfolder): 
    return BASE_DIR / subfolder

def make_cloud_safe(folder_path: Path):
    # کلاؤڈ پر /storage/ والا پاتھ کام نہیں کرتا، یہ فنکشن اسے کلاؤڈ اور ٹرمکس دونوں کے لیے پرفیکٹ بناتا ہے
    if str(folder_path).startswith("/storage/") and not Path("/storage").exists():
        return BASE_DIR / folder_path.name
    return folder_path

@app.post("/scan")
async def scan(req: ScanRequest):
    seen = set(); cleaned = []
    for u in req.urls:
        val = u.strip()
        if val and val not in seen: seen.add(val); cleaned.append(val)
    return {"results": [{"url": u} for u in cleaned[:req.count]]}

def my_hook(d):
    global cancel_download
    if cancel_download: raise Exception("Download Cancelled")

def download_single_video(url: str, folder: Path, quality: str, name: str):
    global cancel_download
    if cancel_download: return False
    ydl_opts = {'outtmpl': str(folder / f'{name}.%(ext)s'), 'quiet': True, 'no_warnings': True, 'ignoreerrors': True, 'progress_hooks': [my_hook], 'nopart': True }
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

@app.post("/download")
def download(req: DownloadRequest):
    global progress_state, cancel_download
    cancel_download = False
    
    raw_folder = Path(req.folderPath.strip()).resolve() if req.folderPath.strip() else get_safe_default_path("TikTok")
    folder = make_cloud_safe(raw_folder)
    folder.mkdir(parents=True, exist_ok=True)
    
    progress_state = {"is_active": True, "total": len(req.selectedUrls), "completed": 0, "status": "Starting..."}
    try:
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures_map = {executor.submit(download_single_video, url, folder, req.quality, f"Mehar_Vid_{uuid.uuid4().hex[:6]}_{i:02d}"): url for i, url in enumerate(req.selectedUrls, 1)}
            for future in as_completed(futures_map):
                if cancel_download: return JSONResponse({"status": "stopped"})
                progress_state["completed"] += 1
                progress_state["status"] = f"Downloading... ({progress_state['completed']}/{progress_state['total']})"
        
        final_location = str(folder)
        if req.saveMode == "zip" and not cancel_download:
            zip_path = str(folder.parent / folder.name)
            shutil.make_archive(zip_path, 'zip', str(folder))
            final_location = f"{zip_path}.zip"
        else:
            # اگر سنگل فائل ہو تو اسے ڈائریکٹ ڈاؤنلوڈ لنک کے لیے پکڑنا
            files = list(folder.glob("Mehar_Vid_*.*"))
            if len(files) == 1:
                final_location = str(files[0])
                
        scan_media(final_location) 
        progress_state["is_active"] = False
        
        try: rel_loc = str(Path(final_location).relative_to(BASE_DIR)).replace("\\", "/")
        except: rel_loc = Path(final_location).name
        
        return JSONResponse({"status": "done", "location": rel_loc})
    except Exception as e:
        progress_state["is_active"] = False
        return JSONResponse({"status": "error", "error": str(e)}, status_code=500)

@app.post("/universal-download")
def universal_download(req: UniversalRequest):
    global progress_state, cancel_download
    cancel_download = False
    
    raw_folder = Path(req.folderPath.strip()).resolve() if req.folderPath.strip() else get_safe_default_path("Universal")
    folder = make_cloud_safe(raw_folder)
    folder.mkdir(parents=True, exist_ok=True)
    
    progress_state = {"is_active": True, "total": 1, "completed": 0, "status": "Grabbing Media..."}
    ydl_opts = {'outtmpl': str(folder / 'Universal_%(title)s.%(ext)s'), 'quiet': True, 'no_warnings': True, 'progress_hooks': [my_hook]}
    if req.formatType == "audio":
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}]
    elif req.formatType == "images":
        ydl_opts['outtmpl'] = str(folder / 'Mehar_Image_%(autonumber)s.%(ext)s')
        ydl_opts['format'] = 'best' 
    else:
        ydl_opts['merge_output_format'] = 'mp4'
        ydl_opts['format'] = 'worst[ext=mp4]/worst' if req.quality == "worst" else 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
        
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl: 
            info = ydl.extract_info(req.url, download=True)
            filename = ydl.prepare_filename(info)
            if req.formatType == "audio": filename = filename.rsplit('.', 1)[0] + '.mp3'
            
        scan_media(str(folder)) 
        progress_state["is_active"] = False
        
        try: rel_loc = str(Path(filename).relative_to(BASE_DIR)).replace("\\", "/")
        except: rel_loc = Path(filename).name
        
        return JSONResponse({"status": "done", "location": rel_loc})
    except Exception as e:
        progress_state["is_active"] = False
        return JSONResponse({"status": "error", "error": str(e)}, status_code=500)

def time_to_sec(t_str):
    parts = t_str.split(':')
    if len(parts) == 2: return int(parts[0]) * 60 + int(parts[1])
    elif len(parts) == 3: return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    return 0

@app.post("/process-yt-document")
def process_yt_document(req: YTDocRequest):
    global progress_state, cancel_download
    cancel_download = False
    text = req.document_text
    url_match = re.search(r'https?://(?:www\.)?youtube\.com/watch\?v=[\w-]+|https?://youtu\.be/[\w-]+', text)
    if not url_match: return JSONResponse({"status": "error", "message": "YouTube URL missing!"})
    yt_url = url_match.group(0)

    raw_folder = Path(req.save_path.strip()).resolve() if req.save_path.strip() else get_safe_default_path("YT_Shorts")
    folder_path = make_cloud_safe(raw_folder)
    folder_path.mkdir(parents=True, exist_ok=True)
    temp_folder = folder_path / "Temp_Process"
    temp_folder.mkdir(exist_ok=True)
    
    progress_state = {"is_active": True, "total": 100, "completed": 0, "status": "Parsing..."}

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
        progress_state["is_active"] = False
        return JSONResponse({"status": "error", "message": "No valid timestamps found!"})

    fmt = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]'
    if req.quality == "720p": fmt = 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]'
    elif req.quality == "1080p": fmt = 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]'

    progress_state["total"] = len(final_clips_data)
    progress_state["completed"] = 0
    total_extracted = 0
    
    for i, segments in enumerate(final_clips_data, 1):
        if cancel_download: break
        part_files = []
        for j, (start, end) in enumerate(segments, 1):
            progress_state["status"] = f"Extracting Clip {i} (Part {j} of {len(segments)})..."
            out_part = temp_folder / f"c_{i}_p_{j}.mp4"
            cmd = [sys.executable, '-m', 'yt_dlp', '-f', fmt, '--download-sections', f"*{start}-{end}", '--force-keyframes-at-cuts', '--quiet', '--no-warnings', '-o', str(out_part), yt_url]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if out_part.exists(): part_files.append(out_part)
        
        if len(part_files) > 0:
            total_extracted += 1
            progress_state["status"] = f"Merging Clip {i}..."
            final_output = folder_path / f"Mehar_Viral_{uuid.uuid4().hex[:4]}_{i:02d}.mp4"
            if len(part_files) == 1: shutil.move(str(part_files[0]), str(final_output))
            elif len(part_files) > 1:
                list_txt = temp_folder / f"list_{i}.txt"
                with open(list_txt, "w") as f:
                    for pf in part_files: f.write(f"file '{pf.name}'\n")
                subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', str(list_txt), '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '22', '-c:a', 'aac', str(final_output)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        progress_state["completed"] += 1

    try: shutil.rmtree(temp_folder)
    except: pass

    if total_extracted == 0:
        progress_state["is_active"] = False
        return JSONResponse({"status": "error", "message": "Extraction Failed."})

    final_loc = str(folder_path)
    if req.mode == "zip" and not cancel_download:
        zip_path = str(folder_path.parent / folder_path.name)
        shutil.make_archive(zip_path, 'zip', str(folder_path))
        final_loc = f"{zip_path}.zip"
    else:
        files = list(folder_path.glob("Mehar_Viral_*.mp4"))
        if len(files) == 1: final_loc = str(files[0])
        
    scan_media(final_loc) 
    progress_state["is_active"] = False
    
    try: rel_loc = str(Path(final_loc).relative_to(BASE_DIR)).replace("\\", "/")
    except: rel_loc = Path(final_loc).name
    
    return JSONResponse({"status": "done", "location": rel_loc})

@app.post("/convert-mp3-upload")
async def convert_mp3_upload(files: List[UploadFile] = File(...)):
    mp3_dir = BASE_DIR / "MP3_Converted"
    mp3_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = mp3_dir / "temp_uploads"
    temp_dir.mkdir(exist_ok=True)
    converted = 0
    last_file = None
    try:
        for file in files:
            temp_file = temp_dir / file.filename
            with open(temp_file, "wb") as buffer: shutil.copyfileobj(file.file, buffer)
            out_file = mp3_dir / f"{temp_file.stem}_Mehar.mp3"
            subprocess.run(['ffmpeg', '-y', '-i', str(temp_file), '-q:a', '0', '-map', 'a', str(out_file)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            scan_media(str(out_file))
            last_file = out_file
            converted += 1
    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return JSONResponse({"status": "error", "message": str(e)})

    shutil.rmtree(temp_dir, ignore_errors=True)
    
    if converted == 1 and last_file:
        try: rel_loc = str(last_file.relative_to(BASE_DIR)).replace("\\", "/")
        except: rel_loc = last_file.name
        return JSONResponse({"status": "done", "location": rel_loc})
    else:
        zip_path = str(mp3_dir)
        shutil.make_archive(zip_path, 'zip', str(mp3_dir))
        try: rel_loc = str(Path(f"{zip_path}.zip").relative_to(BASE_DIR)).replace("\\", "/")
        except: rel_loc = f"{mp3_dir.name}.zip"
        return JSONResponse({"status": "done", "location": rel_loc})

@app.post("/convert-mp3-folder")
def convert_mp3_folder(req: dict):
    raw_folder = req.get("folderPath", "").strip()
    if not raw_folder: return JSONResponse({"status": "error", "message": "Folder path is empty!"})
    
    folder = make_cloud_safe(Path(raw_folder).resolve())
    if not folder.exists() or not folder.is_dir(): return JSONResponse({"status": "error", "message": "Folder not found!"})
    
    mp3_folder = BASE_DIR / "MP3_Bulk_Converted"
    mp3_folder.mkdir(parents=True, exist_ok=True)
    converted = 0
    for file in folder.iterdir():
        if file.is_file() and file.suffix.lower() in ['.mp4', '.webm', '.mov', '.mkv', '.m4a']:
            out_file = mp3_folder / f"{file.stem}_Mehar.mp3"
            subprocess.run(['ffmpeg', '-y', '-i', str(file), '-q:a', '0', '-map', 'a', str(out_file)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            converted += 1
            
    scan_media(str(mp3_folder)) 
    return JSONResponse({"status": "done", "message": f"Converted {converted} files.<br>Saved in: {mp3_folder}"})

# --- IMAGE TOOLS ---
@app.post("/convert-image-format")
async def convert_image_format(files: List[UploadFile] = File(...), target_format: str = Form(...)):
    if 'PIL' not in sys.modules: return JSONResponse({"status": "error", "message": "Pillow not installed. Run: pip install Pillow"})
    out_dir = BASE_DIR / "Image_Conversions"
    out_dir.mkdir(parents=True, exist_ok=True)
    converted = 0
    last_file = None
    ext = target_format.lower()
    if ext == 'jpeg': ext = 'jpg'
    
    for file in files:
        try:
            img = Image.open(file.file)
            if target_format in ['JPEG', 'JPG'] and img.mode in ("RGBA", "P"): img = img.convert("RGB")
            out_file = out_dir / f"{Path(file.filename).stem}_Mehar.{ext}"
            img.save(str(out_file), format=target_format)
            scan_media(str(out_file))
            last_file = out_file
            converted += 1
        except Exception as e: pass
        
    if converted == 1 and last_file:
        try: rel_loc = str(last_file.relative_to(BASE_DIR)).replace("\\", "/")
        except: rel_loc = last_file.name
        return JSONResponse({"status": "done", "location": rel_loc})
    else:
        zip_path = str(out_dir)
        shutil.make_archive(zip_path, 'zip', str(out_dir))
        try: rel_loc = str(Path(f"{zip_path}.zip").relative_to(BASE_DIR)).replace("\\", "/")
        except: rel_loc = f"{out_dir.name}.zip"
        return JSONResponse({"status": "done", "location": rel_loc})

@app.post("/images-to-pdf")
async def images_to_pdf(files: List[UploadFile] = File(...)):
    if 'PIL' not in sys.modules: return JSONResponse({"status": "error", "message": "Pillow not installed. Run: pip install Pillow"})
    if not files: return JSONResponse({"status": "error", "message": "No images provided."})
    out_dir = BASE_DIR / "PDF_Documents"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    img_list = []
    try:
        first_img = Image.open(files[0].file).convert('RGB')
        for file in files[1:]:
            img = Image.open(file.file).convert('RGB')
            img_list.append(img)
            
        out_file = out_dir / f"Mehar_Doc_{len(list(out_dir.glob('*.pdf')))+1}.pdf"
        first_img.save(str(out_file), save_all=True, append_images=img_list)
        scan_media(str(out_file))
        
        try: rel_loc = str(out_file.relative_to(BASE_DIR)).replace("\\", "/")
        except: rel_loc = out_file.name
        return JSONResponse({"status": "done", "location": rel_loc})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)})
