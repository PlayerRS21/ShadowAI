import asyncio
import io
import edge_tts
import soundfile as sf
import sounddevice as sd
from logsGenerator import writeToFile
import os
import httpx

skip = False

def streamAudio(text):
    global skip
    if skip:
        asyncio.run(speak(text))
        return
        
    global written
    written = False

    api = os.getenv("FISH_AUDIO_API_KEY")

    if not api:
        if written:
            return

        writeToFile("FishAudio API key missing ------> Switching to default")
        written = True
        asyncio.run(speak(text))
        return


    url = "https://api.fish.audio/v1/tts"
    headers = {
        "Authorization": f"Bearer {api}",
        "Content-Type": "application/json",
    }
    payload = {
        "text": text,
        "reference_id": "0b617fc096844bbe990bb4c80bce9b43",
        "format": "mp3",
    }

    
    try:

        with httpx.Client() as client:
            res = client.post(url, headers=headers, json=payload, timeout=30)

        res.raise_for_status()

            # Read binary bytes directly into soundfile array
        audio, sample_rate = sf.read(io.BytesIO(res.content), dtype="float32")

            # Play local audio buffer
        sd.play(audio, sample_rate)
        sd.wait()

    except httpx.HTTPStatusError as e:
        writeToFile(f"Fish Audio HTTP error: {e.response.status_code}")
        writeToFile(e.response.text[:500])
        if e.response.status_code == 402:
            skip = True
        asyncio.run(speak(text))

    except httpx.RequestError as e:
        writeToFile(f"Fish Audio connection/timeout error: {e}")
        asyncio.run(speak(response))

    except Exception as e:
        writeToFile(f"Speech playback or decoding failed: {e}")
        asyncio.run(speak(response))

async def speak(text: str) -> None:
    VOICE = "en-IN-NeerjaExpressiveNeural"
    RATE = "+10%"
    PITCH = "+5Hz"
    if not text or not text.strip():
        writeToFile("Empty text passed to speak(). Skipping.")
        return

    mp3_buffer = io.BytesIO()

    # 1. Fetch audio stream from edge-tts
    try:
        communicate = edge_tts.Communicate(
            text=text.strip(),
            voice=VOICE,
            rate=RATE,
            pitch=PITCH
        )

        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                mp3_buffer.write(chunk["data"])

    except edge_tts.exceptions.UnknownVoiceError:
        writeToFile(f"Configured voice '{VOICE}' is invalid or no longer supported.")
        return
    except (asyncio.TimeoutError, ConnectionError) as net_err:
        writeToFile(f"Network error while reaching edge-tts API: {net_err}")
        return
    except Exception as e:
        writeToFile(f"Unexpected error during edge-tts synthesis: {e}")
        return

    mp3_buffer.seek(0)
    buffer_bytes = mp3_buffer.getvalue()

    if not buffer_bytes:
        writeToFile("TTS returned an empty audio buffer.")
        return

    # 2. Decode audio buffer using soundfile
    try:
        data, samplerate = sf.read(mp3_buffer, dtype='float32')
    except sf.LibsndfileError as sf_err:
        writeToFile(f"Failed to decode MP3 stream with soundfile: {sf_err}")
        return
    except Exception as e:
        writeToFile(f"Unexpected audio decoding error: {e}")
        return

    # 3. Output to audio device
    try:
        sd.stop()  # Clear any ongoing streams
        sd.play(data, samplerate=samplerate, blocking=True)
    except sd.PortAudioError as pa_err:
        writeToFile(f"Audio playback error on sounddevice: {pa_err}")
    except Exception as e:
        writeToFile(f"Unexpected audio playback error: {e}")

if __name__=="__main__":
    print("This thing is working")
    stream_speech("This thing is working.")
