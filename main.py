import os
import httpx
import io
from dotenv import load_dotenv
import soundfile as sf
from openai import (OpenAI,OpenAIError,APIConnectionError,APITimeoutError,RateLimitError,AuthenticationError,APIStatusError,)
import sounddevice as sd
load_dotenv()

def stream_speech(text):
    api = os.getenv("FISH_AUDIO_API_KEY")
    if not api:
        print("FishAudio API key missing")
        raise RuntimeError("FishAudio API key missing")
        
    with httpx.Client() as client:
        res = client.post(
            "https://api.fish.audio/v1/tts",
            headers={
                "Authorization": f"Bearer {api}",
                "Content-Type": "application/json",
                "model": "s2.1-pro-free",
            },
            json={
                "text": text,
                "format": "mp3",
            },
            timeout=30,
        )
    res.raise_for_status()
    audio, sample_rate = sf.read(io.BytesIO(res.content),dtype="float32")
    # Play the audio
    sd.play(audio, sample_rate)
    sd.wait()

providers={
    "1":{
        "api":os.getenv("GROQ_API_KEY"),
        "url":"https://api.groq.com/openai/v1",
        "model":"openai/gpt-oss-20b"
    },
    "2":{
        "api":os.getenv("GEMINI_API_KEY"),
        "url":"https://generativelanguage.googleapis.com/v1beta/openai/",
        "model":"gemini-3.8-flash"
    },
    "3":{
        "api":os.getenv("OPENROUTER_API_KEY"),
        "url":"https://openrouter.ai/api/v1",
        "model":"openrouter/free"
    }
}

msg=[
    {
        "role":"system",
        "content":"You are Shadow, a personal assistant created by Developer: Ritesh Saini. You should behave natural instead of sounding too robotic. Reply in short instead of giving a full page essay. Try to sound natural instead of robotic."
    }
]

def getResponse():
    while True:
        try:
            inp=input("Enter your querry \n--> ").strip()

            if not inp:
                print("Empty Responses not allowed.")
                print()
                continue
        
        except EOFError:
            print("No input was provided.")
            print("Shadow AI turning off...")
            break
        
        except KeyboardInterrupt:
            print("\nInput cancelled by the user.")
            print("Shadow AI going off...")
            break
        
        except OSError:
            print("A system input/output error occurred.")
            print()
            continue

        exit_triggers=["exit", "turnoff", "shadow ai off", "switchoff", "quit", "turn yourself off", "off yourself"]
    
        if inp.lower().strip() in exit_triggers:
            print("Shadow AI going off...")
            break
        
        if len(msg)>6:
            del msg[1:3]
            
        msg.append({"role":"user","content":inp})
        # print("done")
        for i in providers:
            # print(providers[i]["api"])
            try:
                api_key=providers[i]["api"]
                base_url=providers[i]["url"]
                model=providers[i]["model"]

                if not api_key:
                    print(f"Skipping {model}: API key is missing.")
                    continue

                client = OpenAI(
                    api_key=api_key,
                    base_url=base_url
                )

                response=client.chat.completions.create(
                    model=providers[i]["model"],
                    messages=msg
                )

                if not response.choices:
                    print(f"No response choice recived from {model}")
                    continue

                response=response.choices[0].message.content
                if not response or not response.strip():
                    print(f"Empty response from {model}. Trying next provider.")
                    continue
                    
                print("ShadowAI: ",response,"\n")
                # msg.append({"role":"user","content":inp})
                msg.append({"role":"assistant","content":response})
                try:
                    stream_speech(response)
                    break
                    
                except httpx.HTTPStatusError as e:
                    print(f"Fish Audio HTTP error: {e.response.status_code}")
                    print(e.response.text[:500])
                    break
                
                except httpx.RequestError as e:
                    print(f"Fish Audio connection/timeout error: {e}")
                    break
                
                except Exception as e:
                    print(f"Speech playback or decoding failed: {e}")
                    break

            except RateLimitError as e:
                print(f"Rate limit or quota issue in {model}:", e)
                print()
                continue
            
            except AuthenticationError as e:
                print(f"Invalid API key or authentication failure in {model}:", e)
                print()
                continue
            
            except APITimeoutError as e:
                print(f"The API request timed out in {model}:", e)
                print()
                continue
            
            except APIConnectionError as e:
                print(f"Could not connect to the API of {model}:", e)
                print()
                continue
            
            except APIStatusError as e:
                print(f"The API returned an HTTP error in {model}:", e.status_code)
                print(e)
                print()
                continue
            
            except OpenAIError as e:
                print(f"Other OpenAI SDK error in {model}:", e)
                print()
                continue
            
        else:
            print("All Providers failed Check above for errors...")
            msg.pop()
            continue

name=r""" ____  _               _                    _    ___
/ ___|| |__   __ _  __| | _____      __    / \  |_ _|
\___ \| '_ \ / _` |/ _` |/ _ \ \ /\ / /   / _ \  | |
 ___) | | | | (_| | (_| | (_) \ V  V /   / ___ \ | |
|____/|_| |_|\__,_|\__,_|\___/ \_/\_/   /_/   \_\___|
"""

print(name)

getResponse()
