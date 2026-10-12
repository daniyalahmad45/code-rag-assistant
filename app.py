"""
app.py

Streamlit UI for the codebase RAG assistant. Lets a user add any Python
repo (GitHub link or .zip upload), chat with it, and see each answer
alongside the exact source chunks (file + line numbers) used to generate it.

Run with: streamlit run app.py
"""

import html
import re
import time
import uuid
from datetime import datetime
from pathlib import Path

import streamlit as st
from embed_store import COLLECTION_NAME
from generate import answer_question
from repo_loader import (
    RepoError,
    add_github_repo,
    add_zip_upload,
    load_sample_repo,
    repo_info,
    sample_is_indexed,
)

st.set_page_config(
    page_title="Codebase Q&A Assistant",
    page_icon="🤖",
    layout="centered",
    initial_sidebar_state="expanded",
)

# Logo is inlined as one line of SVG so st.markdown renders it as HTML.
LOGO_SVG = re.sub(r">\s+<", "><", (Path(__file__).parent / "assets" / "logo.svg").read_text().strip())


def logo(size: int) -> str:
    return f"<span class='logo' style='width:{size}px;height:{size}px'>{LOGO_SVG}</span>"


SAMPLE_SUGGESTIONS = [
    ("Entry point", "How does the app start?", "Walk me through what main.py does when the program starts."),
    ("Data", "How is attendance recorded?", "How does attendance.py record and store attendance?"),
    ("Vision", "How are faces recognized?", "How does simple_facerec.py detect and recognize faces?"),
    ("Hardware", "How does it talk to the Arduino?", "How does the code communicate with the Arduino?"),
]

