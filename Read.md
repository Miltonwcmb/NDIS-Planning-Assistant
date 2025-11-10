# NDIS Planning Assistant  
A Retrieval-Augmented Generation (RAG) application that processes and analyzes NDIS-related documents using Large Language Models (LLMs). It integrates OpenAI embeddings, Azure AI Indexing, and GPT-4o-mini for intelligent retrieval and response generation, presented through a Flask web application.

---

## Application Overview

This application ingests NDIS policy documents (PDF, DOCX, XLSX) and web data, converts them into structured JSONL format, generates embeddings, indexes them in Azure AI Search, and retrieves semantically relevant chunks based on user queries.  
Responses are generated using GPT-4o-mini and displayed through a Flask-based interface.

---
## Data Sources

### 1. Google Drive Folder  
All project documents were manually downloaded and uploaded to a shared Google Drive folder.  
The folder link was shared with the relevant stakeholders for collaboration and access control.

### 2. NDIS Website  
Additional data was web-scraped from the official [NDIS website](https://www.ndis.gov.au/) to include verified and up-to-date policy 
information.


## How to Set Up

### 1. Create a virtual environment
```bash
python3 -m venv .venv
source .venv/bin/activate        # macOS/Linux
.venv\Scripts\activate           # Windows

---

## Installation, Requirements, and Setup

Follow the steps below to install, configure, and run the application.

```bash
# 1. Clone the repository
git clone https://github.com/your-username/ndis-preplanning-assistant.git
cd ndis-preplanning-assistant

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate        # macOS/Linux
.venv\Scripts\activate         # Windows

# 3. Install all dependencies
pip install -r requirements.txt

# 4. Create environment variables (.env file/not shared) 
echo "OPENAI_API_KEY=your_openai_key" >> .env
echo "AZURE_SEARCH_ENDPOINT=your_azure_endpoint" >> .env
echo "AZURE_SEARCH_KEY=your_azure_key" >> .env
echo "AZURE_SEARCH_INDEX=your_index_name" >> .env

# 5. Run the complete RAG pipeline sequentially
python data.py
python embeddings.py
python IndexingAzureAISearch.py
python QueryIndex.py
python RAGLLM.py
python flaskui.py
```

# Requirements
**Language:**  
Python 3.10+

**Core Packages:**  
pandas
numpy
gdown
python-docx
PyPDF2
openpyxl
openai
flask
azure-search-documents
azure-storage-blob
python-dotenv
markdown


# Project Structure 

project/
│── data.py
│── embeddings.py
│── IndexAzureAISearch.py
│── QueryINdex.py
│── RAGLLM.PY
│── Flaskui.py # Flask application output
│── requirements.txt
└── NDIS Planner.md


# Code Flow

### Build-time
1. **data.py** – Ingests and cleans files (PDF, DOCX, XLSX) and exports them as JSONL.  
2. **embeddings.py** – Converts each chunk of text into 1,536-dimensional vectors using `text-embedding-3-small`.  
3. **IndexingAzureAISearch.py** – Uploads embeddings into Azure AI Search for vector-based indexing.

### Run-time
4. **QueryIndex.py** – Embeds user queries and retrieves semantically similar chunks.  
5. **RAGLLM.py** – Combines top-K results and sends them to GPT-4o-mini for grounded responses.  
6. **flaskui.py** – Provides an interactive web interface for querying and viewing results.

## Output

After successful execution, outputs and logs are generated in the `app/` directory.  
The Flask web interface allows interactive queries, displays structured answers, and includes a “Copy Chat” option for exporting conversations.

---

## Technical Summary

The NDIS Pre-Planning Assistant operates through a two-stage RAG pipeline:

1. **Build-Time Processing**  
   - Documents are cleaned, chunked, and embedded using OpenAI’s `text-embedding-3-small` model.  
   - Embedding vectors (1,536 dimensions) are indexed in Azure AI Search for efficient retrieval.

2. **Run-Time Querying**  
   - User queries are embedded in the same vector space.  
   - Top-ranked document chunks are retrieved and combined.  
   - GPT-4o-mini generates a concise, context-based response, guided by NDIS-specific guardrails to maintain safety and relevance.

The Flask interface connects all components, enabling real-time interaction while preserving low latency and cost-efficiency.

---

## Evaluation Metrics

- **Retrieval Quality** – Accuracy and relevance of top-K results from Azure AI Search. (Azure Paid Tier provides similarity cosine score ) 
- **Response Quality** – Clarity, factual correctness, and adherence to NDIS domain boundaries.  
- **System Performance** – Low latency and stable runtime using lightweight models.  
- **Cost Efficiency** – Compact embeddings and small model footprint ensure sustainable execution.

---

## Future Improvements

1. **User Testing** – Pilot with NDIS participants and coordinators.  
2. **Prompt Tuning** – Improve contextual accuracy and tone.  
3. **Logging and Monitoring** – Track performance and token usage.  
4. **Personalization** – Allow user-specific configurations.  
5. **Multimodal Expansion** – Add voice and visual accessibility.  
6. **Source Referencing** – Display citations alongside responses.

---

## License

This project is intended for educational and research purposes only.  
All credentials and API keys must remain private and secure.



