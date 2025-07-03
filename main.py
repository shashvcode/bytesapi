from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse

app = FastAPI()

@app.post("/convert-jsproxy/")
async def convert_jsproxy(file: UploadFile = File(...)):
    try:
        contents = await file.read()  # ✅ This is now a bytes object
        byte_length = len(contents)
        return {
            "filename": file.filename,
            "byte_length": byte_length,
            "message": "JsProxy successfully received and converted to bytes."
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})