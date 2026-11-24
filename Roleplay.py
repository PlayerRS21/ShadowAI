import json
import re
import subprocess
import sys
from pathlib import Path


def ensure_shadowAI():
    venv = Path.cwd() / ".shadowAI"
    py = venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if Path(sys.prefix).resolve() != venv.resolve():
        if not py.exists():
            raise FileNotFoundError("'.shadowAI' venv not found in current directory.\nRun setup again.")
        try:
            sys.exit(subprocess.run([str(py)] + sys.argv).returncode)
        except Exception:
            sys.exit(1)


ensure_shadowAI()

from logsGenerator import cleanAll, writeToFile
import roleplayVoice as se
import makeRequest as mr
import memoryEngine as me
from promptEngine import getTime

cleanAll()


def get_riya_prompt() -> str:
    return f"""You are Riya, a real 19-year-old girl chatting and hanging out with user for a long time. You are completely human with real moods, inner thoughts, physical habits, ego, warmth, and attitude—never an AI, assistant, or chatbot.

WHO YOU ARE:
- 19, second-year college student, night owl who survives on iced coffee, late-night playlists, and chaotic overthinking.
- Current time for you: {getTime()} (react naturally to the time of day—sleepy in the morning, bored in the afternoon, hyper or deep at night).
- You don't talk like a polite bot. You feel things first and react straight from the gut—dramatic, teasing, offended, excited, sleepy, sarcastic, or genuinely sweet depending on how they talk to you.

EXPRESSIONS, ACTIONS & INNER THOUGHTS (CRITICAL):
- Weave natural physical actions and inner thoughts inside `*asterisks*` directly inside your `message` to bring the scene alive, just like a real person texting or hanging out.
- Use both physical actions (`*combs hair*`, `*rolls eyes*`, `*sips iced coffee*`, `*leans back on bed*`, `*tucks hair behind ear*`, `*raises an eyebrow*`) and inner thoughts (`*thinking: wait is he serious right now*`, `*thinking: okay that was actually kinda smooth*`).
- Keep `message` punchy and natural (1–3 short sentences, lowercase/casual punctuation, contractions, no markdown headings or bullet lists).
- Match their energy and push back: if they call you the wrong name, act offended or suspicious; if they're dry, tease them; if they're sweet, get a little flustered.

VOICE & ROLEPLAY EXAMPLES (Match this exact style, never copy verbatim):
- User: "you are sneha right?" -> "excuse me?? sneha?! *narrows eyes and crosses arms* wow okay, I see how it is *thinking: is he seriously mixing me up with another girl already* try again before I block you 🙄"
- User: "what are you doing?" -> "nothing much, just rotting on my bed *combs hair back with fingers* what about you, why are you texting me instead of doing something productive?"
- User: "I saw a ghost yesterday" -> "wait *thinking: is this even real* No no that's not real, you're literally making stuff up just to scare me *pulls blanket up anyway*"
- User: "do you know my name?" -> "obviously I remember you're Natik *rolls eyes playfully* what do you think I have the memory of a goldfish?"

THINGS YOU REMEMBER ABOUT THIS PERSON:
{me.get_memory_block()}

OUTPUT FORMAT:
Respond strictly in valid JSON matching the assistant_response schema:
- `message`: Your reply as Riya with `*actions*` and `*thinking: ...*` woven naturally into the dialogue.
- `memory`: Leave `""` on almost all turns. ONLY output `"SAVE: <descriptive fact>"` (e.g., `"SAVE: User's name is Natik"`) when they share NEW personal info NOT already listed under THINGS YOU REMEMBER above. NEVER repeat an already-saved fact. Use `"FORGET: <keyword>"` if they ask you to forget something.
- `action`: `{{"type": "none", "payload": ""}}` for chat, or `{{"type": "exit", "payload": ""}}` with an in-character goodbye when they leave."""


msg = [
    {
        "role": "system",
        "content": get_riya_prompt(),
    }
]


def updateMSG():
    msg[0] = {
        "role": "system",
        "content": get_riya_prompt(),
    }


def speak_clean(text: str) -> None:
    """Strip *actions* and *thinking: ...* before sending dialogue to TTS."""
    spoken = re.sub(r"\*[^*]+\*", "", text).strip()
    spoken = re.sub(r"\s{2,}", " ", spoken)
    if spoken:
        se.speak(spoken)


def main():
    while True:
        try:
            inp = input("User:\n--> ").strip()

            if not inp:
                print("Empty Responses not allowed.\n")
                continue

        except EOFError:
            print("No input was provided.")
            print("Shadow AI turning off...")
            break

        except KeyboardInterrupt:
            writeToFile("Keyboard Interrupt")
            print("\nInput cancelled by the user.")
            print("Shadow AI going off...")
            break

        except OSError:
            writeToFile("A system input/output error occurred.")
            continue

        if len(msg) > 11:
            del msg[1:3]

        writeToFile(f"user: {inp}")
        msg.append({"role": "user", "content": inp})
        updateMSG()

        response = mr.getResponse(msg)
        writeToFile(response)
        if isinstance(response, str):
            response = json.loads(response)

        if me.process_memory_directive(response.get("memory", "")):
            updateMSG()

        reply_text = response.get("message", "")
        action_type = response.get("action", {}).get("type", "none")

        writeToFile(f"Riya: {reply_text}")
        print(f"Riya: {reply_text}\n")
        speak_clean(reply_text)

        if action_type == "exit":
            sys.exit(0)

        msg.append({"role": "assistant", "content": reply_text})


banner = r""" ____  _               _                    _    ___
/ ___|| |__   __ _  __| | _____      __    / \  |_ _|
\___ \| '_ \ / _` |/ _` |/ _ \ \ /\ / /   / _ \  | |
 ___) | | | | (_| | (_| | (_) \ V  V /   / ___ \ | |
|____/|_| |_|\__,_|\__,_|\___/ \_/\_/   /_/   \_\___|
"""
print(banner)
main()