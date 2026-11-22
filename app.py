import os, uuid, shutil, subprocess, threading, json, re
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, HttpUrl

BASE = Path(__file__).parent
UPLOADS = BASE / "uploads"
OUTPUTS = BASE / "outputs"
UPLOADS.mkdir(exist_ok=True); OUTPUTS.mkdir(exist_ok=True)
JOBS = {}
security = HTTPBasic()

def require_login(credentials: HTTPBasicCredentials = Depends(security)):
    expected_user = os.getenv("CLIPCRAFT_USER", "admin")
    expected_password = os.getenv("CLIPCRAFT_PASSWORD", "")
    if not expected_password:
        raise HTTPException(status_code=503, detail="Set CLIPCRAFT_PASSWORD before starting the app.")
    user_ok = secrets.compare_digest(credentials.username, expected_user)
    pass_ok = secrets.compare_digest(credentials.password, expected_password)
    if not (user_ok and pass_ok):
        raise HTTPException(status_code=401, detail="Incorrect username or password",
                            headers={"WWW-Authenticate": "Basic"})
    return credentials

app = FastAPI(title="ClipCraft AI", dependencies=[Depends(require_login)])
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

@app.get("/")
def home():
    return FileResponse(BASE / "static" / "index.html")

@app.get("/api/health")
def health():
    return {"status": "online", "engine": "local MVP"}

class UrlRequest(BaseModel):
    url: HttpUrl
    caption_mode: str = "bilingual"

def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError((p.stderr or p.stdout)[-1800:])
    return p.stdout

def duration(path):
    out = run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(path)])
    return float(out.strip())

def process_job(job_id, source, caption_mode):
    job = JOBS[job_id]
    try:
        job.update(status="processing", progress=8, message="Preparing video…")
        # Normalize input into MP4 for predictable seeking.
        normalized = OUTPUTS / f"{job_id}_source.mp4"
        run(["ffmpeg","-y","-i",str(source),"-vf","scale='min(1920,iw)':-2","-c:v","libx264","-preset","veryfast","-c:a","aac","-movflags","+faststart",str(normalized)])
        total = duration(normalized)
        job.update(progress=22, message="Transcribing audio…")
        try:
            from faster_whisper import WhisperModel
            model = WhisperModel(os.getenv("WHISPER_MODEL","base"), device="cpu", compute_type="int8")
            segments, info = model.transcribe(str(normalized), beam_size=3, vad_filter=True)
            transcript = [{"start":float(s.start),"end":float(s.end),"text":s.text.strip()} for s in segments]
            language = info.language
        except Exception as e:
            raise RuntimeError("Speech transcription unavailable. Install faster-whisper and its system dependencies. " + str(e))
        if not transcript:
            raise RuntimeError("No speech was detected in this video.")
        job.update(progress=52, message="Finding highlight moments…", language=language)
        # Build 30–45 second windows around transcript clusters. This is a transparent
        # heuristic MVP, not a trained virality predictor.
        candidates=[]
        window = 38
        starts = list(range(0, max(1, int(total-window)+1), max(12, window//2)))
        if not starts: starts=[0]
        for st in starts:
            en=min(total, st+window)
            segs=[s for s in transcript if s["end"]>st and s["start"]<en]
            words=sum(len(s["text"].split()) for s in segs)
            if words < 12: continue
            # Score speech density + expressive punctuation + conversational hook terms.
            text=" ".join(s["text"] for s in segs)
            hook_terms=["wow","wait","look","why","how","secret","first","finally","लेकिन","क्यों","कैसे","देखो","पहली","भाई","अरे"]
            hook=sum(1 for term in hook_terms if term.lower() in text.lower())
            density=min(words/(window*2.2),1.0)
            score=min(98, round(55 + density*30 + min(hook,3)*4))
            candidates.append({"start":st,"end":en,"score":score,"transcript":text[:420]})
        candidates=sorted(candidates,key=lambda x:x["score"],reverse=True)[:8]
        if not candidates:
            candidates=[{"start":0,"end":min(total,38),"score":60,"transcript":"Speech detected; preview the moment."}]
        job.update(progress=65,message="Rendering vertical clips…",clips=[])
        rendered=[]
        for i,c in enumerate(candidates,1):
            out=OUTPUTS/f"{job_id}_clip_{i}.mp4"
            # Center crop to 9:16. For face-aware reframing, add a detector/tracker later.
            run(["ffmpeg","-y","-ss",str(c["start"]),"-i",str(normalized),"-t",str(c["end"]-c["start"]),
                 "-vf","scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
                 "-c:v","libx264","-preset","veryfast","-crf","23","-c:a","aac","-movflags","+faststart",str(out)])
            c.update(id=f"clip_{i}", filename=out.name, download=f"/api/download/{out.name}")
            rendered.append(c)
            job.update(progress=65+int(30*i/len(candidates)),clips=rendered.copy(),message=f"Rendering clip {i}/{len(candidates)}…")
        job.update(status="completed",progress=100,message="Clips ready",clips=rendered,source_language=language,
                   note="Scores are heuristic estimates based on speech density and hook words, not guaranteed virality.")
    except Exception as e:
        job.update(status="failed",message=str(e),error=str(e))

@app.post("/api/jobs/upload")
async def upload_video(file: UploadFile=File(...), caption_mode: str=Form("bilingual")):
    ext=Path(file.filename or "").suffix.lower()
    if ext not in [".mp4",".mov",".mkv",".webm",".avi"]:
        raise HTTPException(400,"Upload an MP4, MOV, MKV, WEBM or AVI video.")
    jid=uuid.uuid4().hex[:10]
    dest=UPLOADS/f"{jid}{ext}"
    with dest.open("wb") as f: shutil.copyfileobj(file.file,f)
    JOBS[jid]={"id":jid,"status":"queued","progress":0,"message":"Queued"}
    threading.Thread(target=process_job,args=(jid,dest,caption_mode),daemon=True).start()
    return {"id":jid}

@app.post("/api/jobs/youtube")
def youtube_video(req: UrlRequest):
    jid=uuid.uuid4().hex[:10]
    dest=UPLOADS/f"{jid}.%(ext)s"
    JOBS[jid]={"id":jid,"status":"downloading","progress":2,"message":"Downloading source video…"}
    def fetch():
        try:
            run(["yt-dlp","--no-playlist","-f","bv*[height<=1080]+ba/b[height<=1080]","--merge-output-format","mp4","-o",str(dest),str(req.url)])
            matches=list(UPLOADS.glob(jid+".*"))
            if not matches: raise RuntimeError("YouTube download did not produce a video file.")
            process_job(jid,matches[0],req.caption_mode)
        except Exception as e:
            JOBS[jid].update(status="failed",message=str(e),error=str(e))
    threading.Thread(target=fetch,daemon=True).start()
    return {"id":jid}

@app.get("/api/jobs/{job_id}")
def get_job(job_id:str):
    if job_id not in JOBS: raise HTTPException(404,"Job not found")
    return JOBS[job_id]

@app.get("/api/download/{filename}")
def download(filename:str):
    path=OUTPUTS/Path(filename).name
    if not path.exists(): raise HTTPException(404,"Clip not found")
    return FileResponse(path,filename=path.name,media_type="video/mp4")
