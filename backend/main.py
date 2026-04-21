"""
Estuda Ai - Backend FastAPI v2.0
Tutor escolar com IA que guia sem entregar respostas.
Features: rate limiting, deteccao de materia, escalada adaptativa, exercicios de pratica.
"""

import os
import json
import time
import httpx
from collections import defaultdict
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="Estuda Ai API", version="2.0.0")

# CORS
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining"],
)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
MODEL = os.getenv("MODEL", "claude-sonnet-4-20250514")

# ──────────────────────────────────────────────
# Rate Limiting (in-memory, per IP)
# ──────────────────────────────────────────────

rate_limit_store: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT_MAX = int(os.getenv("RATE_LIMIT", "20"))
RATE_LIMIT_WINDOW = 60


def check_rate_limit(request: Request) -> int:
    """Check rate limit for IP. Returns remaining requests. Raises 429 if exceeded."""
    ip = request.client.host if request.client else "unknown"
    now = time.time()

    # Prune expired entries
    rate_limit_store[ip] = [t for t in rate_limit_store[ip] if now - t < RATE_LIMIT_WINDOW]

    if len(rate_limit_store[ip]) >= RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=429,
            detail="Muitas requisicoes! Aguarde um minutinho e tente novamente.",
        )

    rate_limit_store[ip].append(now)
    return RATE_LIMIT_MAX - len(rate_limit_store[ip])


# ──────────────────────────────────────────────
# System Prompts
# ──────────────────────────────────────────────

ANOS_INFO = {
    "1": {
        "label": "1 ano",
        "desc": "6-7 anos, aprendendo a ler e escrever, numeros ate 100, formas basicas",
        "tom": "Use frases bem curtinhas e simples. Exemplos do dia a dia (brinquedos, animais, comida). Seja super carinhoso e animado! Use emojis com moderacao.",
    },
    "2": {
        "label": "2 ano",
        "desc": "7-8 anos, leitura basica, adicao e subtracao, textos curtos",
        "tom": "Frases curtas e claras. Exemplos concretos. Seja alegre e paciente. Celebre cada pequeno passo.",
    },
    "3": {
        "label": "3 ano",
        "desc": "8-9 anos, multiplicacao basica, textos narrativos simples, ciencias da natureza",
        "tom": "Pode usar frases um pouco mais longas. Exemplos do cotidiano. Faca perguntas que estimulem a curiosidade.",
    },
    "4": {
        "label": "4 ano",
        "desc": "9-10 anos, divisao, fracoes iniciais, geografia basica, historia do Brasil",
        "tom": "Linguagem clara, pode introduzir termos novos (explicando). Estimule o raciocinio com perguntas.",
    },
    "5": {
        "label": "5 ano",
        "desc": "10-11 anos, fracoes, decimais, porcentagem basica, producao de texto",
        "tom": "Pode ser mais desafiador. Use analogias interessantes. Incentive a pensar antes de responder.",
    },
    "6": {
        "label": "6 ano",
        "desc": "11-12 anos, inicio do fundamental II, equacoes simples, historia antiga, ciencias",
        "tom": "Linguagem adolescente acessivel. Pode usar humor leve. Conecte com coisas que interessam a essa idade.",
    },
    "7": {
        "label": "7 ano",
        "desc": "12-13 anos, equacoes, geometria, biologia celular, literatura",
        "tom": "Tom de conversa, como um tutor legal. Desafie com perguntas que fazem pensar.",
    },
    "8": {
        "label": "8 ano",
        "desc": "13-14 anos, algebra, fisica basica, quimica introdutoria",
        "tom": "Direto e claro, sem ser infantil. Use exemplos do mundo real. Estimule conexoes entre materias.",
    },
    "9": {
        "label": "9 ano",
        "desc": "14-15 anos, preparacao pro ensino medio, conteudos mais complexos",
        "tom": "Tom maduro mas acessivel. Prepare pra complexidade do EM. Incentive autonomia no estudo.",
    },
    "em1": {
        "label": "1 EM",
        "desc": "15-16 anos, fisica/quimica/biologia mais profundas, literatura brasileira",
        "tom": "Tom jovem adulto. Referencias culturais. Conecte teoria com aplicacoes praticas.",
    },
    "em2": {
        "label": "2 EM",
        "desc": "16-17 anos, aprofundamento, preparacao vestibular comeca",
        "tom": "Foco em entendimento profundo. Antecipe duvidas de vestibular. Seja estrategico.",
    },
    "em3": {
        "label": "3 EM",
        "desc": "17-18 anos, revisao geral, vestibular/ENEM",
        "tom": "Estrategico e eficiente. Foque em compreensao real, nao decoreba. Dicas de prova quando relevante.",
    },
}

