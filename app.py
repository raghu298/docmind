"""DocuMind - Streamlit UI. All logic lives in the docmind package."""
from __future__ import annotations

from datetime import date

import streamlit as st

from docmind import access, engine
from docmind.llm_engine import MODELS
from docmind.models import NOT_FOUND
from docmind.samples import SUGGESTED_QUESTIONS

st.set_page_config(page_title="DocuMind", page_icon="📄", layout="wide")

ss = st.session_state
# Shared state lives in non-widget keys (Streamlit drops widget-keyed state when a widget
# is not rendered).
if "store" not in ss:
    ss.store = engine.DocumentStore()
    ss.chat = []            # list[Answer]
    ss.live_count = 0
    ss.unlocked = False
    ss.view = "Documents"
store: engine.DocumentStore = ss.store
today = date.today()


def _secrets():
    try:
        return dict(st.secrets)
    except Exception:  # no secrets file locally
        return {}


secrets = _secrets()

# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.title("📄 DocuMind")
    st.caption("Ask your documents. Get cited answers. Never a made-up one.")

    mode_label = st.radio("Mode", ["Demo (offline)", "Live (Claude)"])
    live = mode_label.startswith("Live")
    settings = engine.Settings()
    if live:
        model = st.selectbox("Model", MODELS)
        user_key = st.text_input("Your Anthropic API key (optional)", type="password")
        if access.owner_access_configured(secrets) and not ss.unlocked and not user_key:
            code = st.text_input("Access code", type="password",
                                 help="Ask the app owner for the access code.")
            if code:
                if access.check_access_code(secrets, code):
                    ss.unlocked = True
                    st.success(access.ACCESS_GRANTED_MESSAGE)
                else:
                    st.error(access.ACCESS_DENIED_MESSAGE)
        elif ss.unlocked:
            st.success("Live mode unlocked with the owner's key.")
        key = access.resolve_key(secrets, user_key, ss.unlocked)
        settings = engine.Settings.from_inputs("live", model, key or "", env={})
        if not settings.has_key:
            st.warning("No key yet — questions will be answered in Demo mode.")
        st.caption(f"Live requests this session: {ss.live_count}/{access.LIVE_REQUEST_CAP}")

    st.divider()
    st.subheader("Documents")
    if st.button("📥 Load sample documents", width="stretch"):
        engine.load_samples(store, today)
    files = st.file_uploader("Upload .pdf / .txt / .md", type=["pdf", "txt", "md"],
                             accept_multiple_files=True)
    for f in files or []:
        if f.name not in store.docs:
            engine.add_upload(store, f.name, f.getvalue())
    for msg in store.rejected:
        st.error(msg)
    store.rejected.clear()
    for d in engine.list_documents(store):
        c1, c2 = st.columns([5, 1])
        flag = "" if d.readable else " ⚠️ no text"
        c1.markdown(f"**{d.name}**{flag}  \n<small>{d.doc_type} · {engine.human_size(d.size_bytes)}</small>",
                    unsafe_allow_html=True)
        if c2.button("✕", key=f"rm-{d.name}", help="Remove"):
            engine.remove_document(store, d.name)
            ss.chat = []
            st.rerun()

    with st.expander("ℹ️ About / how it works"):
        st.markdown(
            "- **Demo mode** works offline with no key: BM25 keyword search over document "
            "passages, and regex extraction of dates and ₹ amounts.\n"
            "- **Live mode** sends your full documents to Claude (long-context grounding).\n"
            "- **No fabrication:** every answer cites a document and an exact passage. Each "
            "quote is checked against the real document text; unverifiable quotes are removed, "
            "and if nothing remains you get *Not found in your documents*.\n"
            "- Nothing is stored — documents live only in this browser session.")


def quote(text: str) -> str:
    """Markdown blockquote that keeps every line of a multi-line passage inside the quote."""
    return "\n".join("> " + line for line in text.strip().splitlines())


def live_allowed() -> bool:
    if settings.mode != "live" or not settings.has_key:
        return True
    if not access.can_make_live_request(ss.live_count):
        st.warning(access.cap_message())
        return False
    return True


def effective_settings() -> engine.Settings:
    if settings.mode == "live" and settings.has_key and not access.can_make_live_request(ss.live_count):
        return engine.Settings()  # cap reached: fall back to Demo
    return settings


# ------------------------------------------------------------------ header
st.title("📄 DocuMind")
st.caption("Personal document intelligence — contracts, bills, insurance, warranties.")

docs = engine.list_documents(store)
if not docs:
    st.info("Load the sample documents or upload your own (in the sidebar) to get started.")
    if st.button("📥 Load sample documents", key="load-main"):
        engine.load_samples(store, today)
        st.rerun()
    st.stop()

dls = engine.deadlines(store, settings, today)
m1, m2, m3, m4 = st.columns(4)
m1.metric("Documents", len(docs))
m2.metric("Due within 30 days", sum(d.status == "within_30" for d in dls))
m3.metric("Overdue", sum(d.status == "overdue" for d in dls))
m4.metric("Facts extracted", engine.fact_count(store, settings))

