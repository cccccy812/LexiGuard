# -*- coding: utf-8 -*-
"""
LexiGuard 網頁版（Streamlit）
只負責：
- 上傳檔案
- 呼叫 lexiguard_core 的函式
- 顯示結果 + 提供報告下載
"""

import pdfplumber
import streamlit as st

from lexiguard_core import (
    LLMClient,
    segment_clauses,
    analyze_document,
    compute_overall_risk_score,
    create_markdown_report,
    normalize_risk_level,   # 如果你想顯示中文風險等級，可以一起匯入
)


def load_text_from_upload(uploaded_file) -> str:
    """
    從 Streamlit 的上傳物件讀取 txt / pdf 內容，回傳字串。
    """
    if uploaded_file is None:
        return ""

    filename = uploaded_file.name.lower()

    if filename.endswith(".txt"):
        return uploaded_file.getvalue().decode("utf-8", errors="ignore")

    if filename.endswith(".pdf"):
        text_pages = []
        with pdfplumber.open(uploaded_file) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                text_pages.append(page_text)
        return "\n".join(text_pages)

    raise ValueError("目前只支援 .txt 或 .pdf")


def main():
    st.set_page_config(page_title="LexiGuard 合約風險分析器", layout="wide")
    st.title("LexiGuard：AI合約風險分析器")

    uploaded_file = st.file_uploader("上傳合約檔案（支援 .txt / .pdf）", type=["txt", "pdf"])

    if uploaded_file is not None:
        st.success(f"已上傳檔案：{uploaded_file.name}")

        if st.button("開始分析"):
            try:
                text = load_text_from_upload(uploaded_file)
            except Exception as e:
                st.error(f"讀取檔案失敗：{e}")
                return

            clauses = segment_clauses(text)
            if not clauses:
                st.warning("無法從文件中切出任何『有效條款』。")
                return

            st.info(f"偵測到 {len(clauses)} 段正式條款，開始分析...")

            llm = LLMClient()

            # 用 progress bar 顯示進度，透過 core 的 progress_callback
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

            # 總覽
            overall_score = compute_overall_risk_score(results)
            high_count = sum(1 for r in results if normalize_risk_level(r["risk_level"]) == "高")
            med_count = sum(1 for r in results if normalize_risk_level(r["risk_level"]) == "中")
            low_count = sum(1 for r in results if normalize_risk_level(r["risk_level"]) == "低")

            st.subheader("分析總結")
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("條款總數", len(results))
            col2.metric("高風險條款", high_count)
            col3.metric("中風險條款", med_count)
            col4.metric("低風險條款", low_count)

            st.markdown(f"**整體風險分數：** `{overall_score} / 100`")

            # Top 3 高風險條款
            high_risk_items = [
                (i + 1, r) for i, r in enumerate(results)
                if normalize_risk_level(r["risk_level"]) == "高"
            ]
            high_risk_items = high_risk_items[:3]

            if high_risk_items:
                st.markdown("###  最高風險條款（Top 3）")
                for idx, r in high_risk_items:
                    first_line = r["clause"].split("\n")[0].strip()
                    st.markdown(f"- 第 {idx} 條：`{first_line}`（風險：高）")
            else:
                st.markdown("###  最高風險條款（Top 3）\n目前沒有偵測到高風險條款。")

            st.markdown("---")

            # 詳細條款列表
            st.subheader("各條款詳細分析")

            for i, r in enumerate(results, start=1):
                title = f"第 {i} 條｜風險：{normalize_risk_level(r['risk_level'])}｜類型：{r['risk_type'] or '（未標示）'}"
                with st.expander(title, expanded=False):
                    st.markdown("**原文：**")
                    st.code(r["clause"], language="text")
                    st.markdown(f"**摘要：** {r['summary']}")
                    st.markdown(f"**風險等級：** {normalize_risk_level(r['risk_level'])}")
                    st.markdown(f"**風險類型：** {r['risk_type']}")
                    st.markdown(f"**風險原因：** {r['risk_reason']}")
                    st.markdown(f"**建議：** {r['suggestion']}")

            # 產生 Markdown 報告並提供下載
            report_md = create_markdown_report(results)
            st.markdown("---")
            st.download_button(
                label="下載完整 Markdown 報告",
                data=report_md,
                file_name="analysis_report.md",
                mime="text/markdown",
            )


if __name__ == "__main__":
    main()
