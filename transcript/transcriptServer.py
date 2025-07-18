from fastapi import FastAPI, File, UploadFile, Form, HTTPException
import os
import uvicorn
import logging
import json
import time
from faster_whisper import WhisperModel
from tempfile import NamedTemporaryFile

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Initialize FastAPI
app = FastAPI()

# Define model storage path
modelPath = "/var/models"

@app.post("/transcribe")
async def transcribe(
    audio: UploadFile = File(...),
    model: str = Form("turbo"),
    lang: str = Form(None)
):
    """
    Transcribes an audio file using Faster-Whisper.

    Parameters:
    - `audio`: The uploaded audio file (mp3, mp4, wav, etc.).
    - `model`: Whisper model size ("small", "medium", etc.).
    - `lang`: Language code (optional). If not provided, language will be auto-detected.

    Returns:
    - JSON response with `model`, `language`, and `transcript`.
    """
    try:
        logging.info(f"Received file: {audio.filename}, Model: {model}, Lang: {lang}")
        start_transcribe_time = time.time()
        # Save the uploaded file temporarily
        with NamedTemporaryFile(delete=False, suffix=os.path.splitext(audio.filename)[-1]) as tempFile:
            tempFilePath = tempFile.name
            tempFile.write(await audio.read())
            tempFile.flush()  # Ensure the file is written to disk
            tempFile.close()  # Close the file to release the handle

        # get file size
        fileSize = os.path.getsize(tempFilePath)
        logging.info(f"File saved at {tempFilePath}, Size: {fileSize} bytes")

        if fileSize == 0:
            logging.error("Uploaded file is empty.")
            raise HTTPException(status_code=400, detail="Application error: uploaded file is empty.")

        # Load the Whisper model
        logging.info(f"Loading model: {model} from {modelPath}")
        whisperModel = WhisperModel(model, download_root=modelPath,device="cpu", compute_type="int8")

        # Transcribe the audio
        transcribeLang = lang if lang else None  # Use provided lang or auto-detect
        logging.info(f"Starting transcription with language: {transcribeLang or 'Auto-Detect'}")
        segments, info = whisperModel.transcribe(tempFilePath, language=transcribeLang)

       
        # Get the detected language (if not provided)
        detectedLanguage = None
        if lang:
            detectedLanguage = lang
        elif info.language_probability > 0.75:
            detectedLanguage = info.language
        logging.info(f"Final language used: {detectedLanguage}")

        # Create a list of segments with timestamps and text
        segmentDetails = []
        for segment in segments:
            segmentDetails.append({
                "start": round(segment.start, 2),
                "end": round(segment.end, 2),
                "text": segment.text
            })
            #logging.info(f"[{segment.start:.2f}s -> {segment.end:.2f}s] {segment.text}")

        end_transcribe_time = time.time()
        logging.info("Transcription completed successfully in %.2f seconds", end_transcribe_time - start_transcribe_time)

        # Remove the temporary file
        os.remove(tempFilePath)
        logging.info(f"Deleted temp file: {tempFilePath}")

        # Return JSON response with timestamps
        return {
            "model": model,
            "language": detectedLanguage,
            "segments": segmentDetails
        }

    except Exception as e:
        logging.exception(f"Error during transcription: {str(e)}")
        raise HTTPException(status_code=400, detail="Application error: {}".format(str(e)))

# Run FastAPI server
if __name__ == "__main__":
    logging.info("Starting FastAPI transcription service...")
    uvicorn.run(app, host="0.0.0.0", port=8888)

