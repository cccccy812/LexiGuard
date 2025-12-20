# LexiGuard — AI Contract Risk Analyzer

LexiGuard is a lightweight AI-powered system designed to help users analyze contract clauses, identify potential legal risks, and summarize key points using natural language models.
This repository includes:

* **A standalone backend core** (`lexiguard_core.py`)
* **A web-based frontend** built with **Streamlit** (`app.py`)
* **Flexible clause segmentation** for various contract formats
* **LLM-based clause-level risk assessment**

LexiGuard supports **TXT** and **PDF** contract files and provides an instant Markdown report for download.

---

## Features

###  Intelligent Clause Segmentation

Automatically detects:

* `第 X 條`-style numbered clauses
* `一、二、三、` Chinese-number format
* `1.`, `(1)` fallback format

Ensures robust segmentation even for poorly formatted contracts.

###  AI-Powered Clause Analysis

Each clause is analyzed using an LLM to produce:

* Summary
* Risk level (低 / 中 / 高)
* Risk type (e.g., 資料隱私, 自動續約風險)
* Explanation
* Suggested mitigation

All outputs are standardized and validated as strict JSON.

###  Overall Risk Scoring

A 0–100 risk score is computed based on clause-level results.

###  Web-Based User Interface

Built with Streamlit:

* Upload contract file
* View progress bar
* Display clause-by-clause expandable panels
* Download full Markdown report

---
## Language Support

LexiGuard currently focuses on Traditional Chinese contract analysis.
All LLM outputs — including summary, risk level, risk type, risk reason, and suggestions — are generated entirely in Traditional Chinese.

Because the legal risk classification logic and prompt instructions are designed specifically for Traditional Chinese contract wording and structure, the system is not yet optimized for other languages.

Support for additional languages may be introduced in future versions.

---

##  System Architecture

```
           ┌──────────────────────────────┐
           │           Streamlit UI       │
           │   - File upload              │
           │   - Progress bar             │
           │   - Results display          │
           │   - Report download          │
           └───────────────┬──────────────┘
                           │
                           ▼
           ┌──────────────────────────────┐
           │       LexiGuard Core         │
           │  - Clause segmentation       │
           │  - LLM API client            │
           │  - Risk scoring              │
           │  - Markdown report           │
           └───────────────┬──────────────┘
                           │
                           ▼
           ┌──────────────────────────────┐
           │        LLM API (Gateway)     │
           │  - /api/generate             │
           │  - model = gpt-oss:20b       │
           └──────────────────────────────┘
```


#  Installation

### 1. Clone the repository

```bash
git clone https://github.com/cccccy812/lexiguard.git
cd lexiguard
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

---

#  Configuration

Edit the following fields in **lexiguard_core.py**:

```python
FULL_ENDPOINT = "https://api-gateway.netdb.csie.ncku.edu.tw/api/generate"
API_KEY = "YOUR_API_KEY_HERE"
MODEL_NAME = "gpt-oss:20b"
```

---

#  Run the Web App

```bash
streamlit run app.py
```

After launching, open the link shown in your terminal (usually `http://localhost:8501`).

---

#  Project Structure

```
lexiguard/
│
├── app.py
├── lexiguard_core.py
├── requirements.txt
├── README.md
├── example contracts
└── state machine diagrams
```

---

# Example Output

After uploading a contract, LexiGuard provides:

* Clause-by-clause risk evaluation
* Overall risk score
* Top 3 high-risk clauses
* Downloadable Markdown report

---

# Important Notes

* This system **does not provide legal advice**; it is for assisting purposes only.
* LLM outputs may be imperfect; human review is required.
* Uploaded documents are processed in memory and not stored.

---
