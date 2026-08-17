# Vecna / AIC51 - Multimodal Video Search Engine

Multimodal video keyframe search engine built for the AI Challenge (AIC). The system integrates CLIP (PE-Core-L-14-336), SigLIP (ViT-SO400M-14-SigLIP-384), Groq LLM Query Expander, and Milvus Vector Database.

## Prerequisites

- Python 3.11+
- Docker Desktop (Running for Milvus Vector Database)
- Node.js 18+ and npm

## Setup & Running the Server

Open PowerShell in the project root directory:

```powershell
# 1. Activate Virtual Environment
.\.venv\Scripts\activate

# 2. Start AIC51 Server (automatically launches Milvus Docker containers and Web UI)
aic51-cli --dev serve
```

Access the web interface at: `http://localhost:6900`

## API Key Configuration (Groq LLM)

Query expansion and spelling correction require a Groq Cloud API Key.

### Method 1: Environment Variable (Recommended)
Set the environment variable in PowerShell prior to starting the server:

```powershell
$env:GROQ_API_KEY="YOUR_GROQ_API_KEY_HERE"
```

### Method 2: Configuration File (`config.yaml`)
Open `config.yaml` in the project root directory and update the `llm` section:

```yaml
llm:
  enable: true
  provider: "groq"
  model_name: "openai/gpt-oss-120b"
  api_key: "YOUR_GROQ_API_KEY_HERE"
```

> **Security Note**: Never commit raw API keys to Git. GitHub Push Protection automatically blocks commits containing active secret keys. Use environment variables or keep `api_key: ""` when pushing to remote repositories.
