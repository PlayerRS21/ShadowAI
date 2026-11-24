import asyncio
import io
import edge_tts
import sounddevice as sd
import soundfile as sf

VOICE = "en-IN-NeerjaExpressiveNeural"  # Young Indian female
RATE = "+6%"                  # Natural conversational pace
PITCH = "+3Hz"                # Slightly brighter/younger tone


async def _play(text: str):
    buf = io.BytesIO()
    communicate = edge_tts.Communicate(text, VOICE, rate=RATE, pitch=PITCH)
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buf.write(chunk["data"])
    buf.seek(0)
    data, sr = sf.read(buf, dtype="float32")
    sd.play(data, sr)
    sd.wait()


def speak(text: str):
    """Call this function anywhere in your assistant."""
    if text and text.strip():
        asyncio.run(_play(text.strip()))


if __name__ == "__main__":
    speak("Hey! I'm ready whenever you are.")