GENERIC_SUGGESTIONS = [
    ("Overview", "What does this codebase do?", "Give me a high-level overview of what this codebase does and how it's structured."),
    ("Entry point", "Where does execution start?", "Where is the main entry point of this project and what happens when it runs?"),
    ("Structure", "What are the core classes?", "What are the most important classes in this codebase and what is each responsible for?"),
    ("Errors", "How are errors handled?", "How does this codebase handle errors and exceptions?"),
]

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap');

    :root {
        --bg: #141413;
        --surface: #1C1B19;
        --surface-2: #262522;
        --line: #302E2A;
        --text: #ECE8DF;
        --muted: #9A958A;
        --faint: #6C685F;
        --accent: #E8603C;
        --serif: 'Instrument Serif', Georgia, serif;
        --mono: 'IBM Plex Mono', ui-monospace, monospace;
        --sans: 'IBM Plex Sans', system-ui, sans-serif;
    }

    html, body, .stMarkdown, .stMarkdown p, .stMarkdown li, button { font-family: var(--sans); }
    code, pre, .stCode * { font-family: var(--mono) !important; }

    .stApp { background: var(--bg); }
    header[data-testid="stHeader"] { background: transparent; }
    #MainMenu, footer { visibility: hidden; }
    .block-container { padding-top: 2rem; padding-bottom: 9rem; max-width: 760px; }

    .label {
        font-family: var(--mono); font-size: .68rem; letter-spacing: .14em;
        text-transform: uppercase; color: var(--faint);
    }

    /* ---------- Empty state ---------- */
    .hello { text-align: center; padding: 14vh 0 2.2rem; }
    .logo { display: inline-block; flex-shrink: 0; line-height: 0; }
    .logo svg { width: 100%; height: 100%; }
    .hello .logo {
        filter: drop-shadow(0 10px 28px rgba(232, 96, 60, .35));
        animation: bob 3.2s ease-in-out infinite;
    }
    @keyframes bob { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-5px); } }
    .hello h1 {
        font-family: var(--serif); font-weight: 400; font-size: 3.2rem; line-height: 1.05;
        letter-spacing: -.01em; color: var(--text); margin: 1.1rem 0 .5rem; padding: 0;
    }
    .hello h1 em { color: var(--accent); }
    .hello p { color: var(--muted); font-size: .98rem; margin: 0; }

    .st-key-suggest div[data-testid="stButton"] > button {
        width: 100%; min-height: 78px; align-items: flex-start; justify-content: flex-start;
        text-align: left; border-radius: 14px; padding: .8rem 1rem;
        background: var(--surface); border: 1px solid var(--line); color: var(--text);
        transition: border-color .15s ease, background .15s ease;
    }
    .st-key-suggest div[data-testid="stButton"] > button:hover {
        border-color: var(--accent); background: var(--surface-2); color: var(--text);
    }
    .st-key-suggest div[data-testid="stButton"] > button > div { width: 100%; justify-content: flex-start; }
    .st-key-suggest div[data-testid="stButton"] > button p { font-size: .92rem; line-height: 1.45; text-align: left; }
    .st-key-suggest div[data-testid="stButton"] > button p strong {
        display: block; font-family: var(--mono); font-weight: 500; font-size: .66rem;
        letter-spacing: .14em; text-transform: uppercase; color: var(--accent); margin-bottom: .25rem;
    }

    /* ---------- Messages ---------- */
    .user-row { display: flex; justify-content: flex-end; margin: 1.8rem 0 1.2rem; }
    .user-bubble {
        max-width: 78%; background: var(--surface-2); border: 1px solid var(--line);
        color: var(--text); padding: .7rem 1.05rem; border-radius: 20px 20px 6px 20px;
        font-size: .98rem; line-height: 1.55; white-space: pre-wrap;
    }
    .bot-head { display: flex; align-items: center; gap: .6rem; margin-bottom: .35rem; }
    .bot-name { font-family: var(--mono); font-size: .74rem; letter-spacing: .1em; color: var(--muted); }
    .bot-meta { margin-left: auto; }

    [class*="st-key-msg_"] { padding-left: 2.15rem; }
    [class*="st-key-msg_"] .stMarkdown p, [class*="st-key-msg_"] .stMarkdown li {
        font-size: 1rem; line-height: 1.72; color: var(--text);
    }
    [class*="st-key-msg_"] .stMarkdown code {
        background: var(--surface-2); color: #F2A285; border-radius: 5px;
        padding: .08rem .32rem; font-size: .85em;
    }

    /* Footnote references */
    .refs { margin-top: .9rem; padding-top: .7rem; border-top: 1px solid var(--line); }
    .refs ol { list-style: none; counter-reset: ref; padding: 0; margin: .45rem 0 0; }
    .refs li {
        counter-increment: ref; display: flex; gap: .7rem; align-items: baseline;
        font-family: var(--mono); font-size: .78rem; padding: .16rem 0; color: var(--text);
    }
    .refs li::before { content: "[" counter(ref) "]"; color: var(--accent); min-width: 1.6rem; }
    .refs .kind { color: var(--faint); }

    div[data-testid="stExpander"] details {
        border: 1px solid var(--line); border-radius: 12px; background: var(--surface);
    }
    div[data-testid="stExpander"] summary p { font-family: var(--mono); font-size: .76rem; letter-spacing: .05em; color: var(--muted); }
    .snip-cap { font-family: var(--mono); font-size: .75rem; color: var(--muted); margin: .6rem 0 .2rem; }
    .snip-cap b { color: var(--text); font-weight: 500; }

    /* Thinking indicator */
    .thinking { display: flex; align-items: center; gap: .55rem; color: var(--muted); font-size: .9rem; }
    .thinking i {
        width: 6px; height: 6px; border-radius: 50%; background: var(--accent);
        animation: pulse 1.2s ease-in-out infinite;
    }
    .thinking i:nth-child(2) { animation-delay: .15s; }
    .thinking i:nth-child(3) { animation-delay: .3s; }
    @keyframes pulse { 0%, 80%, 100% { opacity: .25; transform: scale(.8); } 40% { opacity: 1; transform: scale(1); } }

    /* ---------- Composer ---------- */
    div[data-testid="stBottom"] > div, div[data-testid="stBottomBlockContainer"] { background: var(--bg); }
    div[data-testid="stChatInput"] > div {
        border-radius: 22px; border: 1px solid var(--line); background: var(--surface);
        box-shadow: 0 10px 30px rgba(0, 0, 0, .35);
    }
    div[data-testid="stChatInput"] > div:focus-within { border-color: #4A4740; }
    div[data-testid="stChatInput"] textarea { font-size: .98rem; color: var(--text); }
    div[data-testid="stChatInput"] button {
        border-radius: 12px; background: var(--accent); color: var(--bg);
    }
    div[data-testid="stChatInput"] button:disabled { background: var(--surface-2); color: var(--faint); }

    /* ---------- Sidebar ---------- */
    section[data-testid="stSidebar"] { background: #0F0F0E; border-right: 1px solid var(--line); }
    .brand { display: flex; align-items: center; gap: .6rem; margin-bottom: 1rem; }
    .brand-name { font-family: var(--serif); font-size: 1.45rem; line-height: 1; color: var(--text); }
    .brand-name em { color: var(--accent); }
    .brand-sub { font-family: var(--mono); font-size: .62rem; letter-spacing: .2em; color: var(--faint); margin-top: .25rem; }

    section[data-testid="stSidebar"] div[data-testid="stButton"] > button {
        justify-content: flex-start; border-radius: 10px; border: 1px solid transparent;
        background: transparent; color: var(--muted); padding: .45rem .7rem; min-height: 0;
    }
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button p {
        font-size: .86rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button:hover {
        background: var(--surface); color: var(--text);
    }
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="primary"] {
        background: var(--surface-2); color: var(--text); border-color: var(--line);
    }
    .st-key-newchat div[data-testid="stButton"] > button {
        border: 1px solid var(--line) !important; color: var(--text) !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stDownloadButton"] > button {
        border-radius: 10px; background: transparent; border: 1px solid var(--line); color: var(--muted);
    }
    .side-foot { font-size: .78rem; line-height: 1.6; color: var(--faint); }
    .side-foot code { background: transparent; color: var(--muted); padding: 0; font-size: .74rem; }

    /* Repo picker and add-repo panel */
    section[data-testid="stSidebar"] div[data-baseweb="select"] > div {
        background: var(--surface); border-color: var(--line); border-radius: 10px;
    }
    section[data-testid="stSidebar"] div[data-testid="stPopover"] button {
        justify-content: flex-start; border-radius: 10px; border: 1px dashed #4A4740;
        background: transparent; color: var(--muted);
    }
    section[data-testid="stSidebar"] div[data-testid="stPopover"] button:hover {
        border-color: var(--accent); color: var(--text);
    }
    .repo-chip {
        display: inline-block; font-family: var(--mono); font-size: .8rem; color: var(--accent);
        background: var(--surface); border: 1px solid var(--line); border-radius: 6px; padding: .05rem .4rem;
    }
    .st-key-onboard {
        background: var(--surface); border: 1px solid var(--line); border-radius: 16px; padding: 1.1rem 1.2rem;
    }
    .or-rule { display: flex; align-items: center; gap: .8rem; margin: .4rem 0; }
    .or-rule::before, .or-rule::after { content: ""; flex: 1; border-top: 1px solid var(--line); }

    @media (max-width: 640px) {
        .hello h1 { font-size: 2.3rem; }
        .user-bubble { max-width: 90%; }
        [class*="st-key-msg_"] { padding-left: 0; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------- State ----------
def new_chat():
    cid = uuid.uuid4().hex[:8]
    st.session_state.chats[cid] = {"title": "New chat", "messages": [], "repo": st.session_state.repo}
    st.session_state.current = cid


def switch_repo(collection):
    """Make a repo active; questions about it start in a fresh chat."""
    st.session_state.repo = collection
    if st.session_state.chats[st.session_state.current]["messages"]:
        new_chat()
    else:
        st.session_state.chats[st.session_state.current]["repo"] = collection


if "chats" not in st.session_state:
    # Repos a visitor adds are only listed in their own session; the sample is shared.
    st.session_state.my_repos = []
    st.session_state.repo = COLLECTION_NAME if sample_is_indexed() else None
    st.session_state.chats = {}
    new_chat()
if "pending" not in st.session_state:
    st.session_state.pending = None

# Indexes can disappear (old ones are pruned on a shared deployment), so re-check each run.
repos = {}
for name in ([COLLECTION_NAME] if sample_is_indexed() else []) + st.session_state.my_repos:
    info = repo_info(name)
    if info:
        repos[name] = info
st.session_state.my_repos = [r for r in st.session_state.my_repos if r in repos]
if st.session_state.repo not in repos:
    st.session_state.repo = next(iter(repos), None)

chat = st.session_state.chats[st.session_state.current]
if chat["repo"] not in repos:
    chat["repo"] = st.session_state.repo


# ---------- Helpers ----------
def stream_text(text: str):
    """Yield the answer word-by-word for a typing effect."""
    for word in text.split(" "):
        yield word + " "
        time.sleep(0.012)


def user_message(text: str):
    st.markdown(
        f"<div class='user-row'><div class='user-bubble'>{html.escape(text)}</div></div>",
        unsafe_allow_html=True,
    )


def bot_header(meta: str = ""):
    st.markdown(
        f"""<div class="bot-head">{logo(26)}
        <span class="bot-name">Q&amp;A ASSISTANT</span><span class="label bot-meta">{meta}</span></div>""",
        unsafe_allow_html=True,
    )


def render_sources(sources: list):
    if not sources:
        return
    items = "".join(
        f"<li><span>{html.escape(s['file'])} · L{s['start_line']}–{s['end_line']}</span>"
        f"<span class='kind'>{html.escape(s['type'])} {html.escape(s['name'])}</span></li>"
        for s in sources
    )
    st.markdown(
        f"<div class='refs'><span class='label'>Sources</span><ol>{items}</ol></div>",
        unsafe_allow_html=True,
    )
    with st.expander("Show code excerpts"):
        for i, s in enumerate(sources, 1):
            st.markdown(
                f"<div class='snip-cap'>[{i}] <b>{html.escape(s['file'])}</b> "
                f"· lines {s['start_line']}–{s['end_line']}</div>",
                unsafe_allow_html=True,
            )
            if s.get("code"):
                st.code(s["code"], language="python", line_numbers=True)


def run_indexing(task, *args):
    """Run an indexing job with live progress, then switch to the new repo."""
    with st.status("Starting…", expanded=True) as status:
        def progress(msg):
            status.update(label=msg + "…")
            st.write(msg)
        try:
            info = task(*args, progress=progress)
        except RepoError as e:
            status.update(label="Couldn't add that repo", state="error")
            st.error(str(e))
            return
        except Exception as e:
            status.update(label="Something went wrong", state="error")
            st.error(f"Indexing failed: {e}")
            return
        status.update(label=f"Indexed {info['chunks']} chunks from {info['files']} files", state="complete")

    if info["collection"] != COLLECTION_NAME and info["collection"] not in st.session_state.my_repos:
        st.session_state.my_repos.append(info["collection"])
    switch_repo(info["collection"])
    st.rerun()


def add_repo_form(prefix: str):
    github_tab, zip_tab = st.tabs(["GitHub link", "Upload .zip"])
    with github_tab:
        url = st.text_input(
            "Public GitHub repository",
            placeholder="https://github.com/owner/repo",
            key=f"{prefix}_url",
        )
        if st.button("Index repository", key=f"{prefix}_gh_go", type="primary", disabled=not url.strip()):
            run_indexing(add_github_repo, url)
    with zip_tab:
        upload = st.file_uploader("Zipped Python project", type=["zip"], key=f"{prefix}_zip")
        if st.button("Index upload", key=f"{prefix}_zip_go", type="primary", disabled=upload is None):
            run_indexing(add_zip_upload, upload.name, upload.getvalue())
    st.caption("Python files only · up to 50 MB · indexing takes under a minute for most repos.")


def export_markdown(c: dict) -> str:
    lines = [f"# {c['title']}\n"]
    for m in c["messages"]:
        lines.append(f"**You:** {m['question']}\n")
        lines.append(f"**Assistant:** {m['result']['answer']}\n")
        for s in m["result"]["sources"]:
            lines.append(f"- `{s['file']}:{s['start_line']}-{s['end_line']}` ({s['type']} {s['name']})")
        lines.append("\n---\n")
    return "\n".join(lines)


# ---------- Sidebar ----------
with st.sidebar:
    st.markdown(
        f"<div class='brand'>{logo(38)}<div><div class='brand-name'>Codebase <em>Q&amp;A</em></div>"
        "<div class='brand-sub'>ASSISTANT</div></div></div>",
        unsafe_allow_html=True,
    )
    with st.container(key="newchat"):
        if st.button("New chat", icon=":material/edit_square:", width="stretch"):
            if chat["messages"]:
                new_chat()
            st.session_state.pending = None
            st.rerun()

    st.markdown("<div class='label' style='margin:1.2rem 0 .4rem'>Repository</div>", unsafe_allow_html=True)
    if repos:
        st.session_state.repo_select = st.session_state.repo
        st.selectbox(
            "Repository",
            options=list(repos),
            format_func=lambda c: repos[c]["name"],
            key="repo_select",
            label_visibility="collapsed",
            on_change=lambda: switch_repo(st.session_state.repo_select),
        )
    with st.popover("Add a repository", icon=":material/add:", width="stretch"):
        add_repo_form("side")

    past = [(cid, c) for cid, c in reversed(st.session_state.chats.items()) if c["messages"]]
    if past:
        st.markdown("<div class='label' style='margin:1.2rem 0 .4rem .7rem'>Recent</div>", unsafe_allow_html=True)
        for cid, c in past:
            is_current = cid == st.session_state.current
            if st.button(c["title"], key=f"chat_{cid}", width="stretch",
                         type="primary" if is_current else "secondary"):
                st.session_state.current = cid
                if c["repo"] in repos:
                    st.session_state.repo = c["repo"]
                st.rerun()

    if chat["messages"]:
        st.write("")
        st.download_button(
            "Export this chat",
            data=export_markdown(chat),
            file_name="codebase_qa_chat.md",
            mime="text/markdown",
            icon=":material/download:",
            width="stretch",
        )

    st.markdown(
        """
        <div style='height:1.5rem'></div>
        <div class='label' style='margin-bottom:.4rem'>How it works</div>
        <div class='side-foot'>
            Questions are embedded with <code>sentence-transformers</code>, matched against the
            repo in <code>ChromaDB</code>, and answered by <code>Gemini</code> using only the
            retrieved code, with every claim cited to a file and line range.
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------- First run: nothing indexed yet ----------
if not repos:
    st.markdown(
        f"""
        <div class="hello" style="padding-top:8vh">
            {logo(72)}
            <h1>Point me at a <em>codebase</em>.</h1>
            <p>Add any public Python repo from GitHub, or upload one as a .zip, then ask it anything.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.container(key="onboard"):
        add_repo_form("main")
        st.markdown("<div class='or-rule label'>or</div>", unsafe_allow_html=True)
        if st.button("Try the sample repo (face-recognition attendance)", icon=":material/play_arrow:", width="stretch"):
            run_indexing(load_sample_repo)
    st.chat_input("Add a repository to start asking questions", disabled=True)
    st.stop()

# ---------- Empty state ----------
active = repos[chat["repo"]]
if not chat["messages"] and not st.session_state.pending:
    st.markdown(
        f"""
        <div class="hello">
            {logo(72)}
            <h1>What shall we <em>read</em> today?</h1>
            <p>Ask anything about <span class="repo-chip">{html.escape(active['name'])}</span>. Answers come with line-level sources.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    suggestions = SAMPLE_SUGGESTIONS if chat["repo"] == COLLECTION_NAME else GENERIC_SUGGESTIONS
    with st.container(key="suggest"):
        cols = st.columns(2)
        for i, (tag, label, prompt) in enumerate(suggestions):
            if cols[i % 2].button(f"**{tag}**\n\n{label}", key=f"sugg_{i}", width="stretch"):
                st.session_state.pending = prompt
                st.rerun()

# ---------- Conversation ----------
for i, m in enumerate(chat["messages"]):
    user_message(m["question"])
    bot_header(f"{m['time']} · {m['elapsed']:.1f}s")
    with st.container(key=f"msg_{st.session_state.current}_{i}"):
        st.markdown(m["result"]["answer"])
        render_sources(m["result"]["sources"])

typed = st.chat_input(f"Ask about {active['name']}…")
question = typed or st.session_state.pending
st.session_state.pending = None

if question:
    user_message(question)
    bot_header()
    with st.container(key=f"msg_{st.session_state.current}_{len(chat['messages'])}"):
        thinking = st.empty()
        thinking.markdown(
            "<div class='thinking'><i></i><i></i><i></i>&nbsp;Reading the codebase</div>",
            unsafe_allow_html=True,
        )
        start = time.time()
        try:
            result = answer_question(question, collection_name=chat["repo"])
        except Exception as e:
            thinking.empty()
            st.error(f"Couldn't produce an answer: {e}")
            st.stop()
        elapsed = time.time() - start
        thinking.empty()
        st.write_stream(stream_text(result["answer"]))
        render_sources(result["sources"])

    if not chat["messages"]:
        chat["title"] = question if len(question) <= 40 else question[:38].rstrip() + "…"
    chat["messages"].append(
        {
            "question": question,
            "result": result,
            "time": datetime.now().strftime("%H:%M"),
            "elapsed": elapsed,
        }
    )
    st.rerun()
