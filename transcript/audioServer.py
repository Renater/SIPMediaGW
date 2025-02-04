import asyncio
import websockets
import json
import numpy as np
import os
import glob

async def handler(websocket, path):
    if not path or path == "/":
        print("Participant name not provided.")
        return
    participant_name = path.strip("/")

    # Ensure the directory exists
    output_dir = "audio_records"
    os.makedirs(output_dir, exist_ok=True)

    # Participant folder
    participant_dir = os.path.join("audio_records", participant_name)
    os.makedirs(participant_dir, exist_ok=True)

    # Get latest timestamp
    current_timestamp = get_latest_timestamp(participant_dir)
    output_file = os.path.join(participant_dir, f"{current_timestamp}.pcm") if current_timestamp else None

    try:
        async for message in websocket:
            try:
                msg = json.loads(message)
                timestamp = str(msg["start_time"])
                audio_data = np.array(msg["data"], dtype=np.int16)

                # First packet received or new "start time"
                if current_timestamp is None or current_timestamp != timestamp:
                    current_timestamp = timestamp
                    output_file = os.path.join(participant_dir, f"{timestamp}.pcm")
                    print(f"Recording audio for {participant_name} -> {output_file}")

                # Write data if file
                with open(output_file, "ab") as file:
                    file.write(audio_data.tobytes())

            except (json.JSONDecodeError, KeyError) as e:
                print(f"Invalid message from {participant_name}: {e}")

    except websockets.ConnectionClosed:
        print(f"Connection closed for participant: {participant_name}")
    except Exception as e:
        print(f"Error for participant {participant_name}: {e}")
    finally:
        print(f"Recording stopped for participant: {participant_name}")

def get_latest_timestamp(participant_dir):
    """Récupère le timestamp le plus récent parmi les fichiers du participant"""
    pcm_files = glob.glob(os.path.join(participant_dir, "*.pcm"))

    if not pcm_files:
        return None  # No existing file

    # Extract timestamps and return the latest
    timestamps = [int(os.path.basename(f).replace(".pcm", "")) for f in pcm_files]
    return str(max(timestamps))

async def main():
    async with websockets.serve(handler, "0.0.0.0", 9000):
        print("WebSocket server started")
        await asyncio.Future()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Server stopped")
