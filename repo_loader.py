"""
repo_loader.py

Lets the app index any Python repository at runtime: downloads a public
GitHub repo (or unpacks an uploaded .zip), chunks it with ingest.py, and
stores it in its own ChromaDB collection via embed_store.py.

Limits keep a public deployment from running out of disk or memory.
"""

import hashlib
import io
import os
import re
import shutil
import tempfile
import time
import urllib.error
import urllib.request
import uuid
import zipfile

from embed_store import COLLECTION_NAME, get_client, store_chunks
from ingest import ingest_repo

SAMPLE_REPO_URL = "https://github.com/daniyalahmad45/face-recognition-attendance"
SAMPLE_NAME = "Sample: face attendance"

MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024   # size of the .zip itself
MAX_PY_BYTES = 30 * 1024 * 1024         # total size of the extracted .py files
MAX_PY_FILES = 1500
MAX_CHUNKS = 4000
MAX_STORED_REPOS = 20                   # oldest user repos are deleted past this

GITHUB_URL = re.compile(
    r"^(?:https?://)?(?:www\.)?github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?(?:/tree/([^\s?#]+))?/?$"
)


class RepoError(Exception):
    """A problem the user can fix, with a message safe to show them."""


def _noop(_msg):
    pass


def parse_github_url(url: str):
    match = GITHUB_URL.match(url.strip())
    if not match:
        raise RepoError("That doesn't look like a GitHub repo link. Use the form https://github.com/owner/repo")
    owner, repo, tree = match.groups()
    ref = tree.split("/")[0] if tree else "HEAD"
    return owner, repo, ref


def download_github_zip(owner: str, repo: str, ref: str = "HEAD") -> bytes:
    url = f"https://codeload.github.com/{owner}/{repo}/zip/{ref}"
    request = urllib.request.Request(url, headers={"User-Agent": "codebase-qa-assistant"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read(MAX_DOWNLOAD_BYTES + 1)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise RepoError(f"Couldn't find {owner}/{repo}. Check the link, and note that private repos aren't supported.")
        raise RepoError(f"GitHub returned an error ({e.code}). Try again in a moment.")
    except urllib.error.URLError:
        raise RepoError("Couldn't reach GitHub. Check your connection and try again.")

    if len(data) > MAX_DOWNLOAD_BYTES:
        raise RepoError(f"That repo is larger than {MAX_DOWNLOAD_BYTES // (1024 * 1024)} MB, which is too big to index here.")
    return data


def extract_python_files(data: bytes, dest: str) -> str:
    """Unpack only the .py files from a zip into dest. Returns the repo's root folder."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise RepoError("That file isn't a valid .zip archive.")

    members = [m for m in archive.infolist() if not m.is_dir() and m.filename.endswith(".py")]
    if not members:
        raise RepoError("No Python (.py) files were found in that repository.")
    if len(members) > MAX_PY_FILES:
        raise RepoError(f"That repo has {len(members)} Python files; the limit is {MAX_PY_FILES}.")
    if sum(m.file_size for m in members) > MAX_PY_BYTES:
        raise RepoError("The Python code in that repo is too large to index here.")

    dest_real = os.path.realpath(dest)
    for member in members:
        target = os.path.realpath(os.path.join(dest, member.filename))
        if not target.startswith(dest_real + os.sep):
            continue  # skip entries that try to escape the folder ("zip slip")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with archive.open(member) as src, open(target, "wb") as out:
            shutil.copyfileobj(src, out)

    # GitHub (and most zip tools) wrap everything in one top-level folder;
    # use it as the root so citations read "src/app.py", not "repo-main/src/app.py".
    entries = os.listdir(dest)
    if len(entries) == 1 and os.path.isdir(os.path.join(dest, entries[0])):
        return os.path.join(dest, entries[0])
    return dest


def collection_name_for(display_name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", display_name).strip("-").lower()[:40] or "repo"
    digest = hashlib.sha1(display_name.encode()).hexdigest()[:8]
    return f"repo-{slug}-{digest}"


def _prune_old_repos(keep: str):
    """Delete the oldest user-added indexes so disk use stays bounded."""
    client = get_client()
    user_repos = []
    for c in client.list_collections():
        if c.name in (COLLECTION_NAME, keep):
            continue
        user_repos.append(((c.metadata or {}).get("created", 0), c.name))
    user_repos.sort()
    for _, name in user_repos[: max(0, len(user_repos) - (MAX_STORED_REPOS - 1))]:
        client.delete_collection(name)


def index_zip(data: bytes, display_name: str, collection_name: str = None, progress=_noop) -> dict:
    """Extract, chunk, embed and store a zipped repo. Returns info about the new index."""
    collection_name = collection_name or collection_name_for(display_name)
    workdir = tempfile.mkdtemp(prefix="repo_")
    try:
        progress("Unpacking Python files")
        root = extract_python_files(data, workdir)

        progress("Parsing functions and classes")
        chunks = ingest_repo(root)
        if not chunks:
            raise RepoError("No functions or classes could be parsed from that repo's Python files.")
        if len(chunks) > MAX_CHUNKS:
            raise RepoError(f"That repo produced {len(chunks)} code chunks; the limit is {MAX_CHUNKS}.")

        n_files = len({c["file"] for c in chunks})
        progress(f"Embedding {len(chunks)} chunks from {n_files} files")
        if collection_name != COLLECTION_NAME:
            _prune_old_repos(keep=collection_name)
        store_chunks(
            chunks,
            collection_name,
            metadata={"display_name": display_name, "created": time.time(), "files": n_files},
        )
        return {"collection": collection_name, "name": display_name, "files": n_files, "chunks": len(chunks)}
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def add_github_repo(url: str, progress=_noop) -> dict:
    owner, repo, ref = parse_github_url(url)
    progress(f"Downloading {owner}/{repo} from GitHub")
    data = download_github_zip(owner, repo, ref)
    return index_zip(data, f"{owner}/{repo}", progress=progress)


def add_zip_upload(filename: str, data: bytes, progress=_noop) -> dict:
    if len(data) > MAX_DOWNLOAD_BYTES:
        raise RepoError(f"That file is larger than {MAX_DOWNLOAD_BYTES // (1024 * 1024)} MB.")
    name = os.path.splitext(os.path.basename(filename))[0] or "uploaded-repo"
    # Uploads get a unique index so two people uploading "project.zip" don't overwrite each other
    return index_zip(data, name, collection_name=collection_name_for(f"{name}-{uuid.uuid4()}"), progress=progress)


def load_sample_repo(progress=_noop) -> dict:
    """Index the sample repo into the default collection (used when it's missing, e.g. on a fresh deploy)."""
    owner, repo, ref = parse_github_url(SAMPLE_REPO_URL)
    progress(f"Downloading {owner}/{repo} from GitHub")
    data = download_github_zip(owner, repo, ref)
    return index_zip(data, SAMPLE_NAME, collection_name=COLLECTION_NAME, progress=progress)


def sample_is_indexed() -> bool:
    return any(c.name == COLLECTION_NAME for c in get_client().list_collections())


def repo_info(collection_name: str):
    """Display info for an existing index, or None if it no longer exists."""
    try:
        collection = get_client().get_collection(collection_name)
    except Exception:
        return None
    metadata = collection.metadata or {}
    default_name = SAMPLE_NAME if collection_name == COLLECTION_NAME else collection_name
    return {
        "collection": collection_name,
        "name": metadata.get("display_name", default_name),
        "chunks": collection.count(),
    }
