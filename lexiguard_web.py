# -*- coding: utf-8 -*-

import pdfplumber
import streamlit as st

from lexiguard_core import (
    LLMClient,
    segment_clauses,
    analyze_document,
    compute_overall_risk_score,
    create_markdown_report,
    normalize_risk_level,
)

def load_text_from_upload(uploaded_file) -> str:
    if uploaded_file is None:
        return ""
    filename = uploaded_file.name.lower()

    if filename.endswith(".txt"):
        return uploaded_file.getvalue().decode("utf-8", errors="ignore")

    if filename.endswith(".pdf"):
        pages = []
        with pdfplumber.open(uploaded_file) as pdf:
            for page in pdf.pages:
                pages.append(page.extract_text() or "")
        return "\n".join(pages)

    raise ValueError("目前只支援 .txt 或 .pdf")


def get_clause_title(clause_text: str) -> str:
    """
    抓條款第一行當標題（過長就截斷）
    """
    first = (clause_text.split("\n")[0] if clause_text else "").strip()
    if len(first) > 60:
        first = first[:60] + "..."
    return first or "（未命名條款）"


def main():
    st.set_page_config(page_title="LexiGuard 合約風險分析器", layout="wide")
    st.title("LexiGuard：AI 合約風險分析器")

    # Session state init
    if "results" not in st.session_state:
        st.session_state["results"] = None
    if "clauses" not in st.session_state:
        st.session_state["clauses"] = None
    if "clause_qa" not in st.session_state:
        # clause_qa[i] = [{"q":..., "a":...}, ...]
        st.session_state["clause_qa"] = {}
    if "global_chat" not in st.session_state:
        st.session_state["global_chat"] = []  # [{"q":..., "a":...}...]

    uploaded_file = st.file_uploader("上傳合約檔案（支援 .txt / .pdf）", type=["txt", "pdf"])

    if uploaded_file is None:
        st.info("請先上傳合約檔案。")
        return

    st.success(f"已上傳：{uploaded_file.name}")

    if st.button("開始分析"):
        try:
            text = load_text_from_upload(uploaded_file)
            clauses = segment_clauses(text)
        except Exception as e:
            st.error(f"讀取/切分失敗：{e}")
            return

        if not clauses:
            st.warning("無法切出任何有效條款。")
            return

        st.session_state["clauses"] = clauses
        st.session_state["results"] = None
        st.session_state["clause_qa"] = {}
        st.session_state["global_chat"] = []

        st.info(f"偵測到 {len(clauses)} 段有效條款，開始分析...")

        try:
            llm = LLMClient()
        except Exception as e:
            st.error(str(e))
            return

        progress = st.progress(0.0, text="分析中...")

        def progress_cb(i, total):
            progress.progress(i / total, text=f"分析第 {i}/{total} 條...")

        try:
            results = analyze_document(clauses, llm, progress_callback=progress_cb)
        except Exception as e:
            st.error(f"分析過程發生錯誤：{e}")
            return
        finally:
            progress.empty()

        st.session_state["results"] = results
        st.success("分析完成！")

    # 如果已分析，就顯示結果
    results = st.session_state.get("results")
    clauses = st.session_state.get("clauses")

    if not results or not clauses:
        st.info("按下『開始分析』後會顯示結果。")
        return

    overall_score = compute_overall_risk_score(results)
    high_count = sum(1 for r in results if normalize_risk_level(r["risk_level"]) == "高")
    med_count  = sum(1 for r in results if normalize_risk_level(r["risk_level"]) == "中")
    low_count  = sum(1 for r in results if normalize_risk_level(r["risk_level"]) == "低")

    st.subheader("分析總結")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("條款總數", len(results))
    c2.metric("高風險", high_count)
    c3.metric("中風險", med_count)
    c4.metric("低風險", low_count)
    st.markdown(f"**整體風險分數：** `{overall_score} / 100`")

    st.markdown("---")
    st.subheader("各條款詳細分析（含單條追問）")

    llm = LLMClient()  # 追問用

    for i, r in enumerate(results, start=1):
        title_line = get_clause_title(r["clause"])
        title = f"第 {i} 條｜風險：{normalize_risk_level(r['risk_level'])}｜類型：{r['risk_type'] or '（未標示）'}｜{title_line}"

        with st.expander(title, expanded=False):
            st.markdown("**原文：**")
            st.code(r["clause"], language="text")
            st.markdown(f"**摘要：** {r['summary']}")
            st.markdown(f"**風險等級：** {normalize_risk_level(r['risk_level'])}")
            st.markdown(f"**風險類型：** {r['risk_type']}")
            st.markdown(f"**風險原因：** {r['risk_reason']}")
            st.markdown(f"**建議：** {r['suggestion']}")

            #  A) 單條追問
            st.markdown("### 針對本條追問")
            q_key = f"clause_q_{i}"
            ask_key = f"clause_ask_{i}"

            user_q = st.text_area("輸入你的問題（例如：我該怎麼改這條？）", key=q_key, height=80)

            colA, colB = st.columns([1, 5])
            with colA:
                do_ask = st.button("送出追問", key=ask_key)

            if do_ask:
                history = st.session_state["clause_qa"].get(i, [])
                ans = llm.answer_followup_clause(
                    clause_text=r["clause"],
                    clause_analysis=r,
                    question=user_q,
                    history=history
                )
                history.append({"q": user_q, "a": ans})
                st.session_state["clause_qa"][i] = history

            # 顯示追問紀錄
            history = st.session_state["clause_qa"].get(i, [])
            if history:
                st.markdown("#### 追問紀錄")
                for t in history[-6:]:
                    st.markdown(f"- **問：** {t['q']}\n\n  **答：** {t['a']}")

    st.markdown("---")

    # 下載報告
    report_md = create_markdown_report(results)
    st.download_button(
        label="下載完整 Markdown 報告",
        data=report_md,
        file_name="analysis_report.md",
        mime="text/markdown",
    )

    st.markdown("---")
    st.subheader("聊天室（針對整份合約追問）")

    #  B) 聊天室 
    # 組 top risky（最多 5 條）
    top_risky = []
    for idx, r in enumerate(results, start=1):
        if normalize_risk_level(r["risk_level"]) == "高":
            excerpt = r["clause"].replace("\n", " ")
            if len(excerpt) > 120:
                excerpt = excerpt[:120] + "..."
            top_risky.append({
                "idx": idx,
                "title": get_clause_title(r["clause"]),
                "risk_level": normalize_risk_level(r["risk_level"]),
                "risk_type": r.get("risk_type", ""),
                "risk_reason": r.get("risk_reason", ""),
                "suggestion": r.get("suggestion", ""),
                "clause_excerpt": excerpt,
            })
    top_risky = top_risky[:5]

    overall_summary = {
        "total": len(results),
        "score": overall_score,
        "high": high_count,
        "mid": med_count,
        "low": low_count
    }

    # 顯示聊天紀錄
    for item in st.session_state["global_chat"][-10:]:
        with st.chat_message("user"):
            st.write(item["q"])
        with st.chat_message("assistant"):
            st.write(item["a"])

    user_global_q = st.chat_input("輸入你對整份合約的問題（例如：我該優先改哪三條？）")

    if user_global_q:
        history = st.session_state["global_chat"]
        ans = llm.answer_followup_global(
            question=user_global_q,
            overall_summary=overall_summary,
            top_risky=top_risky,
            history=history
        )
        history.append({"q": user_global_q, "a": ans})
        st.session_state["global_chat"] = history

        with st.chat_message("user"):
            st.write(user_global_q)
        with st.chat_message("assistant"):
            st.write(ans)


if __name__ == "__main__":
    main()