# A stable widget key: passing default=ss.view made Streamlit treat the control as a new widget
# whenever the view changed, so every switch after the first needed two clicks. Clicking the active
# option deselects it, so the last real choice is kept in ss.view.
if ss.get("view_sel") is None:
    ss.view_sel = ss.view


def _on_view() -> None:
    if ss.view_sel is None:
        ss.view_sel = ss.view
    else:
        ss.view = ss.view_sel


st.segmented_control("View", ["Documents", "Deadlines", "Ask"], key="view_sel", on_change=_on_view,
                     label_visibility="collapsed")

# ------------------------------------------------------------------ Documents
if ss.view == "Documents":
    if settings.mode == "live" and settings.has_key:
        pending = engine.pending_live_summaries(store, settings)
        if pending and st.button(f"✨ Extract with Claude ({len(pending)} documents)"):
            if live_allowed():
                with st.spinner("Claude is reading your documents..."):
                    for n in engine.ensure_live_summaries(store, settings):
                        st.info(n)
                ss.live_count = access.next_count(ss.live_count)
                st.rerun()
    for d in docs:
        if not d.readable:
            st.warning(f"{d.name}: no readable text (scanned PDFs are not supported).")
            continue
        sm = engine.cached_summary(store, d.name, settings)
        with st.container(border=True):
            st.markdown(f"### {d.name}")
            st.caption(f"{sm.doc_type} · extracted by {'Claude' if sm.produced_by == 'live' else 'Demo mode'}")
            for n in sm.notices:
                st.caption(f"ℹ️ {n}")
            cols = st.columns(4)
            for col, title, facts in zip(cols, ["👥 Parties", "📅 Dates", "₹ Amounts", "📌 Obligations"],
                                         [sm.parties, sm.dates, sm.amounts, sm.obligations]):
                col.markdown(f"**{title}**")
                if not facts:
                    col.caption("None found")
                for f in facts:
                    val = engine.format_inr(f.amount_inr) if f.amount_inr is not None else f.value
                    with col.expander(f"{f.label}: {val}"[:80]):
                        st.markdown(quote(f.source_quote))

# ------------------------------------------------------------------ Deadlines
elif ss.view == "Deadlines":
    st.subheader("Upcoming deadlines")
    if not dls:
        st.info("No deadlines found in your documents.")
    icon = {"overdue": "🔴", "within_30": "🟠", "later": "🟢"}
    for d in dls:
        with st.container(border=True):
            a, b, c = st.columns([3, 2, 2])
            a.markdown(f"{icon[d.status]} **{d.label}**  \n<small>{d.doc_name}</small>", unsafe_allow_html=True)
            b.markdown(f"**{d.date.strftime('%d %b %Y')}**  \n{engine.days_text(d.days_remaining)}")
            c.markdown(f"`{d.status_text}`")
            with st.expander("Source passage"):
                st.markdown(quote(d.source_quote))

# ------------------------------------------------------------------ Ask
else:
    st.subheader("Ask your documents")
    chips = None
    if any(d.source == "sample" for d in docs):
        chips = st.pills("Try:", SUGGESTED_QUESTIONS, selection_mode="single", key=f"chips-{len(ss.chat)}")
    else:
        st.caption("Ask about what is in your documents, e.g. *When does my policy expire?* or "
                   "*What is the cancellation rule?*")
    if settings.mode != "live":
        st.caption("Demo mode finds the best matching passage by keywords. For written answers to "
                   "questions about long documents, switch to **Live (Claude)**.")
    question = st.chat_input("Ask anything about your documents...")
    question = question or chips
    if question:
        use = effective_settings()
        if use.mode == "live" and use.has_key and not live_allowed():
            use = engine.Settings()
        with st.spinner("Searching your documents..."):
            ans = engine.ask(store, question, use)
        if use.mode == "live" and use.has_key and ans.mode == "live":
            ss.live_count = access.next_count(ss.live_count)
        ss.chat.append(ans)
        st.rerun()

    for ans in reversed(ss.chat):
        with st.chat_message("user"):
            st.write(ans.question)
        with st.chat_message("assistant"):
            if not ans.found:
                st.warning(f"🚫 **{NOT_FOUND}** — DocuMind does not guess.")
            else:
                st.write(ans.text)
                by_doc: dict[str, list[str]] = {}
                for c in ans.citations:
                    by_doc.setdefault(c.doc_name, []).append(c.quote)
                for i, (name, quotes) in enumerate(by_doc.items()):
                    label = f"📎 {name}" + (f" ({len(quotes)} passages)" if len(quotes) > 1 else "")
                    with st.expander(label, expanded=(ans.mode == "demo" and i == 0)):
                        st.markdown("\n\n".join(quote(q) for q in quotes))
            tag = "Claude" if ans.mode == "live" else "Demo mode"
            st.caption(f"Answered by {tag}" + (" (fallback)" if ans.fell_back else ""))
            for n in ans.notices:
                st.caption(f"ℹ️ {n}")
