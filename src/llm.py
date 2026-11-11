
import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

def get_llm():
    api_key = os.getenv("GOOGLE_API_KEY")

    if not api_key:
        raise ValueError("GOOGLE_API_KEY not found in .env file")

    llm = ChatGoogleGenerativeAI(
    model="gemini-3.5-flash",
    google_api_key=api_key,
    temperature=0.3,
    timeout=30,
    max_retries=0,
    )

    return llm


def generate_answer(prompt):
    llm = get_llm()
    response = llm.invoke(prompt)

    if isinstance(response.content, str):
        return response.content

    return "".join(
        item["text"]
        for item in response.content
        if isinstance(item, dict) and item.get("type") == "text"
    )
