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
    url = "http://{}/transcribe".format(transcriptSrv)
else:
    print("Transcription server address is missing", flush=True)
    sys.exit(0)

recordingDir = Path("./recording")
finalTranscript = os.path.join(recordingDir, "final_transcript.srt")
lang=None

def audioToTranscript(data, file):
    timeout = 100
    retryDelay = 2
    response = None
    start_time = time.time()
    while True:
        try:
            response = requests.post(url, files=file, data=data)
            break
        except requests.RequestException as e:
            if time.time() - start_time > timeout:
                break
            time.sleep(retryDelay)
    return response

# Load blacklist from a file
blacklistFile = f"{recordingDir}/blacklist.txt"
try:
    with open(blacklistFile, "r", encoding="utf-8") as file:
        blacklist = [line.strip() for line in file.readlines() if line.strip()]
except FileNotFoundError:
    blacklist = []
if blacklist:
    for bl in blacklist:
        print("In blacklist: {}".format(bl), flush=True)
else:
    print("No blacklist found", flush=True)

# Check if a segment is allowed (not containing blacklisted words/phrases)
def isSegmentAllowed(segmentText, blacklist):
    inText = segmentText.lstrip()
    return not any(blacklisted == inText for blacklisted in blacklist)

def segementDuration(file):
    import subprocess
    secs = subprocess.check_output(f'ffprobe -v error -select_streams v:0 \
                                    -show_entries stream=duration -of default=noprint_wrappers=1:nokey=1 "{file}"',
                                    shell=True).decode()
    return float(secs.rstrip())

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
            fileIn = {"audio": (nextSegment, audio_file, "audio/mpeg")}
            data = {"model": "turbo", "lang": str(lang) if lang else ""}
            response = audioToTranscript(data, fileIn)

        if response and response.status_code == 200:
            transcriptData = response.json()
            if 'language' in transcriptData:
                lang = transcriptData['language']
            with open(str(transcriptFile), "w", encoding="utf-8") as outFile:
                for ss in transcriptData.get("segments", []):
                        if isSegmentAllowed(ss['text'], blacklist):
                            outFile.write(f"[{ss['start']:.2f}s -> {ss['end']:.2f}s] {ss['text']}\n")

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
            fileIn = {"audio": (str(file), audio_file, "audio/mpeg")}
            data = {"model": "turbo", "lang": str(lang) if lang else ""}
            response = audioToTranscript(data, fileIn)

        if response and response.status_code == 200:
            transcriptData = response.json()
            if 'language' in transcriptData:
                lang = transcriptData['language']
            with open(transcriptFile, "w", encoding="utf-8") as outFile:
                for ss in transcriptData.get("segments", []):
                        if isSegmentAllowed(ss['text'], blacklist):
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
            offset += segementDuration(f"{recordingDir}/{Path(file).stem}.processed.mp4")

print(f"Transcription finalized in {finalTranscript}")

