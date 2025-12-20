# -*- coding: utf-8 -*-
"""
LexiGuard 核心模組：
- 不依賴 Streamlit
- 提供：LLMClient、segment_clauses、analyze_document、
        compute_overall_risk_score、create_markdown_report
"""

import re
import json
from typing import List, Dict


import requests

# ======================================================
# 這三個可以視情況改，但通常只在這裡維護一次就好
# ======================================================

FULL_ENDPOINT = "https://api-gateway.netdb.csie.ncku.edu.tw/api/generate"
API_KEY = "33df9458b44b43d8ea119a7da5ef9197a91f8ac445a25fdbcb7e4eff1645c536"
MODEL_NAME = "gpt-oss:20b"


# =========================
# LLM Client（用 /api/generate）
# =========================

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
    回傳：
      {
        "model": "...",
        "created_at": "...",
        "response": "這裡是模型輸出（文字）",
        "done": true,
        ...
      }
    """

    def __init__(self,
                 endpoint: str = FULL_ENDPOINT,
                 api_key: str = API_KEY,
                 model: str = MODEL_NAME):
        self.endpoint = endpoint
        self.api_key = api_key
        self.model = model

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
            "2. 其他欄位（summary, risk_type, risk_reason, suggestion）"
            "一律使用繁體中文，不得包含英文句子或簡體字。\n"
            "3. risk_type 請給出一個簡短的繁體中文分類，例如「自動續約風險」、「責任限制」、「資料隱私」等。\n"
            "4. 不要輸出任何解說文字、說明、Markdown，只能輸出一個純 JSON 字串。\n"
            "5. JSON 必須能被標準 JSON parser 解析（例如 Python json.loads），"
            "不要加註解、不要加反引號。\n"
        )

        user_prompt = (
            f"{system_instr}\n\n"
            "請分析以下合約條款，依規格輸出 JSON：\n"
            "----\n"
            f"{clause_text}\n"
            "----\n"
        )

        payload = {
            "model": self.model,
            "prompt": user_prompt,
            "stream": False,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        resp = requests.post(self.endpoint, headers=headers, json=payload, timeout=300)
        resp.raise_for_status()
        data = resp.json()

        content = data.get("response", "")

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


# =========================
# 條款切分相關
# =========================

def is_trivial_clause(text: str) -> bool:
    """
    判斷這段是不是「沒什麼內容」的條款，可以直接略過不送給 LLM。

    規則：
      - 空的 / 只有 --- 之類
      - 單獨一行標題（例如 **xxx** 或 ### xxx），且下面沒有實際內容
      - 超短的小碎片（幾個字而已）
    """
    s = text.strip()
    if not s:
        return True
    if s == "---":
        return True

    # 把非空白行拆開來看看第一行是不是只有標題
    lines = [ln.strip() for ln in s.splitlines() if ln.strip()]
    if not lines:
        return True

    first = lines[0]

    # 單獨一行 markdown 標題
    if first.startswith("###") and len(lines) == 1:
        return True
    # 單獨一行粗體標題（**xxx**）
    if first.startswith("**") and first.endswith("**") and len(lines) == 1:
        return True

    # 粗略計算中文字數，太短的小碎片就丟掉
    han = len(re.findall(r"[\u4e00-\u9fff]", s))
    if han < 4 and len(s) < 20:
        return True

    return False


def detect_style(text: str):
    """
    粗略偵測這份合約主要用哪種條款標號風格：
    - has_article: 使用「第 一 條」「第1條」這種
    - has_chinese_num: 使用「一、」「二、」這種
    """
    has_article = bool(re.search(r'第\s*[一二三四五六七八九十0-9]+\s*條', text))
    has_chinese_num = bool(re.search(r'^[一二三四五六七八九十]+\s*[、．.]', text, re.M))
    return has_article, has_chinese_num


def is_clause_start(line: str, has_article: bool, has_chinese_num: bool) -> bool:
    """
    判斷這一行是不是「一條新條款」的開頭。

    根據 detect_style 的結果決定要不要把 1. / (一) 之類視為新條款：
    - 如果文件有「第 X 條」或「一、」等大標，則只用這些做切點；
      1. / (一) 被視為「同一條裡的小項」，不另切條。
    - 如果文件都沒有上述形式，才把 1. / (一) 視為主條款切點。
    """
    s = line.strip()
    if not s:
        return False

    # 永遠認「第 X 條」
    if has_article and re.match(r'^#{0,6}\s*第\s*[一二三四五六七八九十0-9]+\s*條', s):
        return True

    # 有「一、二、三、」這種結構時，用這個當大條
    if has_chinese_num and re.match(r'^[一二三四五六七八九十]+\s*[、．.]', s):
        return True

    # 如果既沒有「第 X 條」，也沒有「一、二、」，才考慮 1. / (一) 當主條款
    if not has_article and not has_chinese_num:
        # 1. 2. 3.
        if re.match(r'^\d+\s*[\.．]', s):
            return True
        # (一) (二) (1)
        if re.match(r'^[（(]?\s*[一二三四五六七八九十0-9]+\s*[)）]', s):
            return True

    return False


def segment_clauses(text: str) -> List[str]:
    """
    用「偵測條款開頭」的方式切段：
    - 逐行掃描，遇到 is_clause_start(...) == True 就開新條
    - 避免「第 一 條」和下面的 1. 被拆成兩條
    """

    normalized = re.sub(r'\r\n', '\n', text)
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

    # 過濾掉純標題 / 超短碎片
    clauses = [c for c in clauses if not is_trivial_clause(c)]
    return clauses


# =========================
# 風險等級與報告
# =========================

def normalize_risk_level(lv: str) -> str:
    """
    把 possible 的英文 / 大小寫 / 中文風險等級統一成「低 / 中 / 高 / 未知」
    """
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
    """
    給一串條款文字 + LLMClient，回傳每條的分析結果列表。

    progress_callback(i, total) 可選，用於 Web 那邊顯示進度。
    """
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
    """
    根據每條條款的 risk_level（低/中/高）算一個 0~100 的整體風險分數。
    """
    score_map = {
        "低": 1,
        "中": 3,
        "高": 5,
    }

    scores = []
    for r in results:
        lvl = normalize_risk_level(r.get("risk_level", ""))
        if lvl in score_map:
            scores.append(score_map[lvl])

    if not scores:
        return 0

    avg = sum(scores) / len(scores)  # 介於 1~5
    normalized = int((avg - 1) / (5 - 1) * 100)  # 映射到 0~100
    return max(0, min(100, normalized))


def create_markdown_report(results: List[Dict]) -> str:
    overall_score = compute_overall_risk_score(results)

    high_count = sum(1 for r in results if normalize_risk_level(r.get("risk_level", "")) == "高")
    med_count = sum(1 for r in results if normalize_risk_level(r.get("risk_level", "")) == "中")
    low_count = sum(1 for r in results if normalize_risk_level(r.get("risk_level", "")) == "低")

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
