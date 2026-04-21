# 📖 Estuda Aí!

Tutor escolar com IA que analisa fotos de dever de casa e guia o aluno no raciocínio — **sem entregar respostas**.

## Arquitetura

```
frontend/          → HTML estático (hospede em qualquer lugar)
  index.html       → App completo, single-file

backend/           → FastAPI + Anthropic API (deploy no Railway)
  main.py          → Servidor com streaming SSE
  requirements.txt → Dependências Python
  Procfile         → Config Railway
  Dockerfile       → Alternativa ao Procfile
  .env.example     → Variáveis de ambiente
```

## Deploy do Backend (Railway)

### 1. Crie o serviço no Railway

```bash
# Opção A: via CLI
railway login
cd backend
railway init
railway up

# Opção B: via Dashboard
# → New Project → Deploy from GitHub repo → selecione a pasta backend
```

### 2. Configure as variáveis de ambiente

No painel do Railway, adicione:

| Variável | Valor |
|---|---|
| `ANTHROPIC_API_KEY` | `sk-ant-api03-...` |
| `MODEL` | `claude-sonnet-4-20250514` |
| `ALLOWED_ORIGINS` | URL do seu frontend (ou `*` pra dev) |

O Railway injeta `PORT` automaticamente.

### 3. Teste

```bash
curl https://seu-backend.up.railway.app/health
# → {"status":"ok","service":"estuda-ai"}
```

## Deploy do Frontend

O frontend é um único arquivo HTML. Opções:

- **Railway** (static site) — crie outro serviço apontando pra `frontend/`
- **Vercel/Netlify** — arraste a pasta `frontend/`
- **GitHub Pages** — push e ative nas settings
- **Qualquer servidor** — sirva o `index.html`

Na primeira vez que abrir, o app pede a URL do backend (Railway).

## Desenvolvimento Local

```bash
# Terminal 1 — Backend
cd backend
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
uvicorn main:app --reload --port 8000

# Terminal 2 — Frontend
cd frontend
python -m http.server 3000
# Abra http://localhost:3000
# Configure a URL do backend como http://localhost:8000
```

## Funcionalidades

- **📸 Upload de foto** — tira foto do dever ou seleciona da galeria
- **🎒 Seletor de ano** — 1º ano até 3º EM, com linguagem calibrada
- **🎓 Modo Mestre** — explicações com profundidade acadêmica (socrático)
- **💬 Chat contínuo** — pergunte mais sobre a mesma matéria
- **⚡ Streaming** — resposta aparece em tempo real via SSE
- **📱 Mobile-first** — otimizado pra celular (captura de câmera)

## Como o tutor funciona

O system prompt é diferente para cada ano escolar:

- **Anos iniciais (1º-3º):** linguagem carinhosa, frases curtas, exemplos concretos
- **Anos intermediários (4º-6º):** mais desafiador, analogias, termos novos explicados
- **Anos finais (7º-9º):** tom maduro, conexões interdisciplinares
- **Ensino Médio:** estratégico, foco em compreensão profunda

**Regra fundamental:** o tutor NUNCA entrega a resposta. Ele guia com perguntas socráticas.

## Continuar no Claude Code

```bash
cd estuda-ai
claude
# → "melhora o frontend pra ter modo escuro"
# → "adiciona rate limiting no backend"
# → "implementa histórico de conversas com SQLite"
```
