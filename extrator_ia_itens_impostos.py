"""
Módulo de IA para extração e análise fiscal inteligente
-------------------------------------------------------
Suporte: Gemini | OpenAI | Hugging Face
"""

from typing import Optional, Dict, Any
import json

# =====================================================
# IMPORTS SEGUROS — Inicializados com None
# =====================================================

try:
    from google import generativeai as genai
    GEMINI_DISPONIVEL = True
except ImportError:
    genai = None  # type: ignore
    GEMINI_DISPONIVEL = False

try:
    from openai import OpenAI
    OPENAI_DISPONIVEL = True
except ImportError:
    OpenAI = None
    OPENAI_DISPONIVEL = False

try:
    from transformers import pipeline as hf_pipeline
    HF_DISPONIVEL = True
except ImportError:
    hf_pipeline = None
    HF_DISPONIVEL = False


# =====================================================
# CLASSE PRINCIPAL DE EXTRAÇÃO
# =====================================================

class ExtractorIA:
    def __init__(self, api_key: str, modelo_escolhido: str = "gemini") -> None:
        self.api_key = api_key
        self.modelo_escolhido = modelo_escolhido.lower().strip()
        self.status = "❌ Modelo não inicializado"
        self.client = None
        self.model = None

        if self.modelo_escolhido == "gemini" and GEMINI_DISPONIVEL and genai:
            try:
                genai.configure(api_key=self.api_key)  # type: ignore
                self.client = genai.GenerativeModel("gemini-1.5-flash")  # type: ignore
                self.status = "✅ Gemini conectado"
            except Exception as e:
                self.status = f"⚠️ Falha ao conectar Gemini: {e}"

        elif self.modelo_escolhido == "openai" and OPENAI_DISPONIVEL and OpenAI:
            try:
                self.client = OpenAI(api_key=self.api_key)
                self.status = "✅ OpenAI conectado"
            except Exception as e:
                self.status = f"⚠️ Falha ao conectar OpenAI: {e}"

        elif self.modelo_escolhido == "huggingface" and HF_DISPONIVEL and hf_pipeline:
            try:
                self.model = hf_pipeline("summarization", model="facebook/bart-large-cnn")
                self.status = "✅ Hugging Face conectado"
            except Exception as e:
                self.status = f"⚠️ Falha ao conectar Hugging Face: {e}"

        else:
            self.status = "⚠️ Nenhum modelo de IA disponível"

    def extrair_nf_completa(self, texto: str) -> Dict[str, Any]:
        if not texto:
            return {"erro": "Texto vazio"}

        prompt = (
            "Analise a DANFE a seguir e extraia os dados abaixo em formato JSON:\n"
            "- Itens (descrição, quantidade, valor unitário, valor total)\n"
            "- Impostos (ICMS, IPI, PIS, COFINS, regime tributário)\n"
            "- Se um campo não estiver presente, use null.\n\n"
            f"DANFE:\n{texto}"
        )

        try:
            # Gemini
            if self.modelo_escolhido == "gemini" and self.client and GEMINI_DISPONIVEL:
                resposta = self.client.generate_content(prompt)  # type: ignore
                texto_gerado = resposta.text if resposta else ""
                return {"resposta": texto_gerado.strip() if texto_gerado else ""}
            # OpenAI chamadas de chat
            elif self.modelo_escolhido == "openai" and OPENAI_DISPONIVEL and self.client:
                resposta = self.client.chat.completions.create( # type: ignore
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "Você é um especialista em DANFE e impostos."},
                        {"role": "user", "content": prompt},
                    ],
                )
                texto_gerado = resposta.choices[0].message.content
                return {"resposta": texto_gerado.strip() if texto_gerado else ""}

            # Hugging Face (usando o pipeline diretamente, não como cliente)
            elif self.modelo_escolhido == "huggingface" and HF_DISPONIVEL and self.model:
                output = self.model(
                    texto[:4000], max_length=500, min_length=100, do_sample=False
                )
                resumo = output[0].get("summary_text", "") if (output and isinstance(output, list)) else ""
                return {"resposta": resumo.strip() if resumo else ""}

            else:
                return {"erro": "Modelo IA inválido ou não configurado"}

        except Exception as e:
            return {"erro": str(e)}

    def analisar_texto(self, texto: str) -> str:
        if not texto:
            return "❌ Nenhum texto fornecido."

        try:
            # Gemini
            if self.modelo_escolhido == "gemini" and self.client:
                prompt = f"Você é um analista tributário sênior. Analise este texto e destaque tendências e anomalias:\n\n{texto}"
                resposta = self.client.generate_content(prompt)  # type: ignore
                texto_gerado = resposta.text if resposta else ""
                return texto_gerado.strip() if texto_gerado else ""

            # OpenAI
            elif self.modelo_escolhido == "openai" and self.client:
                resposta = self.client.chat.completions.create( # type: ignore
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "Você é um analista tributário sênior."},
                        {"role": "user", "content": f"Analise este texto e destaque tendências e anomalias:\n\n{texto}"},
                    ],
                )
                texto_gerado = resposta.choices[0].message.content
                return texto_gerado.strip() if texto_gerado else ""

            # Hugging Face (pipeline chamado diretamente)
            elif self.modelo_escolhido == "huggingface" and self.model:
                resumo = self.model(texto[:4000], max_length=200, min_length=50, do_sample=False)
                if isinstance(resumo, list) and resumo and "summary_text" in resumo[0]:
                    texto_gerado = resumo[0]["summary_text"]
                    return texto_gerado.strip() if texto_gerado else ""
                return str(resumo)

            else:
                return "⚠️ Modelo de IA não configurado corretamente."
        except Exception as e:
            return f"❌ Erro ao processar análise de IA: {e}"