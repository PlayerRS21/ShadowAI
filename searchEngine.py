import os
from dotenv import load_dotenv
from tavily import TavilyClient
from logsGenerator import writeToFile

load_dotenv()

written = False

def searchOnline(search_query):
    global written
    if written:
        return "Tavily Search Api Missing."
        
    api=os.getenv("TAVILY_SEARCH_API_KEY")
    if not api:
        writeToFile("Tavily Search API key missing ----> Skipping search")
        written = True
        return

    for i in range(2):
        try:
            client=TavilyClient(api_key=api)
            response = client.search(
                query=search_query.lower(),
                search_depth="advanced",
                include_answer=True,
                include_raw_content=False,
                max_results=3
                )
            response={
                "answer": response.get("answer", ""),
                "sources": [
                    {
                        "title": result.get("title", ""),
                        "url": result.get("url", "")
                    }
                    for result in response.get("results", [])
                    if result.get("url")
                ]
            }

            result = response["answer"] + "\n\nSources:\n"
    
            for i, source in enumerate(response["sources"], start=1):
                result += (
                    f"{i}. {source['title']}\n"
                    f"   URL: {source['url']}\n"
                )

            return "Search Results: " + str(result)

        except Exception as e:
            writeToFile(e)
            continue

    else:
        return "An error occured check logs at shadowAI_logs.txt"


if __name__=="__main__":
    print("Searching: Today's Latest News About AI")
    print(searchOnline("Today's latest news about AI"))
