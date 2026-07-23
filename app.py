"""
app.py

Streamlit UI for the codebase RAG assistant. Lets a user type a question
about the ingested repo and see the answer alongside the exact source
chunks (file + line numbers) used to generate it.

Run with: streamlit run app.py
"""

import streamlit as st
from generate import answer_question

st.set_page_config(page_title="Codebase Q&A Assistant", page_icon="🤖", layout="wide")

st.title("🤖 Codebase Q&A Assistant")
st.caption("Ask questions about a codebase and get answers grounded in the actual code, with exact file/line citations.")

if "history" not in st.session_state:
    st.session_state.history = []

with st.sidebar:
    st.header("About")
    st.write(
        "This assistant uses Retrieval-Augmented Generation (RAG): it searches "
        "the codebase for the most relevant functions/classes, then asks an LLM "
        "to answer using only that retrieved code — with citations."
    )
    st.write("**Stack:** sentence-transformers (embeddings), ChromaDB (vector search), Gemini (generation)")

    if st.button("Clear conversation"):
        st.session_state.history = []
        st.rerun()

question = st.chat_input("Ask a question about the codebase...")

if question:
    with st.spinner("Searching codebase and generating answer..."):
        result = answer_question(question)
    st.session_state.history.append({"question": question, "result": result})

for entry in st.session_state.history:
    with st.chat_message("user"):
        st.write(entry["question"])

    with st.chat_message("assistant"):
        st.write(entry["result"]["answer"])

        with st.expander(f"Sources used ({len(entry['result']['sources'])})"):
            for s in entry["result"]["sources"]:
                st.markdown(f"**{s['file']}** — lines {s['start_line']}-{s['end_line']} ({s['type']} `{s['name']}`)")