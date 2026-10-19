# LeadGen AI — Autonomous B2B Lead Intelligence Platform
> Lead Agent for US, UK based minimal count employees

A high-performance B2B lead discovery and enrichment system powered by **Coresignal Agentic Fast Search**, **Tavily Web Intelligence Engine**, **NVIDIA NIM LLM**, and **SQLite**.

---

## 🚀 Key Features

- **Natural Language Decision-Maker Search**: Search executive profiles (CEOs, Founders, Managing Directors, CTOs) across 900M+ global records using plain English prompts.
- **AI-Powered Deduplication**: Automatically skips companies and executives already saved in the local SQLite database.
- **Concurrent Website Verification**: Multi-threaded Tavily intelligence agent verifies official company websites in parallel.
- **Dedicated Extracted Leads Repository**: Manage, search, inspect, and export all qualified leads to CSV.
- **Responsive Dashboard**: Modern UI with a mobile-friendly collapsible hamburger drawer and fixed proportional data tables.
- **Modular Architecture**: Clean separation between search, data persistence, enrichment, and web presentation.

---

## 🛠️ Tech Stack

- **Backend**: Python 3.12, Flask
- **Discovery Engine**: Coresignal Agentic Fast Search API
- **Verification Engine**: Tavily Search API
- **LLM Engine**: NVIDIA NIM (`nemotron-3.5-super-vl-120b-a12b`)
- **Database**: SQLite3 (`leads.db`)
- **Frontend**: HTML5, Vanilla CSS, Vanilla JavaScript (Zero bloated frameworks)

---

## 📦 Getting Started

### 1. Prerequisites
- Python 3.10+
- [Git](https://git-scm.com/download/win) installed on your system

### 2. Installation & Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/madhavanmarikani-lgtm/leadagentusinggenai.git
   cd leadagentusinggenai
   ```

2. **Create and activate virtual environment**:
   ```bash
   python -m venv env
   # On Windows:
   .\env\Scripts\activate
   # On macOS/Linux:
   source env/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**:
   Copy `.env.example` to `.env` and fill in your API keys:
   ```bash
   cp .env.example .env
   ```
   Edit `.env`:
   ```env
   TAVILY_API_KEY=your_tavily_key
   NVIDIA_API_KEY=your_nvidia_key
   CORESIGNAL_API_KEY=your_coresignal_key
   APOLLO_API_KEY=your_apollo_key (optional)
   ```

5. **Start the server**:
   ```bash
   python server.py
   ```
   Open your browser at `http://localhost:5000`.

---

## 🔒 Security Note
Never commit `.env` or sensitive API keys to GitHub. The included `.gitignore` protects secrets, SQLite database files, and virtual environments from accidental upload.