MATERIAS_VALIDAS = (
    "Matematica, Portugues, Ciencias, Historia, Geografia, Ingles, Artes, "
    "Educacao Fisica, Filosofia, Sociologia, Fisica, Quimica, Biologia, Literatura, Redacao"
)

SUBJECT_INSTRUCTION = (
    "\n\nIDENTIFICACAO DE MATERIA:\n"
    "Na sua PRIMEIRA resposta sobre um exercicio/tema novo, inclua EXATAMENTE esta tag no INICIO da resposta:\n"
    "[MATERIA:NomeDaMateria]\n"
    f"Onde NomeDaMateria e uma de: {MATERIAS_VALIDAS}\n"
    "Use apenas uma das materias listadas. Inclua a tag apenas na primeira resposta de cada assunto novo."
)


def get_escalation_suffix(dificuldade: int) -> str:
    if dificuldade <= 0:
        return ""
    if dificuldade == 1:
        return (
            "\n\nATENCAO: O aluno indicou que NAO ENTENDEU a explicacao anterior.\n"
            "- Use analogias MAIS SIMPLES e concretas do dia a dia\n"
            "- Quebre o raciocinio em passos MENORES\n"
            "- Use exemplos visuais quando possivel\n"
            "- Seja ainda mais paciente e encorajador"
        )
    return (
        "\n\nATENCAO MAXIMA: O aluno NAO ENTENDEU MULTIPLAS VEZES.\n"
        "- Use a linguagem MAIS SIMPLES POSSIVEL\n"
        "- Analogias com coisas do cotidiano (comida, jogos, brincadeiras)\n"
        "- CADA frase deve ser BEM CURTA\n"
        "- Quebre em MICRO-PASSOS (um conceito por vez)\n"
        "- Use exemplos muito concretos e tangiveis\n"
        "- Considere abordar o conceito por um angulo completamente diferente"
    )


def build_system_prompt(ano: str, modo_mestre: bool, dificuldade: int = 0) -> str:
    escalation = get_escalation_suffix(dificuldade)

    if modo_mestre:
        base = (
            "Voce e um professor universitario doutor, extremamente didatico e apaixonado por ensinar. "
            "Voce esta ajudando um aluno com o dever de casa. Analise a imagem enviada e:\n\n"
            "1. Identifique a materia e o conteudo abordado\n"
            "2. Explique o conceito por tras de cada questao com profundidade academica, mas de forma acessivel\n"
            "3. Use analogias sofisticadas e conexoes interdisciplinares\n"
            "4. NAO entregue as respostas prontas - guie o raciocinio com perguntas socraticas\n"
            "5. Se o aluno errou, explique POR QUE o raciocinio falhou antes de guiar pro caminho certo\n"
            "6. Seja encorajador mas rigoroso - elogie o esforco, nao a facilidade\n\n"
            "Formato: Linguagem clara e bem estruturada. Pode usar termos tecnicos, mas sempre explique-os.\n"
            "Trate o aluno como alguem capaz de entender conceitos complexos se bem explicados.\n"
            "Responda sempre em portugues brasileiro."
        )
        return base + SUBJECT_INSTRUCTION + escalation

    info = ANOS_INFO.get(ano, ANOS_INFO["5"])
    base = (
        f'Voce e um tutor escolar brasileiro chamado "Estuda Ai". '
        f'Voce esta ajudando uma crianca/adolescente do {info["label"]}.\n\n'
        f'CONTEXTO DO ALUNO: {info["desc"]}\n\n'
        "REGRAS FUNDAMENTAIS:\n"
        "1. NUNCA entregue a resposta pronta. Seu trabalho e GUIAR o raciocinio.\n"
        "2. Identifique a materia e o conteudo na imagem do dever de casa.\n"
        "3. Explique o conceito necessario de forma adequada a idade.\n"
        "4. Faca perguntas que levem o aluno a descobrir a resposta por conta propria.\n"
        '5. Se o aluno ja respondeu algo errado, nao diga "esta errado" - pergunte '
        '"como voce chegou nessa resposta?" e guie a partir dai.\n'
        "6. Celebre o esforco e a curiosidade, nao apenas acertos.\n\n"
        f'TOM E LINGUAGEM: {info["tom"]}\n\n'
        "ESTRUTURA DA RESPOSTA:\n"
        '- Comece identificando o que voce ve na imagem ("Vi que voce esta estudando...")\n'
        "- Explique o conceito central de forma adequada a idade\n"
        '- Guie com perguntas ("O que voce acha que acontece se...")\n'
        "- Termine com encorajamento\n\n"
        "Responda sempre em portugues brasileiro. Seja paciente e acolhedor."
    )
    return base + SUBJECT_INSTRUCTION + escalation


