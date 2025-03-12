import os
import time
import sys
import glob
import subprocess
import re
import requests
from pathlib import Path

ffmpegPid = os.getenv("FFMPEG_PID")
print(f"FFMEG PID: {ffmpegPid}", flush=True)

transcriptSrv = os.getenv("TRANSCRIPT_SRV").strip('"').strip("'")
if transcriptSrv:
    url = "http://{}:8080/transcribe".format(transcriptSrv)
else:
    print("Transcription server address is missing", flush=True)
    sys.exit(0)

recordingDir = Path("./recording")
finalTranscript = os.path.join(recordingDir, "final_transcript.srt")
lang=None

def findNextSegment(lastSegment):
    while True:
        time.sleep(2)
        # Get all files not yet processed
        files = sorted(glob.glob(f"{recordingDir}/segment_*.mp4"))
        files = [f for f in files if not f.endswith(".processed.mp4")]

        for i in range(len(files) - 1):
            currentSegment = files[i]
            return currentSegment

def isProcessRunning(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, TypeError, ValueError):
        return False

lastProcessed = None

# Segment processing loop (while recording)
while isProcessRunning(ffmpegPid):
    nextSegment = findNextSegment(lastProcessed)

    if nextSegment and nextSegment != lastProcessed:
        print(f"Process {nextSegment}", flush=True)
        transcriptFile = Path(nextSegment).with_suffix(".txt")

        with open(nextSegment, "rb") as audio_file:
            files = {"audio": (nextSegment, audio_file, "audio/mpeg")}
            data = {"model": "medium", "lang": str(lang) if lang else ""}
            response = requests.post(url, files=files, data=data)

        if response.status_code == 200:
            transcriptData = response.json()
            if 'language' in transcriptData:
                lang = transcriptData['language']
            with open(str(transcriptFile), "w", encoding="utf-8") as outFile:
                for ss in transcriptData.get("segments", []):
                        outFile.write(f"[{ss['start']:.2f}s -> {ss['end']:.2f}s] {ss['text']}\n")
                        #print(f"[{ss['start']:.2f}s -> {ss['end']:.2f}s] {ss['text']}")

            # File tagging as "processed"
            processedFile = f"{os.path.splitext(nextSegment)[0]}.processed.mp4"
            os.rename(nextSegment, processedFile)

            lastProcessed = nextSegment

if ffmpegPid:
    sys.exit(0)

# Finalyze transcript (after recording)
for file in sorted(recordingDir.glob("segment_*.mp4")):
    if not  ".processed.mp4" in file.name and os.path.isfile(file):
        print(f"Process {file}", flush=True)
        transcriptFile = file.with_suffix(".txt")

        with open(file, "rb") as audio_file:
            files = {"audio": (str(file), audio_file, "audio/mpeg")}
            data = {"model": "medium", "lang": str(lang) if lang else ""}  
            response = requests.post(url, files=files, data=data)

        if response.status_code == 200:
            transcriptData = response.json()
            if 'language' in transcriptData:
                lang = transcriptData['language']
            with open(transcriptFile, "w", encoding="utf-8") as outFile:
                for ss in transcriptData.get("segments", []):
                        outFile.write(f"[{ss['start']:.2f}s -> {ss['end']:.2f}s] {ss['text']}\n")
                        #print(f"[{ss['start']:.2f}s -> {ss['end']:.2f}s] {ss['text']}")

        processedFile = f"{os.path.splitext(file)[0]}.processed.mp4"
        os.rename(file, processedFile)

# Finalize transcription (srt file)
offset = 0
index = 1
txtFiles = sorted(recordingDir.glob("segment_*.txt"))

def formatSrtTime(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"

with open(finalTranscript, "w", encoding="utf-8") as outFile:
    for file in txtFiles:
        print(f"Process {file}...")
        with open(file, "r", encoding="utf-8") as inFile:
            for line in inFile:
                match = re.match(r'\[(.*?)s -> (.*?)s\] (.*)', line)
                if match:
                    startTime = float(match.group(1)) + offset
                    endTime = float(match.group(2)) + offset
                    text = match.group(3)
                    
                    outFile.write(f"{index}\n{formatSrtTime(startTime)} --> {formatSrtTime(endTime)}\n{text}\n\n")
                    index += 1
        if endTime:
            offset = endTime

print(f"Transcription finalized in {finalTranscript}")
