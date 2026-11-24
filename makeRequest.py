from logsGenerator import writeToFile
import platform
import subprocess
import urllib.request
from providers import sources
from openai import (OpenAI,OpenAIError,APIConnectionError,APITimeoutError,RateLimitError,AuthenticationError,APIStatusError,)
import json
MAX_TRIES=2


def isOnline(url="https://www.google.com", timeout=3) -> bool:
  try:
    urllib.request.urlopen(url, timeout=timeout)
    return True
  except:
      return False

providers=[]

def getResponse(msg: list):
  global providers
  if providers == []:
    providers = sources
  TRIED=0
  while True and TRIED < MAX_TRIES:
    for i in range(len(providers)):
      try:
        api_key=providers[i-1]["api"]
        base_url=providers[i-1]["url"]
        model=providers[i-1]["model"]
        if not model:
          writeToFile(f"Skipping {i}-----> Model name is missing.")
          del providers[i-1]
          continue
        if not api_key:
          writeToFile(f"Skipping {model}-----> API key is missing.")
          del providers[i-1]
          continue
        if not base_url:
          writeToFile(f"Skipping {model}-----> Base Url is missing.")
          del providers[i-1]
          continue
        client = OpenAI(api_key=api_key,base_url=base_url)
        response_schema = {
          "type": "json_schema",
          "json_schema": {
              "name": "assistant_response",
              "strict": True,
              "schema": {
                  "type": "object",
                  "properties": {
                      "message": {
                          "type": "string",
                          "description": "Spoken-friendly response to the user (1-2 short sentences, no markdown/lists/code)."
                      },
                      "memory": {
                          "type": "string",
                          "description": "Leave empty '' on normal turns. Output 'SAVE: <concise durable fact>' to remember across sessions, or 'FORGET: <keyword>' to erase matching memories."
                      },
                      "action": {
                          "type": "object",
                          "properties": {
                              "type": {
                                  "type": "string",
                                  "enum": ["none", "command", "search", "exit"]
                              },
                              "payload": {
                                  "type": "string",
                                  "description": "Shell command, search query, or empty string ''."
                              }
                          },
                          "required": ["type", "payload"],
                          "additionalProperties": False
                      }
                  },
                  "required": ["message", "memory", "action"],
                  "additionalProperties": False
              }
          }
      }
        response=client.chat.completions.create(
                    model=model,
                    messages=msg,
                    temperature=0.3,
                    timeout=30,
                    response_format=response_schema,
                )
        
        if not response.choices:
          writeToFile(f"No response choice recived from {model}.")
          continue

        response=response.choices[0].message.content
        writeToFile(f"ShadowAI: {response}")

        if not response or not response.strip():
          writeToFile(f"Empty response from {model}. Trying next provider.")
          continue
        try:
          r = json.loads(response)
          return r
        except:
          continue
      except RateLimitError as e:
        writeToFile(f"Error Occured with model {model}\n{e}")
        del providers[i-1]

      except AuthenticationError as e:
        writeToFile(f"Error Occured with model {model}\n{e}")
        del providers[i-1]

      except APITimeoutError as e:
        if isOnline:
          writeToFile(f"Error Occured with model {model}:\n{e}")
        else:
          writeToFile("No Internet Connection.")
          return {"message": "No Internet Connection.", "action": {"type": "none", "payload": null}}

      except APIConnectionError as e:
        if isOnline():
          writeToFile(f"Error with model {model}: {e}")
          return {"message": "Error Occured Try Again", "action": {"type": "none", "payload": null}}
        else:
          writeToFile("No Internet Connection.")
          return {"message": "No Internet Connection.", "action": {"type": "none", "payload": null}}

      except APIStatusError as e:
        writeToFile(f"Error Occured with model {model}:\n{e}")

      except OpenAIError as e:
        writeToFile(f"Error Occured with model {model}:\n{e}")
        
  return ["All methods failed try again later.", "Null"]

if __name__ =="__main__":
  test = [
        {
            "role": "system",
            "content": "This is a test.",
        },
        {
            "role": "user",
            "content": "Reply yes it's working.",
        },
    ]
  print(getResponse(test))
