# LexiGuard — AI-Based Contract Risk Analyzer (Web Version)

LexiGuard is a web-based system that analyzes Traditional Chinese contracts and identifies potential legal risks using a Large Language Model (LLM).  
The system is designed for non-legal users and emphasizes structured processing, determinism, and formal modeling, making it suitable for a **Theory of Computation Final Project**.

---

## 1. How to Run the System

### 1.1 Environment Setup

LexiGuard requires Python 3.9 or later.

Install dependencies using:

```bash
pip install -r requirements.txt
````

### 1.2 API Key Configuration

The system uses an Ollama-compatible LLM API provided by NCKU.
**Do not hard-code the API key.** Set it via environment variables.

**Windows (PowerShell):**

```powershell
$env:LEXIGUARD_API_KEY="your_api_key_here"
```

**Linux / macOS:**

```bash
export LEXIGUARD_API_KEY="your_api_key_here"
```

### 1.3 Launch the Web Application

Run the Streamlit web interface:

```bash
streamlit run lexiguard_web.py
```

After execution, open the local URL shown in the terminal using a web browser.

---

## 2. System Architecture and Features

### 2.1 System Overview

LexiGuard consists of two main layers:

* **Web Layer**: Handles user interaction and visualization
* **Core Layer**: Performs deterministic processing and LLM-based analysis

The system processes a contract through a fixed pipeline, ensuring reproducibility and clear state transitions.

### 2.2 Main Features

* Upload contract files (`.txt` / `.pdf`)
* Automatic clause segmentation supporting common Chinese legal formats
* Clause-level risk analysis using LLM
* Risk level classification: **Low / Medium / High**
* Overall contract risk scoring (0–100)
* Identification of top high-risk clauses
* Interactive follow-up questions:

  * Per-clause Q&A
  * Global contract-level Q&A
* Downloadable Markdown analysis report

### 2.3 Language Support

* Currently supports **Traditional Chinese contracts only**
* English and Simplified Chinese contracts are not analyzed directly

(Automatic language detection and translation are considered future extensions.)

---

## 3. Project Structure

The project follows a modular design with clear separation of concerns.

```
.
├── lexiguard_core.py      # Core logic (segmentation, LLM calls, scoring)
├── lexiguard_web.py       # Streamlit-based web interface
├── requirements.txt       # Python dependencies
├── example contracts
├── README.md
```

### 3.1 Core Module (`lexiguard_core.py`)

Responsible for:

* Clause segmentation (rule-based, deterministic)
* LLM interaction via `/api/generate`
* Risk normalization and aggregation
* Markdown report generation

This module is UI-independent and can be reused in CLI or API-based systems.

### 3.2 Web Module (`lexiguard_web.py`)

Responsible for:

* File upload handling
* Progress visualization
* Displaying analysis results
* Managing follow-up Q&A interactions
* Providing report download functionality

---

## 4. State Machine Diagram


---

## Disclaimer

LexiGuard is an experimental academic project and does not provide legal advice.
All analysis results are for reference only.

```

