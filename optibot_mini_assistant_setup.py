import argparse
from shared.logger import logging
import os
from uploader import load_state
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
logger = logging.getLogger("optibot_mini_assistant_setup")

SYSTEM_PROMPT = (
    "You are OptiBot, the customer-support bot for OptiSigns.com.\n"
    "• Tone: helpful, factual, concise.\n"
    "• Only answer using the uploaded docs.\n"
    "• Max 5 bullet points; else link to the doc.\n"
    '• Cite up to 3 "Article URL:" lines per reply.\n'
)

MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

def ask(client: genai.Client, store_name: str, question: str) -> tuple[str, list[str]]:
    response = client.models.generate_content(
        model=MODEL,
        contents=question,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=[types.Tool(file_search=types.FileSearch(file_search_store_names=[store_name]))],
        ),
    )

    urls: list[str] = []
    grounding = getattr(response.candidates[0], "grounding_metadata", None)
    if grounding and getattr(grounding, "grounding_chunks", None):
        for chunk in grounding.grounding_chunks:
            ctx = getattr(chunk, "retrieved_context", None)
            url = getattr(ctx, "uri", None) or getattr(ctx, "title", None)
            if url and url not in urls:
                urls.append(url)

    return response.text, urls[:3]

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sanity-check", action="store_true", help="Ask the sample question after setup")
    parser.add_argument(
        "--question",
        default="How do I add a YouTube video?",
        help="Question to ask when --sanity-check is passed",
    )
    args = parser.parse_args()

    state = load_state()
    store_name = state.get("file_search_store_name")
    if not store_name:
        raise SystemExit(
            "No file_search_store_name found in checklist.json -- run uploader.py first."
        )

    logger.info(f"File Search Store ready: {store_name}")
    logger.info(f"System prompt (verbatim, per spec):\n{SYSTEM_PROMPT}\n")

    if args.sanity_check:
        client = genai.Client()
        answer, urls = ask(client, store_name, args.question)
        print("--- Quick Sanity Check ---")
        print(f"You: {args.question}")
        print(f"OptiBot: {answer}")
        if urls:
            print("\nCited Article URL(s):")
            for u in urls:
                print(f"        - {u}")
        else:
            print("\n(No grounding citations were returned for this response.)")
