from logsGenerator import writeToFile
import platform
import subprocess
import urllib.request
from providers import providers
from openai import (OpenAI,OpenAIError,APIConnectionError,APITimeoutError,RateLimitError,AuthenticationError,APIStatusError,)
import ast
from mistralai.client import Mistral

MAX_TRIES=2

def isOnline(url="https://www.google.com", timeout=3) -> bool:
    try:
        urllib.request.urlopen(url, timeout=timeout)
        return True
    except Exception:
        return False

def getResponse(msg: list):
    TRIED=0
    while True and TRIED < MAX_TRIES:
        providers_new=providers.copy()
        for i in providers_new:
            try:
                api_key=providers[i]["api"]
                base_url=providers[i]["url"]
                model=providers[i]["model"]

                if not model:
                    writeToFile(f"Skipping {i}-----> Model name is missing.")
                    del providers[i]
                    continue
                    
                if not api_key:
                    writeToFile(f"Skipping {model}-----> API key is missing.")
                    del providers[i]
                    continue
                    
                if not base_url:
                    writeToFile(f"Skipping {model}-----> Base Url is missing.")
                    del providers[i]
                    continue    
                    
                client = OpenAI(api_key=api_key,base_url=base_url)

                response=client.chat.completions.create(
                    model=model,
                    messages=msg,
                    temperature=0.3,
                    timeout=30,
                    tools=[],
                )

                if not response.choices:
                    writeToFile(f"No response choice recived from {model}.")
                    continue
                        
                response=response.choices[0].message.content
                writeToFile(response)
                    
                if not response or not response.strip():
                    writeToFile(f"Empty response from {model}. Trying next provider.")
                    continue

                try:
                    r = ast.literal_eval(response)
                    if len(r)==2:
                        return r
                    else:
                        writeToFile(r)  
                        continue
                    
                except:
                    writeToFile(type(response))
                    continue

            except RateLimitError as e:
                writeToFile(f"Rate limit or quota issue in {model}: {e}")
                del providers[i]
                continue

            except AuthenticationError as e:
                writeToFile(f"Invalid API key or authentication failure in {model}: {e}")

                del providers[i]
                continue

            except APITimeoutError as e:
                writeToFile(f"The API request timed out in {model}: {e}")
                if isOnline():
                    continue
                else:
                    return ["No internet connection","Null"]

            except APIConnectionError as e:
                writeToFile(f"Could not connect to the API of {model}: {e}")
                continue

            except APIStatusError as e:
                writeToFile(f"The API returned an HTTP error in {model}:  {e.status_code}")
                writeToFile(e)
                continue

            except OpenAIError as e:
                writeToFile(f"Other OpenAI SDK error in {model}: {e}")
                continue

        else:
            if len(providers) > 0:
                writeToFile("All Providers failed Retrying...")
                TRIED=TRIED+1
                # continue
            else:
                writeToFile("All Providers Failed.")
                return ["All methods failed try again later.","Null"]
                
    return ["All methods failed try again later.","Null"]


if __name__ =="__main__":
    test = [
        {
            "role": "system",
            "content": (
                'STRICT RULE: Output ONLY a valid JSON array of strings matching this exact format: '
                '["Hey user, it\'s working", "Null"]. '
                'Do NOT include markdown formatting, backticks, or any additional conversational text.'
            ),
        },
        {
            "role": "user",
            "content": "Hello",
        },
    ]
    
    print(getResponse(test)[0])
