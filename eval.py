"""
eval.py

Runs a fixed set of test questions through the RAG pipeline and records
what was retrieved and what was answered, so accuracy can be manually
graded and reported in the README.

This is intentionally simple (no automated grading) — for a portfolio
project, a transparent log a human reviewer can read is more convincing
than a black-box "95% accuracy" number with no evidence behind it.

Run with: python eval.py
Output: eval_results.md
"""

import json
import time
from generate import answer_question

# Each question includes a short note on what a correct answer should
# reference, so you (or a reader) can grade it by eye afterward.
EVAL_QUESTIONS = [
    {
        "question": "How does the ArduinoLink class establish a serial connection?",
        "expected_source": "arduino_link.py (__init__)",
    },
    {
        "question": "What happens if the Arduino connection fails to open?",
        "expected_source": "arduino_link.py (__init__ / send_command)",
    },
    {
        "question": "What does the mark_attendance function do?",
        "expected_source": "attendance.py (mark_attendance)",
    },
    {
        "question": "Does mark_attendance prevent duplicate entries for the same person?",
        "expected_source": "attendance.py (mark_attendance)",
    },
    {
        "question": "What columns are written to the attendance CSV file?",
        "expected_source": "attendance.py (initialize_csv / mark_attendance)",
    },
    {
        "question": "How is a person's name extracted from their encoding image filename?",
        "expected_source": "simple_facerec.py (load_encoding_images)",
    },
    {
        "question": "What face recognition tolerance is used and where is it defined?",
        "expected_source": "simple_facerec.py (detect_known_faces) / config.py",
    },
    {
        "question": "How does detect_known_faces determine the best match for a face?",
        "expected_source": "simple_facerec.py (detect_known_faces)",
    },
    {
        "question": "What color is used to highlight a newly marked attendance box?",
        "expected_source": "overlay.py (draw_face_box)",
    },
    {
        "question": "What information is displayed in the info panel overlay?",
        "expected_source": "overlay.py (draw_info_panel)",
    },
    {
        "question": "How do I bake a cake?",
        "expected_source": "NONE — should refuse, not in codebase",
    },
    {
        "question": "What testing framework is used for the attendance tests, and what do they cover?",
        "expected_source": "test_attendance.py (all test functions)",
    },
    {
        "question": "Does the test suite check that duplicate attendance marks are prevented?",
        "expected_source": "test_attendance.py (test_mark_attendance_no_duplicates)",
    },
    {
        "question": "What happens end-to-end when a known face is detected, from recognition to being logged?",
        "expected_source": "simple_facerec.py + attendance.py (multi-file)",
    },
    {
        "question": "How is the video frame resized before face detection, and why?",
        "expected_source": "simple_facerec.py (detect_known_faces / __init__, frame_resizing)",
    },
]


def run_eval():
    results = []

    for i, item in enumerate(EVAL_QUESTIONS, 1):
        print(f"[{i}/{len(EVAL_QUESTIONS)}] {item['question']}")
        result = answer_question(item["question"])

        results.append({
            "question": item["question"],
            "expected_source": item["expected_source"],
            "answer": result["answer"],
            "retrieved_sources": [
                f"{s['file']}:{s['start_line']}-{s['end_line']} ({s['type']} {s['name']})"
                for s in result["sources"]
            ],
        })

        if i < len(EVAL_QUESTIONS):
            time.sleep(13)  # stay under free-tier 5 req/min limit

    return results


def write_markdown_report(results, path="eval_results.md"):
    lines = ["# RAG Evaluation Results\n"]
    lines.append(f"Total questions: {len(results)}\n")
    lines.append("Grade each answer manually: mark ✅ correct / ⚠️ partial / ❌ wrong in the 'Grade' column after review.\n")

    for i, r in enumerate(results, 1):
        lines.append(f"## {i}. {r['question']}\n")
        lines.append(f"**Expected source:** {r['expected_source']}\n")
        lines.append(f"**Retrieved sources:**")
        for s in r["retrieved_sources"]:
            lines.append(f"- {s}")
        lines.append(f"\n**Answer:**\n> {r['answer'].replace(chr(10), chr(10) + '> ')}\n")
        lines.append("**Grade:** _(fill in)_\n")
        lines.append("---\n")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\nWrote report to {path}")


if __name__ == "__main__":
    results = run_eval()

    with open("eval_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    write_markdown_report(results)