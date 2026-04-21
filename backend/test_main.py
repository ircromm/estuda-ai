"""
Tests for Estuda Ai Backend v2.0
Run with: pytest test_main.py -v
"""

import time
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

from main import (
    app,
    build_system_prompt,
    build_practice_prompt,
    check_rate_limit,
    rate_limit_store,
    ANOS_INFO,
    RATE_LIMIT_MAX,
)

client = TestClient(app)


# ──────────────────────────────────────────────
# Health Check
# ──────────────────────────────────────────────
class TestHealthCheck:
    def test_health_returns_ok(self):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "estuda-ai"
        assert data["version"] == "2.0.0"


# ──────────────────────────────────────────────
# System Prompt Building
# ──────────────────────────────────────────────
class TestSystemPrompts:
    def test_regular_prompt_contains_ano_info(self):
        prompt = build_system_prompt("5", modo_mestre=False)
        assert "5 ano" in prompt
        assert "Estuda Ai" in prompt
        assert "NUNCA entregue a resposta" in prompt

    def test_regular_prompt_contains_subject_instruction(self):
        prompt = build_system_prompt("5", modo_mestre=False)
        assert "[MATERIA:" in prompt
        assert "IDENTIFICACAO DE MATERIA" in prompt

    def test_mestre_prompt_is_different(self):
        regular = build_system_prompt("5", modo_mestre=False)
        mestre = build_system_prompt("5", modo_mestre=True)
        assert "professor universitario" in mestre
        assert "profundidade academica" in mestre
        assert regular != mestre

    def test_mestre_prompt_contains_subject_instruction(self):
        prompt = build_system_prompt("5", modo_mestre=True)
        assert "[MATERIA:" in prompt

    def test_all_anos_have_valid_prompts(self):
        for ano_key in ANOS_INFO:
            prompt = build_system_prompt(ano_key, modo_mestre=False)
            assert len(prompt) > 100
            assert "MATERIA" in prompt

    def test_unknown_ano_falls_back_to_5(self):
        prompt = build_system_prompt("99", modo_mestre=False)
        assert "5 ano" in prompt

    def test_escalation_level_0_no_extra(self):
        prompt = build_system_prompt("5", modo_mestre=False, dificuldade=0)
        assert "NAO ENTENDEU" not in prompt

    def test_escalation_level_1_adds_simplification(self):
        prompt = build_system_prompt("5", modo_mestre=False, dificuldade=1)
        assert "NAO ENTENDEU" in prompt
        assert "analogias MAIS SIMPLES" in prompt

    def test_escalation_level_2_adds_max_simplification(self):
        prompt = build_system_prompt("5", modo_mestre=False, dificuldade=2)
        assert "ATENCAO MAXIMA" in prompt
        assert "MICRO-PASSOS" in prompt

    def test_escalation_works_with_mestre(self):
        prompt = build_system_prompt("5", modo_mestre=True, dificuldade=1)
        assert "professor universitario" in prompt
        assert "NAO ENTENDEU" in prompt


# ──────────────────────────────────────────────
# Practice Prompt Building
# ──────────────────────────────────────────────
class TestPracticePrompts:
    def test_practice_prompt_contains_materia(self):
        prompt = build_practice_prompt("Matematica", "fracoes", "5", False)
        assert "Matematica" in prompt
        assert "fracoes" in prompt

    def test_practice_prompt_contains_ano(self):
        prompt = build_practice_prompt("Portugues", "verbos", "3", False)
        assert "3 ano" in prompt

    def test_practice_prompt_mestre_mode(self):
        prompt = build_practice_prompt("Fisica", "cinematica", "em1", True)
        assert "academico" in prompt

    def test_practice_prompt_no_answer_rule(self):
        prompt = build_practice_prompt("Matematica", "equacoes", "7", False)
        assert "NAO incluir a resposta" in prompt


