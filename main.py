from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional
import subprocess
import os
import shutil
import mimetypes
import magic
from datetime import datetime, timezone
from dotenv import load_dotenv
import os
import requests
from supabase import create_client, Client

app = FastAPI()
load_dotenv()
print("Starting server...")

# Supabase Config
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_BUCKET = "paulbucket"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

DEFAULT_EXTENSION = "png"
TEMP_DIR = "temp_files"
os.makedirs(TEMP_DIR, exist_ok=True)

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

def get_timestamped_filename(prefix: str, ext: str):
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return f"{prefix}_{timestamp}.{ext}"

def upload_to_supabase(file_path: str, file_name: str) -> str:
    mime = magic.Magic(mime=True)
    content_type = mime.from_file(file_path) or "application/octet-stream"
    with open(file_path, "rb") as f:
        supabase.storage.from_(SUPABASE_BUCKET).upload(
            file_name,
            f,
            file_options={
                "upsert": True,
                "content-type": content_type
            }
        )
    public_url = supabase.storage.from_(SUPABASE_BUCKET).get_public_url(file_name)
    return public_url

@app.post("/")
async def upload_image(
    imageFile: UploadFile = File(...),
    fileName: Optional[str] = Form(None)
):
    try:
        temp_path = os.path.join(TEMP_DIR, f"temp_{datetime.utcnow().timestamp()}")
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(imageFile.file, buffer)

        ext = get_extension(temp_path)
        final_name = fileName or get_timestamped_filename("image", ext)

        public_url = upload_to_supabase(temp_path, final_name)
        os.remove(temp_path)

        return JSONResponse({
            "imageUrl": public_url,
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
        temp_video_path = os.path.join(TEMP_DIR, f"temp_video_{datetime.utcnow().timestamp()}.mp4")
        with open(temp_video_path, "wb") as f:
            shutil.copyfileobj(video_response.raw, f)

        # Download audio
        audio_response = requests.get(audioUrl, stream=True)
        if audio_response.status_code != 200:
            raise Exception("Failed to download audio file from URL.")
        temp_audio_path = os.path.join(TEMP_DIR, f"temp_audio_{datetime.utcnow().timestamp()}.wav")
        with open(temp_audio_path, "wb") as f:
            shutil.copyfileobj(audio_response.raw, f)

        # Output file
        output_filename = get_timestamped_filename("merged", "mp4")
        output_path = os.path.join(TEMP_DIR, output_filename)

        # Run ffmpeg
        command = [
            "ffmpeg", "-y",
            "-i", temp_video_path,
            "-i", temp_audio_path,
            "-c:v", "copy",
            "-c:a", "aac",
            "-shortest",
            output_path
        ]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        if result.returncode != 0:
            raise Exception(result.stderr.decode())

        # Upload final video
        public_url = upload_to_supabase(output_path, output_filename)

        # Clean up
        os.remove(temp_video_path)
        os.remove(temp_audio_path)
        os.remove(output_path)

        return JSONResponse({
            "videoUrl": public_url,
            "fileName": output_filename
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/video-duration-from-url")
async def get_video_duration_from_url(videoUrl: str = Form(...)):
    try:
        response = requests.get(videoUrl, stream=True)
        if response.status_code != 200:
            raise Exception("Failed to download video file from URL.")

        temp_video_path = os.path.join(TEMP_DIR, f"temp_url_{datetime.utcnow().timestamp()}.mp4")
        with open(temp_video_path, "wb") as f:
            shutil.copyfileobj(response.raw, f)

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
        os.remove(temp_video_path)

        return JSONResponse({"duration_seconds": duration_seconds})

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))