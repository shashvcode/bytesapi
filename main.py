from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from typing import Optional
import os
import shutil
import mimetypes
import magic
from datetime import datetime

app = FastAPI()


UPLOAD_DIR = "public_images"
DEFAULT_EXTENSION = "png"
COUNTER_FILE = os.path.join(UPLOAD_DIR, "filename_counter.txt")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app.mount("/images", StaticFiles(directory=UPLOAD_DIR), name="images")

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