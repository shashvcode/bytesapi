from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from typing import Optional
import os
import shutil
import subprocess
from datetime import datetime

app = FastAPI()

UPLOAD_DIR = "public_videos"
MERGED_DIR = "merged_videos"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(MERGED_DIR, exist_ok=True)

# Serve merged videos publicly
app.mount("/videos", StaticFiles(directory=MERGED_DIR), name="videos")

def get_timestamped_filename(extension: str) -> str:
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    return f"merged_{timestamp}.{extension}"

@app.post("/merge")
async def merge_audio_video(
    audioFile: UploadFile = File(...),
    videoFile: UploadFile = File(...),
    fileName: Optional[str] = Form(None)
):
    try:
        # Save uploaded files temporarily
        audio_path = os.path.join(UPLOAD_DIR, f"temp_audio_{audioFile.filename}")
        video_path = os.path.join(UPLOAD_DIR, f"temp_video_{videoFile.filename}")

        with open(audio_path, "wb") as a:
            shutil.copyfileobj(audioFile.file, a)

        with open(video_path, "wb") as v:
            shutil.copyfileobj(videoFile.file, v)

        # Define output path
        final_name = get_timestamped_filename("mp4")
        output_path = os.path.join(MERGED_DIR, final_name)

        # Run ffmpeg to merge audio and video
        command = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", audio_path,
            "-c:v", "copy",
            "-c:a", "aac",
            output_path
        ]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        if result.returncode != 0:
            raise Exception(result.stderr.decode())

        return JSONResponse({
            "videoUrl": f"/videos/{final_name}",
            "fileName": final_name
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))