# -*- coding: utf-8 -*-


import os
import re
import json
from typing import List, Dict, Optional

import requests


FULL_ENDPOINT = "https://api-gateway.netdb.csie.ncku.edu.tw/api/generate"
MODEL_NAME = "gpt-oss:20b"

# Windows PowerShell:
#   $env:LEXIGUARD_API_KEY="your key"
# Linux/macOS:
#   export LEXIGUARD_API_KEY="your key"
API_KEY = os.environ.get("LEXIGUARD_API_KEY", "")


class LLMClient:
    """
    使用 Ollama /api/generate 的簡單 client。

    POST /api/generate
    body:
      {
        "model": "gpt-oss:20b",
        "prompt": "...",
        "stream": false
      }

    回傳 JSON 中的 data["response"] 為模型輸出文字
    """

    def __init__(self,
                 endpoint: str = FULL_ENDPOINT,
                 api_key: str = API_KEY,
                 model: str = MODEL_NAME):
        self.endpoint = endpoint
        self.api_key = api_key
        self.model = model

        if not self.api_key:
            raise ValueError("找不到 API KEY：請先設定環境變數 LEXIGUARD_API_KEY")

    def _generate(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        resp = requests.post(self.endpoint, headers=headers, json=payload, timeout=300)
        resp.raise_for_status()
        data = resp.json()
        return (data.get("response") or "").strip()

    def analyze_clause(self, clause_text: str) -> Dict:
        """
        對「單一條款」呼叫 LLM，請它回傳一個 JSON：

        {
          "summary": ...,
          "risk_level": "低" | "中" | "高",
          "risk_type": "...",
          "risk_reason": "...",
          "suggestion": "..."
        }
        """

        system_instr = (
            "你是一名協助一般民眾閱讀合約的法律顧問。\n"
            "針對輸入的「單一合約條款」，請只輸出一個 JSON 物件，"
            "欄位為：summary, risk_level, risk_type, risk_reason, suggestion。\n"
            "限制：\n"
            "1. risk_level 必須使用繁體中文：只能是「低」、「中」、「高」三者之一。\n"
            "2. 其他欄位（summary, risk_type, risk_reason, suggestion）一律使用繁體中文，"
            "不得包含英文句子或簡體字。\n"
            "3. risk_type 請給出一個簡短的繁體中文分類，例如「自動續約風險」、「責任限制」、「資料隱私」等。\n"
            "4. 不要輸出任何解說文字、說明、Markdown，只能輸出一個純 JSON 字串。\n"
            "5. JSON 必須能被標準 JSON parser 解析（例如 Python json.loads），不要加註解、不要加反引號。\n"
        )

        user_prompt = (
            f"{system_instr}\n\n"
            "請分析以下合約條款，依規格輸出 JSON：\n"
            "----\n"
            f"{clause_text}\n"
            "----\n"
        )

        content = self._generate(user_prompt)

        try:
            parsed = json.loads(content)
            for k in ["summary", "risk_level", "risk_type", "risk_reason", "suggestion"]:
                parsed.setdefault(k, "")
            return parsed
        except json.JSONDecodeError:
            return {
                "summary": "",
                "risk_level": "未知",
                "risk_type": "",
                "risk_reason": "LLM 回傳內容不是合法 JSON；原始輸出為：" + content[:200],
                "suggestion": "",
            }

    # A) 單一條款追問
    
    def answer_followup_clause(
        self,
        clause_text: str,
        clause_analysis: Dict,
        question: str,
        history: Optional[List[Dict[str, str]]] = None,
        max_history_turns: int = 6
    ) -> str:
        """
        回傳「繁體中文」回答（非 JSON）。
        history: [{"q": "...", "a": "..."}, ...]
        """
        question = (question or "").strip()
        if not question:
            return "請先輸入你的問題。"

        sys = (
            "你是合約風險說明助理，面向一般民眾。\n"
            "你只能根據我提供的『條款原文』與『系統分析結果』回答，不可憑空補條款。\n"
            "一律使用繁體中文，不得出現英文句子或簡體字。\n"
            "禁止使用『一定違法』『保證無效』等斷言，只能用『可能涉及』『可能有風險』。\n"
            "回答要具體可操作：\n"
            "- 若使用者問原因：請用「依本條…」引用條款內容說明。\n"
            "- 若使用者問怎麼改：請提供可直接替換的條款示例文字（繁體中文）。\n"
            "- 若資訊不足：請清楚指出缺少什麼資訊，並列出要補的資料。\n"
            "請直接回答（不要 JSON、不要 Markdown）。\n"
        )

        analysis_block = (
            f"【系統分析結果】\n"
            f"- 摘要：{clause_analysis.get('summary','')}\n"
            f"- 風險等級：{clause_analysis.get('risk_level','')}\n"
            f"- 風險類型：{clause_analysis.get('risk_type','')}\n"
            f"- 風險原因：{clause_analysis.get('risk_reason','')}\n"
            f"- 建議：{clause_analysis.get('suggestion','')}\n"
        )

        hist_txt = ""
        if history:
            history = history[-max_history_turns:]
            turns = []
            for t in history:
                q = (t.get("q") or "").strip()
                a = (t.get("a") or "").strip()
                if q and a:
                    turns.append(f"使用者問：{q}\n助理答：{a}")
            if turns:
                hist_txt = "【先前追問紀錄】\n" + "\n\n".join(turns) + "\n"

        prompt = (
            f"{sys}\n"
            f"{hist_txt}"
            f"{analysis_block}\n"
            "【條款原文】\n"
            "----\n"
            f"{clause_text}\n"
            "----\n\n"
            f"【使用者問題】{question}\n"
        )

        return self._generate(prompt)


    # B) 整份合約追問聊天室
    
    def answer_followup_global(
        self,
        question: str,
        overall_summary: Dict,
        top_risky: List[Dict],
        history: Optional[List[Dict[str, str]]] = None,
        max_history_turns: int = 8
    ) -> str:
        """
        overall_summary: {"score":..., "high":..., "mid":..., "low":..., "total":...}
        top_risky: web端整理後的高風險摘要
        history: [{"q": "...", "a": "..."}, ...]
        """
        question = (question or "").strip()
        if not question:
            return "請先輸入你的問題。"

        sys = (
            "你是合約風險說明助理，面向一般民眾。\n"
            "你只能依據我提供的『總結資訊』與『高風險條款摘要』回答，不可憑空補合約內容。\n"
            "一律使用繁體中文，不得出現英文句子或簡體字。\n"
            "禁止使用『一定違法』『保證無效』等斷言，只能用『可能涉及』『可能有風險』。\n"
            "回答請以條列方式，並給出可執行的下一步（例如談判優先順序、要補齊的資訊）。\n"
            "請直接回答（不要 JSON、不要 Markdown）。\n"
        )

        hist_txt = ""
        if history:
            history = history[-max_history_turns:]
            turns = []
            for t in history:
                q = (t.get("q") or "").strip()
                a = (t.get("a") or "").strip()
                if q and a:
                    turns.append(f"使用者問：{q}\n助理答：{a}")
            if turns:
                hist_txt = "【聊天室紀錄】\n" + "\n\n".join(turns) + "\n"

        summary_txt = (
            "【整體總結】\n"
            f"- 有效條款數：{overall_summary.get('total','')}\n"
            f"- 整體風險分數：{overall_summary.get('score','')}/100\n"
            f"- 高風險：{overall_summary.get('high','')}\n"
            f"- 中風險：{overall_summary.get('mid','')}\n"
            f"- 低風險：{overall_summary.get('low','')}\n"
        )

        risky_lines = ["【高風險條款摘要（僅列重點，不代表全文）】"]
        for item in (top_risky or [])[:5]:
            risky_lines.append(
                f"- 第 {item.get('idx','?')} 條｜{item.get('title','')}\n"
                f"  類型：{item.get('risk_type','')}\n"
                f"  風險原因：{item.get('risk_reason','')}\n"
                f"  建議：{item.get('suggestion','')}\n"
                f"  摘錄：{item.get('clause_excerpt','')}"
            )
        risky_txt = "\n".join(risky_lines)

        prompt = (
            f"{sys}\n"
            f"{hist_txt}"
            f"{summary_txt}\n\n"
            f"{risky_txt}\n\n"
            f"【使用者問題】{question}\n"
        )

        return self._generate(prompt)


# 條款切分相關

def is_trivial_clause(text: str) -> bool:
    """
    判斷這段是不是「沒什麼內容」的條款，可以略過不送給 LLM。
    """
    s = (text or "").strip()
    if not s:
        return True
    if s == "---":
        return True

    lines = [ln.strip() for ln in s.splitlines() if ln.strip()]
    if not lines:
        return True

    first = lines[0]
    if first.startswith("###") and len(lines) == 1:
        return True
    if first.startswith("**") and first.endswith("**") and len(lines) == 1:
        return True

    han = len(re.findall(r"[\u4e00-\u9fff]", s))
    if han < 4 and len(s) < 20:
        return True

    return False


def detect_style(text: str):
    has_article = bool(re.search(r'第\s*[一二三四五六七八九十0-9]+\s*條', text))
    has_chinese_num = bool(re.search(r'^[一二三四五六七八九十]+\s*[、．.]', text, re.M))
    return has_article, has_chinese_num


def is_clause_start(line: str, has_article: bool, has_chinese_num: bool) -> bool:
    s = (line or "").strip()
    if not s:
        return False

    if has_article and re.match(r'^#{0,6}\s*第\s*[一二三四五六七八九十0-9]+\s*條', s):
        return True

    if has_chinese_num and re.match(r'^[一二三四五六七八九十]+\s*[、．.]', s):
        return True

    if not has_article and not has_chinese_num:
        if re.match(r'^\d+\s*[\.．]', s):
            return True
        if re.match(r'^[（(]?\s*[一二三四五六七八九十0-9]+\s*[)）]', s):
            return True

    return False


def segment_clauses(text: str) -> List[str]:
    normalized = re.sub(r'\r\n', '\n', text or "")
    has_article, has_chinese_num = detect_style(normalized)
    lines = normalized.split('\n')

    clauses: List[str] = []
    buf: List[str] = []

    for line in lines:
        if is_clause_start(line, has_article, has_chinese_num) and buf:
            clause_text = "\n".join(buf).strip()
            if clause_text:
                clauses.append(clause_text)
            buf = [line]
        else:
            buf.append(line)

    last = "\n".join(buf).strip()
    if last:
        clauses.append(last)

    # 丟掉最前面的抬頭（如果沒有「第 X 條」或「一、」等字樣）
    if len(clauses) >= 2:
        first = clauses[0]
        if not re.search(r'第\s*[一二三四五六七八九十0-9]+\s*條', first) and \
           not re.search(r'^[一二三四五六七八九十]+\s*[、．.]', first, re.M):
            clauses = clauses[1:]

    clauses = [c for c in clauses if not is_trivial_clause(c)]
    return clauses


# 風險等級與報告


def normalize_risk_level(lv: str) -> str:
    if lv is None:
        return "未知"
    s = str(lv).strip()
    mapping = {
        "low": "低", "Low": "低", "LOW": "低",
        "medium": "中", "Medium": "中", "MEDIUM": "中",
        "high": "高", "High": "高", "HIGH": "高",
        "低": "低", "中": "中", "高": "高",
    }
    return mapping.get(s, s if s else "未知")


def analyze_document(clauses: List[str],
                     llm: LLMClient,
                     progress_callback=None) -> List[Dict]:
    results: List[Dict] = []
    total = len(clauses)

    for i, c in enumerate(clauses, start=1):
        if progress_callback is not None:
            progress_callback(i, total)

        analysis = llm.analyze_clause(c)
        lv_norm = normalize_risk_level(analysis.get("risk_level", ""))

        results.append({
            "clause": c,
            "summary": analysis.get("summary", ""),
            "risk_level": lv_norm,
            "risk_type": analysis.get("risk_type", ""),
            "risk_reason": analysis.get("risk_reason", ""),
            "suggestion": analysis.get("suggestion", ""),
        })

    return results


def compute_overall_risk_score(results: List[Dict]) -> int:
    score_map = {"低": 1, "中": 3, "高": 5}

    scores = []
    for r in results:
        lvl = normalize_risk_level(r.get("risk_level", ""))
        if lvl in score_map:
            scores.append(score_map[lvl])

    if not scores:
        return 0

    avg = sum(scores) / len(scores)  # 1~5
    normalized = int((avg - 1) / (5 - 1) * 100)  # 0~100
    return max(0, min(100, normalized))


def create_markdown_report(results: List[Dict]) -> str:
    overall_score = compute_overall_risk_score(results)

    high_count = sum(1 for r in results if normalize_risk_level(r.get("risk_level", "")) == "高")
    med_count  = sum(1 for r in results if normalize_risk_level(r.get("risk_level", "")) == "中")
    low_count  = sum(1 for r in results if normalize_risk_level(r.get("risk_level", "")) == "低")

    lines: List[str] = []
    lines.append("# 合約風險分析報告\n")
    lines.append(f"- 條款總數：{len(results)}")
    lines.append(f"- 整體風險分數（0~100）：**{overall_score}**")
    lines.append(f"- 高風險條款數量：**{high_count}**")
    lines.append(f"- 中風險條款數量：**{med_count}**")
    lines.append(f"- 低風險條款數量：**{low_count}**")
    lines.append("\n---\n")

    for i, r in enumerate(results, start=1):
        lines.append(f"## 第 {i} 條\n")
        lines.append("**原文：**")
        lines.append("```text")
        lines.append(r["clause"])
        lines.append("```\n")

        lines.append(f"- **摘要**：{r['summary']}")
        lines.append(f"- **風險等級**：{normalize_risk_level(r['risk_level'])}")
        lines.append(f"- **風險類型**：{r['risk_type']}")
        lines.append(f"- **風險原因**：{r['risk_reason']}")
        lines.append(f"- **建議**：{r['suggestion']}")
        lines.append("\n---\n")

    return "\n".join(lines)
