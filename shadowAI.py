import os
import subprocess
import sys
from pathlib import Path
import time

def ensure_shadowAI():
  venv = Path.cwd() / ".shadowAI"
  py = venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
  if Path(sys.prefix).resolve() != venv.resolve():
    if not py.exists():
      raise FileNotFoundError("'.shadowAI' venv not found in current directory.\nRun setup again.")
    try:
      sys.exit(subprocess.run([str(py)] + sys.argv).returncode)
    except:
      exit()
ensure_shadowAI()
from logsGenerator import cleanAll, writeToFile
import speakEngine as se
import searchEngine as s
import commandEngine as ce
import promptEngine as pe
import makeRequest as mr
cleanAll()
msg=[
  {
    "role":"system",
    "content":pe.getSystemPrompt()
  }
]

def updateMSG():
  msg[0] = {
    "role":"system",
    "content":pe.getSystemPrompt()
  }

MAX_COMMANDS = 8 
MAX_SEARCHES, MAX_FAILED = 3 , 3

def main():

  def updateTempData():
    tempMSG[0] = {
    "role":"system",
    "content":pe.getSystemPrompt()
  }

  writeToFile("ShadowAI initialized successfully.")
  while True:
    if len(msg)>11:
      del msg[1:3]
    try:
      userInput = input("Enter Your Message: ").strip()
      writeToFile(f"User Input: {userInput}")
      if not userInput:
        print("Empty Message Not Allowed.")
        writeToFile("Empty message from user.")
        continue

    except EOFError:
      print("No input was provided.")
      continue

    except KeyboardInterrupt:
      writeToFile("Keyboard Intrupt")
      print("\nInput cancelled by the user.")
      print("Shadow AI going off...")
      break

    except OSError:
      writeToFile("A system input/output error occurred.")
      continue

    msg.append({"role":"user","content":f'{userInput}'})
    updateMSG()
    response = mr.getResponse(msg)
    done = set()
    COMMAND_RUN, SEARCH_DONE, FAILED_COMMAND = 0 , 0 , 0
    tempMSG = list(msg)
    facts = []
    while response['action']['type'] in ["search","command"] and ((COMMAND_RUN < MAX_COMMANDS) and (SEARCH_DONE < MAX_SEARCHES)):
      done.add(f"{response['action']['type']} : {response['action']['payload']}")
      if response['action']['type'] == "search":
        se.streamAudio(response["message"])
        result = s.searchOnline(response["action"]["payload"])
        SEARCH_DONE = SEARCH_DONE + 1
        tempMSG = tempMSG + [{
          "role":"assistant",
          "content":("Search has already been performed and the search results are given below don't search for same query again"
          "Use the search results to answer user original query or solve the errors from this."
          f"Search Result: {result}"
          )
        }
        ]
        searchQuery = response['action']['payload']
        updateTempData()
        response = mr.getResponse(tempMSG)
        facts.append({searchQuery:response["message"]})
        tempMSG = tempMSG + [
          {
            "role": "assistant",
            "content":f"{response}"
          }
        ]
        
      else:
        se.streamAudio(response["message"])
        result = ce.executeCommand(response["action"]["payload"])
        formated = ce.format_result(result)
        COMMAND_RUN = COMMAND_RUN + 1
        tempMSG = tempMSG + [
          {
            "role":"assistant",
            "content": (
              "Command Ran in the terminal and the result is given below if you get wrong output of command search for the exact command and it's parameters."
              "Don't rerun the wrong command again and again instead search for the exact or correct command."
              f"Command Result: {result}"
            )
          }
        ]
        if not result["success"]:
          FAILED_COMMAND = FAILED_COMMAND + 1
          updateTempData()
        writeToFile(f"Command Result:\n{result}")
        tempMSG = tempMSG + [
          {
            "role": "assistant",
            "content":"Command ran in terminal. Evaluate the result below:\n"
                    f"{formated}\n\n"
                    f"Already executed this turn: {done}. Do NOT rerun failing commands without changing approach. "
                    "If done, summarize with action.type='none'; otherwise run a corrective command or search."
          }
        ]
        updateTempData()
        response = mr.getResponse(tempMSG)
        facts.append(response['action']['payload'])
    
    if response["action"]["type"] == "exit":
      se.streamAudio(response['message'])
      print("ShadowAI: ",response["message"])
      sys.exit()
    else:
      print("ShadowAI: ", response["message"], "\n\n")
      msg.append({
        "role":"assistant",
        "content":(
          f"{response["message"]}"
          f"DISCOVERED/EXECUTED: {facts}"
        )
      })
      se.streamAudio(response["message"])


    # {"message": "Error Occured", "action": {"type": "none", "payload": null}}


baner=r""" ____  _               _                    _    ___
/ ___|| |__   __ _  __| | _____      __    / \  |_ _|
\___ \| '_ \ / _` |/ _` |/ _ \ \ /\ / /   / _ \  | |
 ___) | | | | (_| | (_| | (_) \ V  V /   / ___ \ | |
|____/|_| |_|\__,_|\__,_|\___/ \_/\_/   /_/   \_\___|
"""
print(baner)
main()