from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional
from pydantic import BaseModel
import subprocess
import os
import shutil
import mimetypes
import magic
from datetime import datetime, timezone
import requests
from supabase import create_client, Client
from dotenv import load_dotenv
from PIL import Image
from io import BytesIO
import cv2
import numpy as np

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

# Pydantic models for request bodies
class OverlayLogoRequest(BaseModel):
    base_image_url: str
    logo_image_url: str
    corner: str = "bottom-right"  # choices: "top-left", "top-right", "bottom-left", "bottom-right"

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

def get_audio_extension(file_path: str):
    try:
        mime = magic.Magic(mime=True)
        mime_type = mime.from_file(file_path)
    except:
        mime_type, _ = mimetypes.guess_type(file_path)
    
    ext = {
        "audio/mpeg": "mp3",
        "audio/mp3": "mp3",
        "audio/wav": "wav",
        "audio/wave": "wav",
        "audio/x-wav": "wav",
        "audio/aac": "aac",
        "audio/ogg": "ogg",
        "audio/flac": "flac",
        "audio/m4a": "m4a",
        "audio/mp4": "m4a",
        "audio/webm": "webm"
    }.get(mime_type, "mp3")  # Default to mp3 for audio files
    return ext

@app.post("/upload-audio")
async def upload_audio(
    audioFile: UploadFile = File(...),
    fileName: Optional[str] = Form(None)
):
    temp_path = None
    try:
        # Create temp file with proper extension
        temp_path = os.path.join(TEMP_DIR, f"temp_audio_{datetime.now(timezone.utc).timestamp()}")
        
        # Save uploaded file to temp location
        with open(temp_path, "wb") as buffer:
            # Read the entire file content
            file_content = await audioFile.read()
            buffer.write(file_content)
        
        # Verify file was written and has content
        if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
            raise Exception("Failed to save uploaded file or file is empty")
        
        # Get file extension - updated for audio files
        ext = get_audio_extension(temp_path)
        
        # Generate filename
        if fileName:
            # If user provided filename, ensure it has correct extension
            if not fileName.endswith(f".{ext}"):
                fileName = f"{fileName}.{ext}"
            final_name = fileName
        else:
            final_name = get_timestamped_filename("audio", ext)
        
        # Upload to Supabase
        public_url = upload_to_supabase(temp_path, final_name)
        
        return JSONResponse({
            "audioUrl": public_url,
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

def video_has_audio(file_path: str) -> bool:
    command = [
        "ffprobe", "-v", "error",
        "-select_streams", "a",
        "-show_entries", "stream=codec_type",
        "-of", "csv=p=0",
        file_path
    ]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return "audio" in result.stdout.decode().strip().lower()

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
        if video_has_audio(temp_video_path):
            # Mix existing voiceover + new music
            command = [
                "ffmpeg", "-y",
                "-i", temp_video_path,
                "-i", temp_audio_path,
                "-filter_complex", "[1:a]volume=0.4[a1];[0:a][a1]amix=inputs=2:duration=first:dropout_transition=2[aout]",
                "-map", "0:v",
                "-map", "[aout]",
                "-c:v", "copy",
                "-c:a", "aac",
                "-shortest",
                output_path
            ]
        else:
            # Just add background music as audio track
            command = [
                "ffmpeg", "-y",
                "-i", temp_video_path,
                "-i", temp_audio_path,
                "-map", "0:v",
                "-map", "1:a",
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
    

@app.post("/overlay-logo-url")
async def overlay_logo_url(
    request: OverlayLogoRequest = None,
    base_image_url: str = Form(None),
    logo_image_url: str = Form(None),
    corner: str = Form("bottom-right")
):
    temp_base_path = temp_logo_path = temp_output_path = None
    try:
        # Handle both JSON and form data
        if request is not None:
            # JSON request body
            actual_base_url = request.base_image_url
            actual_logo_url = request.logo_image_url
            actual_corner = request.corner
        else:
            # Form data
            if not base_image_url or not logo_image_url:
                raise HTTPException(status_code=400, detail="base_image_url and logo_image_url are required")
            actual_base_url = base_image_url
            actual_logo_url = logo_image_url
            actual_corner = corner
        
        # Download base image
        resp = requests.get(actual_base_url, timeout=10)
        if resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to fetch base image")
        base_img = Image.open(BytesIO(resp.content)).convert("RGBA")

        # Download logo image
        resp = requests.get(actual_logo_url, timeout=10)
        if resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to fetch logo image")
        logo = Image.open(BytesIO(resp.content)).convert("RGBA")

        # Resize logo (scale to 15% width of base)
        bw, bh = base_img.size
        ratio = 0.20
        nw = int(bw * ratio)
        nh = int(logo.size[1] * (nw / logo.size[0]))
        logo = logo.resize((nw, nh), Image.LANCZOS)

        # Determine position
        margin = 10
        if actual_corner == "top-left":
            pos = (margin, margin)
        elif actual_corner == "top-right":
            pos = (bw - nw - margin, margin)
        elif actual_corner == "bottom-left":
            pos = (margin, bh - nh - margin)
        else:  # "bottom-right"
            pos = (bw - nw - margin, bh - nh - margin)

        # Paste logo
        base_img.paste(logo, pos, mask=logo)

        # Save output to a temp file
        output_ext = "png"
        temp_output_path = os.path.join(TEMP_DIR, get_timestamped_filename("overlayed", output_ext))
        base_img.save(temp_output_path, format="PNG")

        # Upload to Supabase
        final_name = os.path.basename(temp_output_path)
        public_url = upload_to_supabase(temp_output_path, final_name)

        return JSONResponse({
            "outputUrl": public_url,
            "fileName": final_name
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if temp_output_path and os.path.exists(temp_output_path):
            os.remove(temp_output_path)




@app.post("/overlay_infographic2")
async def overlay_infographic2(
    base_image_url: str = Form(...),
    overlay_image_url: str = Form(...)
):
    temp_output_path = None
    try:
        # Download base image
        base_resp = requests.get(base_image_url, timeout=10)
        if base_resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to fetch base image")
        base_img = Image.open(BytesIO(base_resp.content)).convert("RGBA")

        # Download overlay image
        overlay_resp = requests.get(overlay_image_url, timeout=10)
        if overlay_resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to fetch overlay image")
        overlay_img = Image.open(BytesIO(overlay_resp.content)).convert("RGBA")

        # Calculate new size for overlay image scaled to 70% of base image size
        base_width, base_height = base_img.size
        new_width = int(base_width * 0.7)
        aspect_ratio = overlay_img.width / overlay_img.height
        new_height = int(new_width / aspect_ratio)

        # Resize overlay image maintaining aspect ratio
        overlay_resized = overlay_img.resize((new_width, new_height), Image.LANCZOS)

        # Center the overlay on base image
        pos_x = (base_width - new_width) // 2
        pos_y = (base_height - new_height) // 2

        # Paste resized overlay onto base image at centered position with transparency
        base_img.paste(overlay_resized, (pos_x, pos_y), overlay_resized)

        # Save output to temp file with your existing Supabase logic
        output_ext = "png"
        output_filename = get_timestamped_filename("overlayed", output_ext)
        temp_output_path = os.path.join(TEMP_DIR, output_filename)
        base_img.save(temp_output_path, format="PNG")

        # Upload image to Supabase
        public_url = upload_to_supabase(temp_output_path, output_filename)

        return JSONResponse({
            "outputUrl": public_url,
            "fileName": output_filename
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        if temp_output_path and os.path.exists(temp_output_path):
            os.remove(temp_output_path)
