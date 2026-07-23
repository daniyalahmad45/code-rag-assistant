"""
ingest.py

Walks a target code repository, parses each Python file with the `ast`
module, and extracts chunks at function/class granularity (rather than
naive fixed-size text splitting). Each chunk carries metadata: the file
path and the exact start/end line numbers, which is what lets the final
answers cite precise locations.

Run this after cloning the target repo into ./target_repo
"""

import ast
import os
import json

TARGET_DIR = "target_repo"
OUTPUT_FILE = "chunks.json"


def get_source_segment(source_lines, node):
    """Extract the exact source text for a given AST node."""
    start = node.lineno - 1
    end = node.end_lineno
    return "\n".join(source_lines[start:end])


def chunk_file(filepath):
    """Parse one Python file and return a list of chunk dicts."""
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        source = f.read()

    try:
        tree = ast.parse(source)
    except SyntaxError:
        print(f"  Skipping (syntax error): {filepath}")
        return []

    source_lines = source.splitlines()
    chunks = []
    rel_path = filepath.replace(TARGET_DIR + os.sep, "").replace("\\", "/")

    # Module-level chunk: imports, constants, and any top-level code that
    # sits outside a function/class. This captures things like `import
    # pytest` or config constants that the function/class-level chunker
    # would otherwise miss entirely.
    top_level_lines = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            segment = get_source_segment(source_lines, node)
            top_level_lines.append(segment)

    if top_level_lines:
        chunks.append({
            "file": rel_path,
            "name": "(module level)",
            "type": "module",
            "start_line": 1,
            "end_line": tree.body[0].lineno - 1 if tree.body else len(source_lines),
            "code": "\n".join(top_level_lines),
        })

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            kind = "class" if isinstance(node, ast.ClassDef) else "function"
            code = get_source_segment(source_lines, node)

            chunks.append({
                "file": rel_path,
                "name": node.name,
                "type": kind,
                "start_line": node.lineno,
                "end_line": node.end_lineno,
                "code": code,
            })

    return chunks


def ingest_repo(target_dir=TARGET_DIR):
    """Walk the whole repo and collect chunks from every .py file."""
    all_chunks = []

    for root, dirs, files in os.walk(target_dir):
        # skip hidden/virtualenv/cache folders
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("venv", "__pycache__", "node_modules")]

        for filename in files:
            if filename.endswith(".py"):
                filepath = os.path.join(root, filename)
                print(f"Parsing: {filepath}")
                all_chunks.extend(chunk_file(filepath))

    return all_chunks


if __name__ == "__main__":
    if not os.path.isdir(TARGET_DIR):
        print(f"Error: '{TARGET_DIR}' folder not found. Clone your target repo there first, e.g.:")
        print(f"  git clone <your-repo-url> {TARGET_DIR}")
        raise SystemExit(1)

    chunks = ingest_repo()

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=2)

    print(f"\nDone. Extracted {len(chunks)} chunks (functions/classes) into {OUTPUT_FILE}")