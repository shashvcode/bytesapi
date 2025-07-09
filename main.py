from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from typing import Optional
import subprocess
import os
import shutil
import mimetypes
import magic
from datetime import datetime, timezone
import requests

app = FastAPI()


UPLOAD_DIR = "public_images"
DEFAULT_EXTENSION = "png"
COUNTER_FILE = os.path.join(UPLOAD_DIR, "filename_counter.txt")
os.makedirs(UPLOAD_DIR, exist_ok=True)

MERGE_OUTPUT_DIR = "public_videos"
os.makedirs(MERGE_OUTPUT_DIR, exist_ok=True)

app.mount("/images", StaticFiles(directory=UPLOAD_DIR), name="images")
app.mount("/videos", StaticFiles(directory=MERGE_OUTPUT_DIR), name="videos")

def get_extension(file_path: str):
    try:
        mime = magic.Magic(mime=True)
        mime_type = mime.from_file(file_path)
    except:
        mime_type, _ = mimetypes.guess_type(file_path)
    ext = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/gif": "gif",
        "image/webp": "webp",
        "image/bmp": "bmp",
        "image/svg+xml": "svg"
    }.get(mime_type, DEFAULT_EXTENSION)
    return ext

def get_next_filename(base_name: Optional[str], ext: str):
    if base_name:
        base_name = "".join(c for c in base_name if c.isalnum() or c in "-_").rstrip(".-_")
    else:
        if not os.path.exists(COUNTER_FILE):
            with open(COUNTER_FILE, "w") as f:
                f.write("1")
        with open(COUNTER_FILE, "r+") as f:
            counter = int(f.read().strip())
            base_name = f"image_{counter:05}"
            f.seek(0)
            f.write(str(counter + 1))
            f.truncate()
    return f"{base_name}.{ext}"

def get_timestamped_video_filename() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return f"merged_{timestamp}.mp4"


@app.post("/")
async def upload_image(
    imageFile: UploadFile = File(...),
    fileName: Optional[str] = Form(None)
):
    try:
        temp_path = os.path.join(UPLOAD_DIR, f"temp_{datetime.utcnow().timestamp()}")
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(imageFile.file, buffer)

        ext = get_extension(temp_path)
        final_name = get_next_filename(fileName, ext)
        final_path = os.path.join(UPLOAD_DIR, final_name)

        os.rename(temp_path, final_path)

        return JSONResponse({
            "imageUrl": f"/images/{final_name}",
            "fileName": final_name
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.post("/merge")
async def merge_audio_video_from_url(
    videoUrl: str = Form(...),
    audioUrl: str = Form(...)
):
    try:
        # Download video
        video_response = requests.get(videoUrl, stream=True)
        if video_response.status_code != 200:
            raise Exception("Failed to download video file from URL.")
        temp_video_path = os.path.join(MERGE_OUTPUT_DIR, f"temp_video_{datetime.utcnow().timestamp()}.mp4")
        with open(temp_video_path, "wb") as f:
            shutil.copyfileobj(video_response.raw, f)

        # Download audio
        audio_response = requests.get(audioUrl, stream=True)
        if audio_response.status_code != 200:
            raise Exception("Failed to download audio file from URL.")
        temp_audio_path = os.path.join(MERGE_OUTPUT_DIR, f"temp_audio_{datetime.utcnow().timestamp()}.wav")
        with open(temp_audio_path, "wb") as f:
            shutil.copyfileobj(audio_response.raw, f)

        # Output file
        output_filename = get_timestamped_video_filename()
        output_path = os.path.join(MERGE_OUTPUT_DIR, output_filename)

        # Run ffmpeg
        command = [
            "ffmpeg", "-y",
            "-i", temp_video_path,
            "-i", temp_audio_path,
            "-c:v", "copy",
            "-c:a", "aac",
            "-shortest",  # <-- Ensures the output is cut to the shortest stream (the video)
            output_path
        ]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        if result.returncode != 0:
            raise Exception(result.stderr.decode())

        return JSONResponse({
            "videoUrl": f"/videos/{output_filename}",
            "fileName": output_filename
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/video-duration-from-url")
async def get_video_duration_from_url(videoUrl: str = Form(...)):
    try:
        # Download the video from the URL
        response = requests.get(videoUrl, stream=True)
        if response.status_code != 200:
            raise Exception("Failed to download video file from URL.")
        
        # Save to temp file
        temp_video_path = os.path.join(MERGE_OUTPUT_DIR, f"temp_url_{datetime.utcnow().timestamp()}.mp4")
        with open(temp_video_path, "wb") as f:
            shutil.copyfileobj(response.raw, f)

        # Use ffprobe to get duration
        command = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            temp_video_path
        ]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            raise Exception(result.stderr.decode())

        duration_seconds = float(result.stdout.decode().strip())

        # Cleanup
        os.remove(temp_video_path)

        return JSONResponse({"duration_seconds": duration_seconds})

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/get-video-url")
async def get_video_url(fileName: str):
    try:
        video_path = os.path.join(MERGE_OUTPUT_DIR, fileName)

        if not os.path.isfile(video_path):
            raise HTTPException(status_code=404, detail="Video file not found.")

        return JSONResponse({
            "videoUrl": f"/videos/{fileName}"
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))