def build_practice_prompt(materia: str, topico: str, ano: str, modo_mestre: bool) -> str:
    info = ANOS_INFO.get(ano, ANOS_INFO["5"])
    nivel = "academico e aprofundado" if modo_mestre else f"adequado para {info['label']}"
    return (
        f"Voce e um professor criativo que gera exercicios de pratica.\n\n"
        f"Materia: {materia}\n"
        f"Topico que o aluno acabou de estudar: {topico}\n"
        f"Nivel: {nivel} ({info['label']})\n\n"
        "Gere UM exercicio pratico sobre esse topico.\n"
        "O exercicio deve:\n"
        "1. Ser DIFERENTE do que o aluno acabou de estudar, mas sobre o MESMO conceito\n"
        "2. Ter nivel de dificuldade adequado a serie\n"
        "3. Ser claro e objetivo\n"
        "4. NAO incluir a resposta - o aluno deve tentar resolver\n"
        "5. Incluir uma dica sutil para ajudar no raciocinio\n\n"
        "Formato:\n"
        "- Apresente o exercicio de forma clara e encorajadora\n"
        "- Use um emoji no inicio para tornar mais visual\n"
        "- Termine com uma frase motivacional\n\n"
        "Responda em portugues brasileiro."
    )


# ──────────────────────────────────────────────
# API Models
# ──────────────────────────────────────────────


class ImageData(BaseModel):
    base64: str
    media_type: str


class ChatMessage(BaseModel):
    role: str
    text: Optional[str] = None
    image: Optional[ImageData] = None


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    ano: str = "5"
    modo_mestre: bool = False
    dificuldade: int = 0


class PracticeRequest(BaseModel):
    materia: str
    topico: str
    ano: str = "5"
    modo_mestre: bool = False


# ──────────────────────────────────────────────
# Streaming helper
# ──────────────────────────────────────────────


async def stream_anthropic(system_prompt: str, api_messages: list):
    """Stream response from Anthropic API as SSE events."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST",
            ANTHROPIC_URL,
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": MODEL,
                "max_tokens": 2048,
                "system": system_prompt,
                "messages": api_messages,
                "stream": True,
            },
        ) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        event = json.loads(data)
                        if event.get("type") == "content_block_delta":
                            text = event.get("delta", {}).get("text", "")
                            if text:
                                yield f"data: {json.dumps({'text': text})}\n\n"
                        elif event.get("type") == "message_stop":
                            yield "data: [DONE]\n\n"
                    except json.JSONDecodeError:
                        continue


def build_streaming_response(generator, remaining: int) -> StreamingResponse:
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-RateLimit-Limit": str(RATE_LIMIT_MAX),
            "X-RateLimit-Remaining": str(remaining),
        },
    )


# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────


@app.get("/health")
async def health():
    return {"status": "ok", "service": "estuda-ai", "version": "2.0.0"}


@app.post("/chat")
async def chat(req: ChatRequest, request: Request):
    """Chat endpoint with subject detection and adaptive escalation."""
    remaining = check_rate_limit(request)

    system_prompt = build_system_prompt(req.ano, req.modo_mestre, req.dificuldade)

    api_messages = []
    for msg in req.messages:
        content = []
        if msg.image:
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": msg.image.media_type,
                        "data": msg.image.base64,
                    },
                }
            )
        if msg.text:
            content.append({"type": "text", "text": msg.text})
        if not content:
            continue
        api_messages.append({"role": msg.role, "content": content})

    return build_streaming_response(
        stream_anthropic(system_prompt, api_messages), remaining
    )


@app.post("/practice")
async def practice(req: PracticeRequest, request: Request):
    """Generate a practice exercise based on subject and topic."""
    remaining = check_rate_limit(request)

    system_prompt = build_practice_prompt(
        req.materia, req.topico, req.ano, req.modo_mestre
    )
    api_messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": f"Gere um exercicio de {req.materia} sobre: {req.topico}",
                }
            ],
        }
    ]

    return build_streaming_response(
        stream_anthropic(system_prompt, api_messages), remaining
    )


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
