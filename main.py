from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional
import subprocess
import os
import shutil
import mimetypes
import magic
from datetime import datetime, timezone
import requests
from supabase import create_client, Client
from dotenv import load_dotenv

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
    try:
        # Get content type
        mime = magic.Magic(mime=True)
        content_type = mime.from_file(file_path) or "application/octet-stream"
        
        # Read file content
        with open(file_path, "rb") as f:
            file_content = f.read()
        
        # Upload to Supabase
        response = supabase.storage.from_(SUPABASE_BUCKET).upload(
            file_name,
            file_content,
            file_options={
                "upsert": "true",
                "content-type": content_type
            }
        )
        
        # Check if upload was successful
        if hasattr(response, 'error') and response.error:
            raise Exception(f"Upload failed: {response.error}")
        
        # Get public URL
        public_url = supabase.storage.from_(SUPABASE_BUCKET).get_public_url(file_name)
        return public_url
        
    except Exception as e:
        raise Exception(f"Failed to upload to Supabase: {str(e)}")

@app.post("/")
async def upload_image(
    imageFile: UploadFile = File(...),
    fileName: Optional[str] = Form(None)
):
    temp_path = None
    try:
        # Create temp file with proper extension
        temp_path = os.path.join(TEMP_DIR, f"temp_{datetime.utcnow().timestamp()}")
        
        # Save uploaded file to temp location
        with open(temp_path, "wb") as buffer:
            # Read the entire file content
            file_content = await imageFile.read()
            buffer.write(file_content)
        
        # Verify file was written and has content
        if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
            raise Exception("Failed to save uploaded file or file is empty")
        
        # Get file extension
        ext = get_extension(temp_path)
        
        # Generate filename
        if fileName:
            # If user provided filename, ensure it has correct extension
            if not fileName.endswith(f".{ext}"):
                fileName = f"{fileName}.{ext}"
            final_name = fileName
        else:
            final_name = get_timestamped_filename("image", ext)
        
        # Upload to Supabase
        public_url = upload_to_supabase(temp_path, final_name)
        
        return JSONResponse({
            "imageUrl": public_url,
            "fileName": final_name,
            "fileSize": os.path.getsize(temp_path),
            "contentType": magic.Magic(mime=True).from_file(temp_path)
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Clean up temp file
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

@app.post("/merge")
async def merge_audio_video_from_url(
    videoUrl: str = Form(...),
    audioUrl: str = Form(...)
):
    temp_video_path = None
    temp_audio_path = None
    output_path = None
    
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

        return JSONResponse({
            "videoUrl": public_url,
            "fileName": output_filename
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Clean up temp files
        for path in [temp_video_path, temp_audio_path, output_path]:
            if path and os.path.exists(path):
                os.remove(path)

@app.post("/video-duration-from-url")
async def get_video_duration_from_url(videoUrl: str = Form(...)):
    temp_video_path = None
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

        return JSONResponse({"duration_seconds": duration_seconds})

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Clean up temp file
        if temp_video_path and os.path.exists(temp_video_path):
            os.remove(temp_video_path)

# Add a test endpoint to verify file contents
@app.get("/test-file/{filename}")
async def test_file_info(filename: str):
    try:
        # Get file info from Supabase
        response = supabase.storage.from_(SUPABASE_BUCKET).list(path="", search=filename)
        
        if not response:
            raise HTTPException(status_code=404, detail="File not found")
        
        file_info = response[0] if response else None
        public_url = supabase.storage.from_(SUPABASE_BUCKET).get_public_url(filename)
        
        return JSONResponse({
            "filename": filename,
            "file_info": file_info,
            "public_url": public_url,
            "direct_access_url": f"https://jtzeygznrcbqubzrxjux.supabase.co/storage/v1/object/public/paulbucket/{filename}"
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))