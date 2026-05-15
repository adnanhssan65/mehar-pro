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
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import uuid

try:
    from PIL import Image
except ImportError:
    pass

app = FastAPI()

progress_state = {"is_active": False, "total": 0, "completed": 0, "status": "Idle", "percent": "0%", "speed": "0B/s"}
cancel_download = False 
ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

class ScanRequest(BaseModel): urls: List[str]; count: int = 5000
class DownloadRequest(BaseModel): selectedUrls: List[str]; folderPath: str; quality: str; saveMode: str
class ConvertRequest(BaseModel): folderPath: str; singleFilePath: Optional[str] = None
class UniversalRequest(BaseModel): url: str; folderPath: str; formatType: str; quality: str
class YTDocRequest(BaseModel): document_text: str; save_path: str; mode: str; quality: str

def scan_media(path_to_scan: str):
    try: subprocess.run(['termux-media-scan', str(path_to_scan)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except: pass

BASE_DIR = Path("/storage/emulated/0/Mehar Pro Downloader")
BASE_DIR.mkdir(parents=True, exist_ok=True)
if not (BASE_DIR / "temp").exists(): (BASE_DIR / "temp").mkdir()

app.mount("/files", StaticFiles(directory=str(BASE_DIR)), name="files")

def get_rel_path(full_path):
    try: return str(Path(full_path).relative_to(BASE_DIR)).replace("\\", "/")
    except: return Path(full_path).name

@app.get("/health")
def health(): return {"ok": True}

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
      <title>Mehar Pro Workspace</title>
      <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;800&display=swap" rel="stylesheet">
      <style>
        :root {
            --bg-body: #f4f7f6; --bg-panel: #ffffff; --border-color: #e2e8f0;
            --text-main: #1e293b; --text-muted: #64748b; --accent-primary: #10b981; 
            --accent-hover: #059669; --shadow-sm: 0 4px 6px rgba(0,0,0,0.05);
            --shadow-md: 0 10px 25px rgba(0,0,0,0.08); --input-bg: #f8fafc;
        }
        [data-theme="dark"] {
            --bg-body: #000000; --bg-panel: #111111; --border-color: #222222;
            --text-main: #ffffff; --text-muted: #94a3b8; --accent-primary: #10b981;
            --accent-hover: #34d399; --shadow-sm: 0 4px 6px rgba(255,255,255,0.02);
            --shadow-md: 0 10px 25px rgba(255,255,255,0.05); --input-bg: #1a1a1a;
        }
        * { box-sizing: border-box; }
        body { margin: 0; font-family: 'Poppins', sans-serif; background: var(--bg-body); color: var(--text-main); padding: 20px; transition: background 0.4s ease; padding-bottom: 80px; }
        
        /* Smooth Animations Added */
        @keyframes popIn { 0% { opacity: 0; transform: scale(0.95) translateY(20px); } 100% { opacity: 1; transform: scale(1) translateY(0); } }
        @keyframes float { 0% { transform: translateY(0px); } 50% { transform: translateY(-5px); } 100% { transform: translateY(0px); } }
        @keyframes pulseBar { 0% { opacity: 1; } 50% { opacity: 0.6; } 100% { opacity: 1; } }

        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 40px; padding-bottom: 15px; border-bottom: 2px solid var(--border-color); }
        .header h1 { margin: 0; font-size: 26px; font-weight: 800; letter-spacing: -0.5px; color: var(--text-main); }
        .header-sub { font-size: 11px; color: var(--accent-primary); font-weight: 800; letter-spacing: 2px; text-transform: uppercase;}
        .theme-btn { background: var(--input-bg); border: 2px solid var(--border-color); color: var(--text-main); width: 45px; height: 45px; border-radius: 50%; font-size: 18px; cursor: pointer; display: flex; justify-content: center; align-items: center; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); }
        .theme-btn:hover { border-color: var(--accent-primary); transform: rotate(15deg) scale(1.1); }

        .dashboard-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 20px; animation: popIn 0.5s cubic-bezier(0.4, 0, 0.2, 1); }
        .tool-card { background: var(--bg-panel); border: 2px solid transparent; border-radius: 24px; padding: 25px 15px; text-align: center; cursor: pointer; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); box-shadow: var(--shadow-sm); display: flex; flex-direction: column; align-items: center; gap: 10px; }
        .tool-card:hover { transform: translateY(-8px) scale(1.02); box-shadow: var(--shadow-md); border-color: var(--accent-primary); }
        .tool-icon { font-size: 38px; margin-bottom: 5px; animation: float 3s ease-in-out infinite; }
        .tool-title { font-size: 14px; font-weight: 800; }
        .tool-desc { font-size: 11px; color: var(--text-muted); font-weight: 600; }

        .tool-view { display: none; animation: popIn 0.4s cubic-bezier(0.4, 0, 0.2, 1); max-width: 800px; margin: 0 auto; }
        .tool-view.active { display: block; }
        .back-nav { display: inline-flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 800; cursor: pointer; margin-bottom: 25px; background: var(--bg-panel); padding: 12px 20px; border-radius: 50px; border: 2px solid var(--border-color); color: var(--text-main); transition: all 0.3s; box-shadow: var(--shadow-sm);}
        .back-nav:hover { border-color: var(--accent-primary); color: var(--accent-primary); transform: translateX(-5px); }

        .tool-container { background: var(--bg-panel); border-radius: 30px; padding: 30px; box-shadow: var(--shadow-md); border: 1px solid var(--border-color); }
        .tool-header { text-align: center; margin-bottom: 30px; }
        .tool-header h2 { margin: 10px 0 10px 0; font-size: 24px; font-weight: 800; }
        .tool-header p { margin: 0; font-size: 13px; color: var(--text-muted); font-weight: 600; }

        /* Custom YouTube Logo Animation */
        .yt-logo-container svg { width: 55px; height: 55px; transition: transform 0.4s cubic-bezier(0.4, 0, 0.2, 1); }
        .yt-logo-container:hover svg { transform: scale(1.15) rotate(5deg); }

        textarea, input[type="text"], select { width: 100%; border-radius: 20px; border: 2px solid var(--border-color); background: var(--input-bg); color: var(--text-main); padding: 18px 20px; box-sizing: border-box; font-size: 13px; font-weight: 600; margin-bottom: 15px; transition: all 0.3s; font-family: 'Poppins', sans-serif;}
        textarea { min-height: 140px; resize: vertical; border-radius: 24px; }
        textarea:focus, input:focus, select:focus { border-color: var(--accent-primary); outline: none; background: transparent; box-shadow: 0 0 0 4px rgba(16, 185, 129, 0.1); }
        
        .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 15px;}
        .btn-group { display: flex; flex-wrap: wrap; gap: 15px; margin-top: 10px; }
        
        button.btn { flex: 1; min-width: 140px; border: none; padding: 18px; border-radius: 50px; cursor: pointer; font-weight: 800; font-size: 14px; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); font-family: 'Poppins', sans-serif; letter-spacing: 0.5px;}
        .btn-primary { background: var(--accent-primary); color: white; box-shadow: 0 8px 20px rgba(16, 185, 129, 0.3); }
        .btn-primary:hover { background: var(--accent-hover); transform: translateY(-3px) scale(1.02); box-shadow: 0 12px 25px rgba(16, 185, 129, 0.4); }
        .btn-secondary { background: var(--input-bg); color: var(--text-main); border: 2px solid var(--border-color); }
        .btn-secondary:hover { border-color: var(--text-muted); transform: translateY(-2px); }
        .btn-danger { background: #ef4444; color: white; display: none; width: 100%; margin-top: 15px; border-radius: 50px; padding: 18px;}

        .status-box { background: var(--input-bg); padding: 20px; border-radius: 24px; margin-top: 25px; border: 2px solid var(--border-color); font-size: 13px; font-weight: 600; display: none; animation: popIn 0.3s ease-out; }
        .progress-container { width: 100%; background-color: var(--border-color); border-radius: 50px; margin: 15px 0; overflow: hidden; height: 12px; display: none; }
        .progress-bar { height: 100%; background-color: var(--accent-primary); width: 0%; border-radius: 50px; transition: width 0.4s ease; animation: pulseBar 2s infinite; }
        .progress-details { display: flex; justify-content: space-between; font-size: 11px; color: var(--text-muted); font-weight: 800; }

        .dl-buttons-container { display: flex; gap: 15px; margin-top: 20px; flex-wrap: wrap; animation: popIn 0.4s ease; }
        .dl-btn { flex: 1; padding: 18px; border-radius: 50px; text-align: center; font-weight: 800; font-size: 13px; text-decoration: none; display: flex; align-items: center; justify-content: center; gap: 8px; color: white; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); box-shadow: var(--shadow-sm);}
        .dl-btn-file { background: #1e293b; }
        .dl-btn-zip { background: #f59e0b; }
        .dl-btn:hover { filter: brightness(1.1); transform: translateY(-3px) scale(1.02); box-shadow: 0 10px 20px rgba(0,0,0,0.15); }
        [data-theme="dark"] .dl-btn-file { background: #334155; }

        .file-upload-wrapper { border: 2px dashed var(--border-color); border-radius: 24px; padding: 35px 15px; text-align: center; cursor: pointer; transition: all 0.3s; background: var(--input-bg); margin-bottom: 20px; }
        .file-upload-wrapper:hover { border-color: var(--accent-primary); background: transparent; transform: scale(1.01); }
        .file-upload-wrapper p { margin: 15px 0 0 0; font-size: 13px; color: var(--text-muted); font-weight: 600; }
        
        .modal-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); z-index: 1000; justify-content: center; align-items: center; backdrop-filter: blur(5px); opacity: 0; transition: opacity 0.3s; }
        .modal-content { background: var(--bg-panel); padding: 35px; border-radius: 30px; width: 90%; max-width: 500px; max-height: 85vh; overflow-y: auto; position: relative; border: 1px solid var(--border-color); box-shadow: var(--shadow-md); transform: scale(0.9); transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);}
        .modal-overlay.show { opacity: 1; }
        .modal-overlay.show .modal-content { transform: scale(1); }
        
        .modal-content h3 { margin-top: 0; color: var(--text-main); font-size: 22px; font-weight: 800; border-bottom: 2px solid var(--input-bg); padding-bottom: 15px;}
        .close-modal { position: absolute; top: 25px; right: 25px; font-size: 24px; cursor: pointer; color: var(--text-muted); font-weight: bold; transition: 0.2s; }
        .close-modal:hover { color: #ef4444; transform: rotate(90deg); }
        .help-item { margin-bottom: 15px; font-size: 13px; line-height: 1.6; color: var(--text-muted); font-weight: 500;}
        .help-item b { color: var(--text-main); font-size: 14px; font-weight: 800;}
        
        .toast { position: fixed; top: 20px; left: 50%; transform: translateX(-50%) translateY(-100px); background: var(--text-main); color: var(--bg-body); padding: 15px 30px; border-radius: 50px; font-size: 13px; font-weight: 800; z-index: 9999; opacity: 0; transition: all 0.5s cubic-bezier(0.4, 0, 0.2, 1); box-shadow: var(--shadow-md);}
        .toast.show { transform: translateX(-50%) translateY(0); opacity: 1; }
        .footer { text-align: center; color: var(--text-muted); margin-top: 50px; font-size: 12px; font-weight: 600;}
      </style>
    </head>
    <body>
      <div id="toast" class="toast">Action Completed!</div>

      <div class="header">
        <div class="header-brand">
            <h1>Mehar Pro.</h1>
            <span class="header-sub">Local Workspace</span>
        </div>
        <button class="theme-btn" onclick="toggleTheme()">🌓</button>
      </div>

      <div id="view-dashboard" class="dashboard-grid">
        <div class="tool-card" onclick="openTool('tool-tiktok')"><div class="tool-icon">📱</div><div class="tool-title">TikTok Bulk</div><div class="tool-desc">Batch download videos</div></div>
        <div class="tool-card" onclick="openTool('tool-yt')"><div class="tool-icon">✂️</div><div class="tool-title">YT Clips</div><div class="tool-desc">AI Specific extraction</div></div>
        <div class="tool-card" onclick="openTool('tool-universal')"><div class="tool-icon">🌍</div><div class="tool-title">Universal</div><div class="tool-desc">Any link downloader</div></div>
        <div class="tool-card" onclick="openTool('tool-mp3')"><div class="tool-icon">🎵</div><div class="tool-title">MP3 Audio</div><div class="tool-desc">Convert files to MP3</div></div>
        <div class="tool-card" onclick="openTool('tool-thumbnail')"><div class="tool-icon">🖼️</div><div class="tool-title">Thumbnails</div><div class="tool-desc">HD YouTube covers</div></div>
        <div class="tool-card" onclick="openTool('tool-img-convert')"><div class="tool-icon">🔄</div><div class="tool-title">Img Convert</div><div class="tool-desc">PNG, JPG, WEBP</div></div>
        <div class="tool-card" onclick="openTool('tool-pdf')"><div class="tool-icon">📄</div><div class="tool-title">Image to PDF</div><div class="tool-desc">Combine images</div></div>
        <div class="tool-card" onclick="openTool('tool-settings')"><div class="tool-icon">⚙️</div><div class="tool-title">Settings</div><div class="tool-desc">Paths & History</div></div>
      </div>

      <div id="tools-container">
        <div id="tool-tiktok" class="tool-view">
          <div class="back-nav" onclick="goHome()">🔙 Back to Home</div>
          <div class="tool-container">
              <div class="tool-header"><h2>TikTok Bulk Downloader</h2><p>Paste multiple links to batch download instantly.</p></div>
              <textarea id="urls" placeholder="Paste links line by line..."></textarea>
              <div class="grid-2">
                  <select id="quality"><option value="worst">Fast (Low Quality)</option><option value="best" selected>Original (HD Quality)</option><option value="audio_only">Audio Only (MP3)</option></select>
                  <select id="saveMode"><option value="separate">Save Mode: Separate Files</option><option value="zip">Save Mode: ZIP Archive</option></select>
              </div>
              <div class="btn-group">
                <button class="btn btn-secondary" onclick="triggerFileImport('urls')">📁 Import TXT</button>
                <button class="btn btn-secondary" onclick="scan()">🔍 Scan URLs</button>
                <button class="btn btn-primary" id="downloadBtn" onclick="download('video')">🚀 Start Download</button>
              </div>
              <button class="btn btn-danger" id="stopBtn1" onclick="stopDownload()">🛑 Cancel Process</button>
              <div id="status1" class="status-box"><div id="msg1">Ready.</div><div class="progress-container" id="pc1"><div class="progress-bar" id="pb1"></div></div><div class="progress-details" id="pd1"></div><div id="res1"></div></div>
          </div>
        </div>

        <div id="tool-universal" class="tool-view">
          <div class="back-nav" onclick="goHome()">🔙 Back to Home</div>
          <div class="tool-container">
              <div class="tool-header"><h2>Universal Downloader</h2><p>Extract media from Facebook, Insta, Twitter, etc.</p></div>
              <input type="text" id="uniUrl" placeholder="Media Link (https://...)">
              <div class="grid-2">
                  <select id="uniType"><option value="video">Format: Video</option><option value="audio">Format: Audio (MP3)</option></select>
                  <select id="uniQuality"><option value="best">Quality: Best</option><option value="worst">Quality: Fastest</option></select>
              </div>
              <button class="btn btn-primary" id="uniBtn" onclick="startUniversal()" style="width:100%;">🚀 Download Media</button>
              <button class="btn btn-danger" id="stopBtn2" onclick="stopDownload()">🛑 Cancel Process</button>
              <div id="status2" class="status-box"><div id="msg2">Ready.</div><div class="progress-container" id="pc2"><div class="progress-bar" id="pb2"></div></div><div class="progress-details" id="pd2"></div><div id="res2"></div></div>
          </div>
        </div>

        <div id="tool-yt" class="tool-view">
          <div class="back-nav" onclick="goHome()">🔙 Back to Home</div>
          <div class="tool-container">
              <div class="tool-header yt-logo-container">
                  <svg viewBox="0 0 24 24" fill="#ff0000" xmlns="http://www.w3.org/2000/svg">
                      <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.5 12 3.5 12 3.5s-7.505 0-9.377.55a3.016 3.016 0 0 0-2.122 2.136C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.55 9.376.55 9.376.55s7.505 0 9.377-.55a3.016 3.016 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>
                  </svg>
                  <h2>YT Clips Downloader</h2>
                  <p>Frame-accurate clipping and auto-merging.</p>
              </div>
              <textarea id="ytDoc" placeholder="Paste AI Script with timestamps..."></textarea>
              <div class="grid-2">
                  <select id="ytQuality"><option value="720p">Quality: 720p HD</option><option value="1080p" selected>Quality: 1080p FHD</option></select>
                  <select id="ytMode"><option value="separate">Save Mode: Separate Shorts</option><option value="zip">Save Mode: ZIP Archive</option></select>
              </div>
              <div class="btn-group">
                <button class="btn btn-secondary" onclick="triggerFileImport('ytDoc')">📄 Import Doc</button>
                <button class="btn btn-primary" id="ytBtn" onclick="startYtShorts()">✂️ Extract & Merge</button>
              </div>
              <button class="btn btn-danger" id="stopBtn3" onclick="stopDownload()">🛑 Cancel Process</button>
              <div id="status3" class="status-box"><div id="msg3">Ready.</div><div class="progress-container" id="pc3"><div class="progress-bar" id="pb3"></div></div><div class="progress-details" id="pd3"></div><div id="res3"></div></div>
          </div>
        </div>

        <div id="tool-mp3" class="tool-view">
          <div class="back-nav" onclick="goHome()">🔙 Back to Home</div>
          <div class="tool-container">
              <div class="tool-header"><h2>MP3 Converter</h2><p>Local high-speed audio extraction.</p></div>
              <input type="file" id="mp3UploadFiles" multiple accept="video/*,audio/*" style="display:none;" onchange="document.getElementById('mp3Text').innerText = this.files.length + ' file(s) selected'">
              <div class="file-upload-wrapper" onclick="document.getElementById('mp3UploadFiles').click()">
                  <div style="font-size:38px; margin-bottom:10px;">📁</div><p id="mp3Text">Tap to select video files</p>
              </div>
              <button class="btn btn-primary" onclick="convertMp3()" style="width:100%;">⚡ Convert to MP3</button>
              <div style="margin: 25px 0; border-top: 2px dashed var(--border-color);"></div>
              <input type="text" id="mp3Folder" placeholder="Or paste bulk folder path here...">
              <button class="btn btn-secondary" onclick="convertMp3Bulk()" style="width:100%;">🔄 Convert Entire Folder</button>
              <div id="status4" class="status-box"><div id="msg4">Ready.</div><div id="res4"></div></div>
          </div>
        </div>

        <div id="tool-thumbnail" class="tool-view">
          <div class="back-nav" onclick="goHome()">🔙 Back to Home</div>
          <div class="tool-container">
              <div class="tool-header"><h2>Thumbnail Grabber</h2><p>Download max-res YouTube covers instantly.</p></div>
              <input type="text" id="thumbUrl" placeholder="YouTube Link (https://...)">
              <button class="btn btn-primary" onclick="getThumb()" style="width:100%;">🖼️ Fetch HD Thumbnail</button>
              <div id="status5" class="status-box"><div id="msg5">Ready.</div><div id="res5"></div></div>
          </div>
        </div>

        <div id="tool-img-convert" class="tool-view">
          <div class="back-nav" onclick="goHome()">🔙 Back to Home</div>
          <div class="tool-container">
              <div class="tool-header"><h2>Image Format Converter</h2><p>Convert images locally (PNG, JPG, WEBP).</p></div>
              <input type="file" id="imgUploads" multiple accept="image/*" style="display:none;" onchange="document.getElementById('imgFilesText').innerText = this.files.length + ' image(s) selected'">
              <div class="file-upload-wrapper" onclick="document.getElementById('imgUploads').click()">
                  <div style="font-size:38px; margin-bottom:10px;">📸</div><p id="imgFilesText">Tap to select images</p>
              </div>
              <select id="imgTargetFormat"><option value="PNG">Convert To: PNG</option><option value="JPEG">Convert To: JPG</option><option value="WEBP">Convert To: WEBP</option></select>
              <button class="btn btn-primary" onclick="convertImages()" style="width:100%;">🔄 Convert Now</button>
              <div id="statusImg" class="status-box"><div id="msgImg">Ready.</div><div id="resImg"></div></div>
          </div>
        </div>

        <div id="tool-pdf" class="tool-view">
          <div class="back-nav" onclick="goHome()">🔙 Back to Home</div>
          <div class="tool-container">
              <div class="tool-header"><h2>Image to PDF</h2><p>Combine multiple images into one PDF document.</p></div>
              <input type="file" id="pdfUploads" multiple accept="image/*" style="display:none;" onchange="document.getElementById('pdfFilesText').innerText = this.files.length + ' image(s) selected'">
              <div class="file-upload-wrapper" onclick="document.getElementById('pdfUploads').click()">
                  <div style="font-size:38px; margin-bottom:10px;">📄</div><p id="pdfFilesText">Tap to select images (Order matters)</p>
              </div>
              <button class="btn btn-primary" onclick="imagesToPdf()" style="width:100%;">📑 Generate PDF</button>
              <div id="statusPdf" class="status-box"><div id="msgPdf">Ready.</div><div id="resPdf"></div></div>
          </div>
        </div>

        <div id="tool-settings" class="tool-view">
          <div class="back-nav" onclick="goHome()">🔙 Back to Home</div>
          <div class="tool-container">
              <div class="tool-header"><h2>System Settings</h2><p>View recent activity.</p></div>
              <h3 style="font-size:16px; margin-top:0; border-bottom: 2px solid var(--border-color); padding-bottom:10px;">🕒 Recent History</h3>
              <div id="historyList" style="max-height: 250px; overflow-y: auto; font-size:13px; margin-bottom:20px; padding-right:10px;"></div>
              <button class="btn btn-secondary" onclick="clearHistory()" style="width:100%;">🗑️ Clear History</button>
          </div>
        </div>
      </div>

      <input type="file" id="fileInput" accept=".txt" style="display:none;" onchange="handleFileSelect(event)">

      <div id="helpModal" class="modal-overlay" onclick="if(event.target==this) closeHelp()">
        <div class="modal-content">
          <span class="close-modal" onclick="closeHelp()">&times;</span>
          <h3>📖 How to Use</h3>
          <div class="help-item"><b>📱 Direct Downloads:</b> Just paste links and hit Download. Files are automatically saved to your Phone Storage.</div>
          <div class="help-item"><b>📦 ZIP Files:</b> For multiple files, a ZIP button will automatically appear at the end.</div>
          <div class="help-item"><b>✂️ YT Clips:</b> Paste document with timestamps. Now uses <code>-c copy</code> for lightning fast merging!</div>
          <div class="help-item"><b>🎵 MP3 Audio:</b> Select files to convert them to MP3. Speed has been highly optimized.</div>
          <div class="help-item"><b>🖼️ Thumbnails:</b> Paste a YouTube link to get its HD Cover Photo.</div>
          <button class="btn btn-primary" onclick="closeHelp()" style="width: 100%; margin-top: 20px;">Got it, Thanks!</button>
        </div>
      </div>

      <div class="footer">
        Mehar Pro Workspace<br>Support: +92 343 6873471<br><br>
        <button class="btn btn-secondary" style="border-radius: 50px; padding: 12px 30px; font-weight: 800;" onclick="openHelp()">📖 How to Use?</button>
      </div>

      <script>
        let progressInterval = null;
        let activeTargetId = '';

        function showToast(msg) {
            const t = document.getElementById('toast');
            t.innerHTML = `✅ ${msg}`; t.classList.add('show');
            setTimeout(() => { t.classList.remove('show'); }, 3000);
        }

        function toggleTheme() {
            const html = document.documentElement;
            const th = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
            html.setAttribute('data-theme', th); localStorage.setItem('mehar_theme', th);
        }
        if(localStorage.getItem('mehar_theme') === 'dark') document.documentElement.setAttribute('data-theme', 'dark');

        function openTool(id) { document.getElementById('view-dashboard').style.display='none'; document.getElementById(id).classList.add('active'); window.scrollTo({top:0, behavior:'smooth'}); }
        function goHome() { document.querySelectorAll('.tool-view').forEach(v=>v.classList.remove('active')); document.getElementById('view-dashboard').style.display='grid'; window.scrollTo({top:0, behavior:'smooth'}); }
        function openHelp() { let m = document.getElementById('helpModal'); m.style.display='flex'; setTimeout(()=>m.classList.add('show'), 10); }
        function closeHelp() { let m = document.getElementById('helpModal'); m.classList.remove('show'); setTimeout(()=>m.style.display='none', 300); }

        function renderDlBtns(file, zip) {
            let html = `<div class="dl-buttons-container">`;
            if(file) html += `<a href="/files/${file}" class="dl-btn dl-btn-file" download>📥 Open Folder / File</a>`;
            if(zip) html += `<a href="/files/${zip}" class="dl-btn dl-btn-zip" download>📦 Download ZIP</a>`;
            html += `</div>`; return html;
        }

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
            div.innerHTML = hist.map(h => `<div style="padding:12px 15px; background:var(--input-bg); border-radius:12px; margin-bottom:10px; border-left:4px solid var(--accent-primary); box-shadow: var(--shadow-sm);">${h}</div>`).join('');
        }
        function clearHistory() { localStorage.removeItem('mehar_hist'); renderHistory(); showToast("History Cleared"); }
        renderHistory();

        async function stopDownload() {
            document.querySelectorAll('[id^="msg"]').forEach(el => el.innerHTML = 'Stopping Engine... Please wait.');
            await fetch('/stop');
        }

        function startPoll(baseId, stopBtnId, btnId) {
            if(progressInterval) clearInterval(progressInterval);
            document.getElementById(stopBtnId).style.display = 'block';
            document.getElementById(btnId).style.display = 'none';
            document.getElementById('status'+baseId).style.display = 'block';
            document.getElementById('res'+baseId).innerHTML = '';
            
            let pc = document.getElementById('pc'+baseId);
            if(pc) { pc.style.display = 'block'; document.getElementById('pb'+baseId).style.width = '0%'; }

            progressInterval = setInterval(async () => {
                try {
                    let r = await fetch('/progress'); let d = await r.json();
                    if(d.is_active) {
                        document.getElementById('msg'+baseId).innerText = d.status;
                        if(d.percent && pc) {
                            document.getElementById('pb'+baseId).style.width = d.percent;
                            document.getElementById('pd'+baseId).innerHTML = `<span>${d.percent}</span><span>${d.speed}</span>`;
                        }
                    } else {
                        clearInterval(progressInterval);
                        document.getElementById(stopBtnId).style.display = 'none';
                        document.getElementById(btnId).style.display = 'block';
                        if(pc) pc.style.display = 'none';
                        let pd = document.getElementById('pd'+baseId); if(pd) pd.innerHTML = '';
                    }
                } catch(e){}
            }, 1000);
        }

        async function scan() {
            let urls = document.getElementById('urls').value.split('\\n').map(s=>s.trim()).filter(Boolean);
            if(!urls.length) return;
            document.getElementById('urls').value = [...new Set(urls)].join('\\n');
            document.getElementById('status1').style.display = 'block';
            document.getElementById('msg1').innerHTML = `Scanned ${urls.length} links ready.`;
        }

        async function download() {
            let urls = document.getElementById('urls').value.split('\\n').map(s=>s.trim()).filter(Boolean);
            if(!urls.length) return;
            startPoll('1', 'stopBtn1', 'downloadBtn');
            try {
                let res = await fetch('/download', {
                    method:'POST', headers:{'Content-Type':'application/json'},
                    body:JSON.stringify({selectedUrls: urls, folderPath: 'TikTok', quality: document.getElementById('quality').value, saveMode: document.getElementById('saveMode').value})
                });
                let data = await res.json();
                if(data.status==="error") document.getElementById('msg1').innerHTML = `❌ Error: ${data.error}`;
                else { document.getElementById('msg1').innerHTML = `✅ Complete!`; document.getElementById('res1').innerHTML = renderDlBtns(data.file_location, data.zip_location); showToast("Downloaded"); addHistory(`TikTok Batch: ${urls.length} items`); }
            } catch(e) { document.getElementById('msg1').innerHTML = `❌ Error`; }
        }

        async function startUniversal() {
            let url = document.getElementById('uniUrl').value.trim(); if(!url) return;
            startPoll('2', 'stopBtn2', 'uniBtn');
            try {
                let res = await fetch('/universal-download', {
                    method:'POST', headers:{'Content-Type':'application/json'},
                    body:JSON.stringify({url: url, folderPath: 'Universal', formatType: document.getElementById('uniType').value, quality: document.getElementById('uniQuality').value})
                });
                let data = await res.json();
                if(data.status==="error") document.getElementById('msg2').innerHTML = `❌ Error: ${data.error}`;
                else { document.getElementById('msg2').innerHTML = `✅ Complete!`; document.getElementById('res2').innerHTML = renderDlBtns(data.file_location, data.zip_location); showToast("Downloaded"); addHistory("Universal Extract"); }
            } catch(e) { document.getElementById('msg2').innerHTML = `❌ Error`; }
        }

        async function startYtShorts() {
            let txt = document.getElementById('ytDoc').value.trim(); if(!txt) return;
            startPoll('3', 'stopBtn3', 'ytBtn');
            try {
                let res = await fetch('/process-yt-document', {
                    method:'POST', headers:{'Content-Type':'application/json'},
                    body:JSON.stringify({document_text: txt, save_path: 'YT_Shorts', mode: document.getElementById('ytMode').value, quality: document.getElementById('ytQuality').value})
                });
                let data = await res.json();
                if(data.status==="error") document.getElementById('msg3').innerHTML = `❌ Error: ${data.message}`;
                else { document.getElementById('msg3').innerHTML = `✅ Complete!`; document.getElementById('res3').innerHTML = renderDlBtns(data.file_location, data.zip_location); showToast("Saved"); addHistory("YT Clips Sliced"); }
            } catch(e) { document.getElementById('msg3').innerHTML = `❌ Error`; }
        }

        async function convertMp3() {
            let f = document.getElementById('mp3UploadFiles'); 
            if(!f.files.length) return; 
            document.getElementById('status4').style.display = 'block';
            document.getElementById('msg4').innerHTML = "Converting... ⏳";
            let fd = new FormData(); for(let x of f.files) fd.append('files', x);
            try {
                let res = await fetch('/convert-mp3-upload', {method:'POST', body:fd});
                let data = await res.json();
                if(data.status==="error") document.getElementById('msg4').innerHTML = `❌ Error: ${data.message}`;
                else { document.getElementById('msg4').innerHTML = `✅ Complete!`; document.getElementById('res4').innerHTML = renderDlBtns(data.file_location, data.zip_location); showToast("Converted"); addHistory("MP3 Converted"); }
                f.value = ''; document.getElementById('mp3Text').innerText = 'Tap to select video files';
            } catch(e) { document.getElementById('msg4').innerHTML = `❌ Error`; }
        }

        async function convertMp3Bulk() {
            let p = document.getElementById('mp3Folder').value.trim(); 
            if(!p) return; 
            document.getElementById('status4').style.display = 'block';
            document.getElementById('msg4').innerHTML = "Processing Folder... ⏳";
            try {
                let res = await fetch('/convert-mp3-folder', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({folderPath: p})});
                let data = await res.json();
                if(data.status==="error") document.getElementById('msg4').innerHTML = `❌ Error: ${data.message}`;
                else { document.getElementById('msg4').innerHTML = `✅ Complete!`; document.getElementById('res4').innerHTML = renderDlBtns(data.file_location, data.zip_location); showToast("Converted"); addHistory("Bulk MP3"); }
            } catch(e) { document.getElementById('msg4').innerHTML = `❌ Error`; }
        }

        function getThumb() {
            let url = document.getElementById('thumbUrl').value;
            let match = url.match(/(?:youtu\.be\/|youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})/);
            let stat = document.getElementById('status5');
            stat.style.display = 'block';
            if(match && match[1]) {
                let imgUrl = `https://img.youtube.com/vi/${match[1]}/maxresdefault.jpg`;
                document.getElementById('msg5').innerHTML = `✅ Found HD Cover:<br><br><img src="${imgUrl}" style="width:100%; border-radius:15px; margin-bottom:10px; box-shadow:var(--shadow-md);">`;
                document.getElementById('res5').innerHTML = `<a href="${imgUrl}" target="_blank" style="color:var(--accent-primary); font-weight:bold;">📥 Long press image to Save</a>`;
                showToast("Thumbnail Grabbed"); addHistory("Thumbnail Fetched");
            } else { document.getElementById('msg5').innerHTML = "❌ Please paste a valid YouTube link."; document.getElementById('res5').innerHTML = ''; }
        }

        async function convertImages() {
            let f = document.getElementById('imgUploads'); 
            if(!f.files.length) return; 
            document.getElementById('statusImg').style.display = 'block';
            document.getElementById('msgImg').innerHTML = "Converting... ⏳";
            let fd = new FormData(); for(let x of f.files) fd.append('files', x); fd.append('target_format', document.getElementById('imgTargetFormat').value);
            try {
                let res = await fetch('/convert-image-format', {method:'POST', body:fd});
                let data = await res.json();
                if(data.status==="error") document.getElementById('msgImg').innerHTML = `❌ Error: ${data.message}`;
                else { document.getElementById('msgImg').innerHTML = `✅ Converted!`; document.getElementById('resImg').innerHTML = renderDlBtns(data.file_location, data.zip_location); showToast("Images Saved"); addHistory("Image Converted"); }
                f.value = ''; document.getElementById('imgFilesText').innerText = 'Tap to select images';
            } catch(e) { document.getElementById('msgImg').innerHTML = `❌ Error`; }
        }

        async function imagesToPdf() {
            let f = document.getElementById('pdfUploads'); 
            if(!f.files.length) return; 
            document.getElementById('statusPdf').style.display = 'block';
            document.getElementById('msgPdf').innerHTML = "Generating PDF... ⏳";
            let fd = new FormData(); for(let x of f.files) fd.append('files', x);
            try {
                let res = await fetch('/images-to-pdf', {method:'POST', body:fd});
                let data = await res.json();
                if(data.status==="error") document.getElementById('msgPdf').innerHTML = `❌ Error: ${data.message}`;
                else { document.getElementById('msgPdf').innerHTML = `✅ PDF Ready!`; document.getElementById('resPdf').innerHTML = renderDlBtns(data.file_location, data.zip_location); showToast("PDF Saved"); addHistory("Images to PDF"); }
                f.value = ''; document.getElementById('pdfFilesText').innerText = 'Tap to select images';
            } catch(e) { document.getElementById('msgPdf').innerHTML = `❌ Error`; }
        }
      </script>
    </body>
    </html>
    """
# --- BACKEND LOGIC (Part 3) ---

def get_safe_default_path(subfolder): 
    return BASE_DIR / subfolder

def my_hook(d):
    global cancel_download, progress_state, ansi_escape
    if cancel_download: raise Exception("Download Cancelled")
    if d['status'] == 'downloading':
        try:
            p = ansi_escape.sub('', d.get('_percent_str', '0%')).strip()
            s = ansi_escape.sub('', d.get('_speed_str', '0B/s')).strip()
            progress_state['percent'] = p
            progress_state['speed'] = s
        except: pass

def download_single_video(url: str, folder: Path, quality: str, name: str):
    global cancel_download
    if cancel_download: return False
    
    # SPEED BOOSTERS FOR YT-DLP (Throttling Bypass)
    ydl_opts = {
        'outtmpl': str(folder / f'{name}.%(ext)s'), 
        'quiet': True, 'no_warnings': True, 'ignoreerrors': True, 
        'progress_hooks': [my_hook], 'nopart': True,
        'concurrent_fragment_downloads': 10,
        'http_chunk_size': 10485760,
        'hls_prefer_native': True
    }
    
    if quality == "audio_only":
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}]
    else:
        ydl_opts['merge_output_format'] = 'mp4'
        ydl_opts['format'] = 'worst[ext=mp4]/worst' if quality == "worst" else 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl: ydl.download([url])
        return True
    except: return False

@app.post("/download")
def download(req: DownloadRequest):
    global progress_state, cancel_download
    cancel_download = False
    
    batch_name = f"TikTok_Batch_{uuid.uuid4().hex[:6]}"
    folder = Path(req.folderPath.strip()).resolve() if req.folderPath.strip() else get_safe_default_path("TikTok")
    folder = folder / batch_name
    folder.mkdir(parents=True, exist_ok=True)
    
    progress_state = {"is_active": True, "total": len(req.selectedUrls), "completed": 0, "status": "Starting...", "percent": "0%", "speed": "0B/s"}
    try:
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures_map = {executor.submit(download_single_video, url, folder, req.quality, f"Mehar_Vid_{i:02d}"): url for i, url in enumerate(req.selectedUrls, 1)}
            for future in as_completed(futures_map):
                if cancel_download: return JSONResponse({"status": "stopped"})
                progress_state["completed"] += 1
                progress_state["status"] = f"Downloading... ({progress_state['completed']} of {progress_state['total']})"
        
        zip_url = None
        file_url = get_rel_path(folder)
        
        if req.saveMode == "zip" and not cancel_download:
            zip_path = str(folder)
            shutil.make_archive(zip_path, 'zip', str(folder))
            zip_url = get_rel_path(f"{zip_path}.zip")
            file_url = None
            
        scan_media(str(folder)) 
        progress_state["is_active"] = False
        return JSONResponse({"status": "done", "file_location": file_url, "zip_location": zip_url})
    except Exception as e:
        progress_state["is_active"] = False
        return JSONResponse({"status": "error", "error": str(e)}, status_code=500)

@app.post("/universal-download")
def universal_download(req: UniversalRequest):
    global progress_state, cancel_download
    cancel_download = False
    folder = Path(req.folderPath.strip()).resolve() if req.folderPath.strip() else get_safe_default_path("Universal")
    folder.mkdir(parents=True, exist_ok=True)
    
    progress_state = {"is_active": True, "total": 1, "completed": 0, "status": "Downloading...", "percent": "0%", "speed": "0B/s"}
    ydl_opts = {
        'outtmpl': str(folder / 'Universal_%(title)s.%(ext)s'), 'quiet': True, 'no_warnings': True, 
        'progress_hooks': [my_hook], 'concurrent_fragment_downloads': 10, 'http_chunk_size': 10485760
    }
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
        return JSONResponse({"status": "done", "file_location": get_rel_path(filename), "zip_location": None})
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

    base_folder = Path(req.save_path.strip()).resolve() if req.save_path.strip() else get_safe_default_path("YT_Shorts")
    folder_path = base_folder / f"Shorts_{uuid.uuid4().hex[:6]}"
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
            # FIXED REGEX for "23:2823 minutes"
            times = re.findall(r'\d{1,2}:\d{2}(?::\d{2})?', sub)
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
            progress_state["status"] = f"Merging Clip {i} (Lightning Fast)..."
            final_output = folder_path / f"Mehar_Viral_{i:02d}.mp4"
            if len(part_files) == 1: shutil.move(str(part_files[0]), str(final_output))
            elif len(part_files) > 1:
                list_txt = temp_folder / f"list_{i}.txt"
                with open(list_txt, "w") as f:
                    for pf in part_files: f.write(f"file '{pf.name}'\n")
                # SPEED FIX: using -c copy for instant merging!
                subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', str(list_txt), '-c', 'copy', str(final_output)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        progress_state["completed"] += 1

    try: shutil.rmtree(temp_folder)
    except: pass

    if total_extracted == 0:
        progress_state["is_active"] = False
        return JSONResponse({"status": "error", "message": "Extraction Failed."})

    zip_url = None
    file_url = get_rel_path(folder_path)

    if req.mode == "zip" and not cancel_download:
        zip_path = str(folder_path)
        shutil.make_archive(zip_path, 'zip', str(folder_path))
        zip_url = get_rel_path(f"{zip_path}.zip")
        file_url = None
        
    scan_media(str(folder_path)) 
    progress_state["is_active"] = False
    return JSONResponse({"status": "done", "file_location": file_url, "zip_location": zip_url})

@app.post("/convert-mp3-upload")
async def convert_mp3_upload(files: List[UploadFile] = File(...)):
    base_folder = get_safe_default_path("MP3_Converted")
    folder = base_folder / f"MP3_Batch_{uuid.uuid4().hex[:6]}"
    folder.mkdir(parents=True, exist_ok=True)
    converted = 0
    last_file = None
    try:
        for file in files:
            temp_file = folder / file.filename
            with open(temp_file, "wb") as buffer: shutil.copyfileobj(file.file, buffer)
            out_file = folder / f"{temp_file.stem}_Mehar.mp3"
            # SPEED FIX: -vn avoids reading video completely, making MP3 extraction instant
            subprocess.run(['ffmpeg', '-y', '-i', str(temp_file), '-vn', '-c:a', 'libmp3lame', '-q:a', '2', '-threads', '8', str(out_file)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if temp_file.exists(): temp_file.unlink()
            if out_file.exists():
                scan_media(str(out_file))
                last_file = out_file
                converted += 1
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)})

    if converted == 0:
        return JSONResponse({"status": "error", "message": "FFmpeg failed to convert."})

    zip_url = None
    file_url = get_rel_path(folder) if converted > 1 else get_rel_path(last_file)

    if len(files) > 1:
        zip_path = str(folder)
        shutil.make_archive(zip_path, 'zip', str(folder))
        zip_url = get_rel_path(f"{zip_path}.zip")

    return JSONResponse({"status": "done", "file_location": file_url, "zip_location": zip_url})

@app.post("/convert-mp3-folder")
def convert_mp3_folder(req: dict):
    folder_path = req.get("folderPath", "").strip()
    if not folder_path: return JSONResponse({"status": "error", "message": "Folder path is empty!"})
    folder = Path(folder_path).resolve()
    if not folder.exists() or not folder.is_dir(): return JSONResponse({"status": "error", "message": "Folder not found!"})
    
    mp3_folder = get_safe_default_path("MP3_Bulk_Converted") / f"Bulk_{uuid.uuid4().hex[:6]}"
    mp3_folder.mkdir(parents=True, exist_ok=True)
    converted = 0
    for file in folder.iterdir():
        if file.is_file() and file.suffix.lower() in ['.mp4', '.webm', '.mov', '.mkv', '.m4a']:
            out_file = mp3_folder / f"{file.stem}_Mehar.mp3"
            subprocess.run(['ffmpeg', '-y', '-i', str(file), '-vn', '-c:a', 'libmp3lame', '-q:a', '2', '-threads', '8', str(out_file)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            converted += 1
    
    scan_media(str(mp3_folder)) 
    
    zip_path = str(mp3_folder)
    shutil.make_archive(zip_path, 'zip', str(mp3_folder))
    zip_url = get_rel_path(f"{zip_path}.zip")
    
    return JSONResponse({"status": "done", "file_location": get_rel_path(mp3_folder), "zip_location": zip_url})

@app.post("/convert-image-format")
async def convert_image_format(files: List[UploadFile] = File(...), target_format: str = Form(...)):
    if 'PIL' not in sys.modules: return JSONResponse({"status": "error", "message": "Pillow not installed."})
    base_folder = get_safe_default_path("Image_Conversions")
    folder = base_folder / f"Images_{uuid.uuid4().hex[:6]}"
    folder.mkdir(parents=True, exist_ok=True)
    converted = 0
    last_file = None
    ext = target_format.lower()
    if ext == 'jpeg': ext = 'jpg'
    
    for file in files:
        try:
            img = Image.open(file.file)
            if target_format in ['JPEG', 'JPG'] and img.mode in ("RGBA", "P"): img = img.convert("RGB")
            out_file = folder / f"{Path(file.filename).stem}_Mehar.{ext}"
            img.save(str(out_file), format=target_format)
            scan_media(str(out_file))
            last_file = out_file
            converted += 1
        except Exception as e: pass
        
    zip_url = None
    file_url = get_rel_path(folder) if converted > 1 else get_rel_path(last_file)

    if converted > 1:
        zip_path = str(folder)
        shutil.make_archive(zip_path, 'zip', str(folder))
        zip_url = get_rel_path(f"{zip_path}.zip")
        
    return JSONResponse({"status": "done", "file_location": file_url, "zip_location": zip_url})

@app.post("/images-to-pdf")
async def images_to_pdf(files: List[UploadFile] = File(...)):
    if 'PIL' not in sys.modules: return JSONResponse({"status": "error", "message": "Pillow not installed."})
    if not files: return JSONResponse({"status": "error", "message": "No images provided."})
    folder = get_safe_default_path("PDF_Documents")
    folder.mkdir(parents=True, exist_ok=True)
    
    img_list = []
    try:
        first_img = Image.open(files[0].file).convert('RGB')
        for file in files[1:]:
            img = Image.open(file.file).convert('RGB')
            img_list.append(img)
            
        out_file = folder / f"Mehar_Doc_{uuid.uuid4().hex[:6]}.pdf"
        first_img.save(str(out_file), save_all=True, append_images=img_list)
        scan_media(str(out_file))
        return JSONResponse({"status": "done", "file_location": get_rel_path(out_file), "zip_location": None})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)})
