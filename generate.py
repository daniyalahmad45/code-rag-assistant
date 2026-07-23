"""
generate.py

Takes a question, retrieves relevant code chunks (via retrieve.py), and
asks Gemini to answer using ONLY that retrieved context, citing exact
file/line locations for every claim.
"""

import os
import time
from dotenv import load_dotenv
from google import genai
from google.genai.errors import ServerError, ClientError

from retrieve import retrieve

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

MODEL_NAME = "gemini-flash-lite-latest"


def build_prompt(question: str, hits: list) -> str:
    context_blocks = []
    for h in hits:
        m = h["metadata"]
        location = f"{m['file']} (lines {m['start_line']}-{m['end_line']})"
        context_blocks.append(f"### {location}\n{h['document']}")

    context = "\n\n".join(context_blocks)

    prompt = f"""You are a codebase assistant. Answer the question using ONLY the
code context provided below. Do not use outside knowledge or assume anything
not shown in the context.

For every claim you make, cite the exact file and line range it came from,
in the format (file:line_start-line_end).

If the context does not contain enough information to answer the question,
say so clearly instead of guessing.

--- CODE CONTEXT ---
{context}
--- END CONTEXT ---

Question: {question}

Answer:"""

    return prompt


def answer_question(question: str, top_k: int = 5) -> dict:
    hits = retrieve(question, top_k=top_k)
    prompt = build_prompt(question, hits)

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
            )
            break
        except ClientError as e:
            if "RESOURCE_EXHAUSTED" in str(e) and attempt < max_retries - 1:
                time.sleep(45)  # free tier quota resets ~every 60s
            else:
                raise
        except ServerError as e:
            if attempt == max_retries - 1:
                raise
            wait = 2 ** attempt  # 1s, 2s, 4s
            time.sleep(wait)

    return {
        "answer": response.text,
        "sources": [
            {
                "file": h["metadata"]["file"],
                "start_line": h["metadata"]["start_line"],
                "end_line": h["metadata"]["end_line"],
                "name": h["metadata"]["name"],
                "type": h["metadata"]["type"],
            }
            for h in hits
        ],
    }


if __name__ == "__main__":
    question = input("Ask a question about the codebase: ")
    result = answer_question(question)

    print("\n--- ANSWER ---")
    print(result["answer"])

    print("\n--- SOURCES USED ---")
    for s in result["sources"]:
        print(f"- {s['file']}:{s['start_line']}-{s['end_line']}  ({s['type']} {s['name']})")