# ──────────────────────────────────────────────
# Rate Limiting
# ──────────────────────────────────────────────
class TestRateLimiting:
    def setup_method(self):
        """Clear rate limit store before each test."""
        rate_limit_store.clear()

    def test_rate_limit_allows_requests(self):
        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"

        remaining = check_rate_limit(mock_request)
        assert remaining == RATE_LIMIT_MAX - 1

    def test_rate_limit_counts_down(self):
        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.2"

        for i in range(5):
            remaining = check_rate_limit(mock_request)

        assert remaining == RATE_LIMIT_MAX - 5

    def test_rate_limit_blocks_at_max(self):
        from fastapi import HTTPException

        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.3"

        for _ in range(RATE_LIMIT_MAX):
            check_rate_limit(mock_request)

        with pytest.raises(HTTPException) as exc_info:
            check_rate_limit(mock_request)
        assert exc_info.value.status_code == 429

    def test_rate_limit_per_ip(self):
        mock_request_a = MagicMock()
        mock_request_a.client.host = "10.0.0.1"
        mock_request_b = MagicMock()
        mock_request_b.client.host = "10.0.0.2"

        for _ in range(10):
            check_rate_limit(mock_request_a)

        # IP B should still have full quota
        remaining = check_rate_limit(mock_request_b)
        assert remaining == RATE_LIMIT_MAX - 1

    def test_rate_limit_expires_old_entries(self):
        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.4"

        # Fill up with old timestamps
        old_time = time.time() - 120  # 2 minutes ago
        rate_limit_store["127.0.0.4"] = [old_time] * RATE_LIMIT_MAX

        # Should still allow (old entries expired)
        remaining = check_rate_limit(mock_request)
        assert remaining == RATE_LIMIT_MAX - 1

    def test_rate_limit_no_client(self):
        mock_request = MagicMock()
        mock_request.client = None

        remaining = check_rate_limit(mock_request)
        assert remaining >= 0


# ──────────────────────────────────────────────
# Chat Endpoint Validation
# ──────────────────────────────────────────────
class TestChatEndpoint:
    def setup_method(self):
        rate_limit_store.clear()

    def test_chat_rejects_empty_messages(self):
        response = client.post("/chat", json={
            "messages": [],
            "ano": "5",
            "modo_mestre": False,
        })
        # Should return 200 but empty stream (no messages to process)
        assert response.status_code == 200

    def test_chat_accepts_valid_request(self):
        """Test that the endpoint accepts a valid request structure."""
        # This will fail to connect to Anthropic (no API key in test),
        # but validates request parsing
        with patch("main.stream_anthropic") as mock_stream:
            async def fake_stream(*args):
                yield "data: {\"text\": \"Hello\"}\n\n"
                yield "data: [DONE]\n\n"

            mock_stream.return_value = fake_stream()

            response = client.post("/chat", json={
                "messages": [{"role": "user", "text": "Hello"}],
                "ano": "5",
                "modo_mestre": False,
                "dificuldade": 0,
            })
            assert response.status_code == 200

    def test_chat_with_dificuldade(self):
        """Test that dificuldade parameter is accepted."""
        with patch("main.stream_anthropic") as mock_stream:
            async def fake_stream(*args):
                yield "data: {\"text\": \"Simplificado\"}\n\n"
                yield "data: [DONE]\n\n"

            mock_stream.return_value = fake_stream()

            response = client.post("/chat", json={
                "messages": [{"role": "user", "text": "Nao entendi"}],
                "ano": "5",
                "modo_mestre": False,
                "dificuldade": 2,
            })
            assert response.status_code == 200

    def test_chat_rate_limit_header(self):
        """Test that rate limit headers are present."""
        with patch("main.stream_anthropic") as mock_stream:
            async def fake_stream(*args):
                yield "data: [DONE]\n\n"

            mock_stream.return_value = fake_stream()

            response = client.post("/chat", json={
                "messages": [{"role": "user", "text": "Test"}],
                "ano": "5",
            })
            assert "x-ratelimit-limit" in response.headers
            assert "x-ratelimit-remaining" in response.headers


# ──────────────────────────────────────────────
# Practice Endpoint Validation
# ──────────────────────────────────────────────
class TestPracticeEndpoint:
    def setup_method(self):
        rate_limit_store.clear()

    def test_practice_accepts_valid_request(self):
        with patch("main.stream_anthropic") as mock_stream:
            async def fake_stream(*args):
                yield "data: {\"text\": \"Exercicio: 2+2=?\"}\n\n"
                yield "data: [DONE]\n\n"

            mock_stream.return_value = fake_stream()

            response = client.post("/practice", json={
                "materia": "Matematica",
                "topico": "adicao",
                "ano": "3",
                "modo_mestre": False,
            })
            assert response.status_code == 200

    def test_practice_rejects_missing_fields(self):
        response = client.post("/practice", json={
            "topico": "fracoes",
        })
        assert response.status_code == 422  # validation error

    def test_practice_rate_limited(self):
        """Fill up rate limit and verify 429."""
        rate_limit_store["testclient"] = [time.time()] * RATE_LIMIT_MAX

        response = client.post("/practice", json={
            "materia": "Matematica",
            "topico": "fracoes",
            "ano": "5",
        })
        assert response.status_code == 429
