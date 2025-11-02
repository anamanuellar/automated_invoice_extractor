"""
Módulo de IA para extração e análise fiscal inteligente
-------------------------------------------------------
Suporte: Gemini | OpenAI | Hugging Face
"""

from typing import Optional, Dict, Any, Union
import json
import re

# ========================= IMPORTS SEGUROS =========================
# Inicializamos as libs com None para evitar alertas de "possibly unbound"
genai = None
OpenAI = None
pipeline = None

try:
    import google.generativeai as genai  # type: ignore
    GEMINI_DISPONIVEL = True
except Exception:
    GEMINI_DISPONIVEL = False

try:
    from openai import OpenAI  # type: ignore
    OPENAI_DISPONIVEL = True
except Exception:
    OPENAI_DISPONIVEL = False

try:
    from transformers import pipeline  # type: ignore
    HF_DISPONIVEL = True
except Exception:
    HF_DISPONIVEL = False


class ExtractorIA:
    """Classe unificada para extração e análise de DANFEs via IA."""

    def __init__(self, api_key: str, modelo_escolhido: str = "gemini"):
        """
        Inicializa o extrator de IA com base no modelo escolhido.
        Opções válidas: gemini | openai | huggingface
        """
        self.api_key = api_key
        self.modelo_escolhido = modelo_escolhido.lower().strip()
        self.model: Optional[Union[Any, object]] = None
        self.status: str = "❌ Modelo não inicializado"

        # ==================== GEMINI ====================
        if self.modelo_escolhido == "gemini" and GEMINI_DISPONIVEL and genai is not None:
            try:
                genai.configure(api_key=self.api_key)
                self.model = genai.GenerativeModel("gemini-1.5-flash")
                self.status = "✅ Gemini conectado"
            except Exception as e:
                self.status = f"⚠️ Falha ao conectar Gemini: {e}"

        # ==================== OPENAI ====================
        elif self.modelo_escolhido == "openai" and OPENAI_DISPONIVEL and OpenAI is not None:
            try:
                self.model = OpenAI(api_key=self.api_key)
                self.status = "✅ OpenAI conectado"
            except Exception as e:
                self.status = f"⚠️ Falha ao conectar OpenAI: {e}"

        # ==================== HUGGINGFACE ====================
        elif self.modelo_escolhido == "huggingface" and HF_DISPONIVEL and pipeline is not None:
            try:
                self.model = pipeline("summarization", model="facebook/bart-large-cnn")
                self.status = "✅ Hugging Face conectado"
            except Exception as e:
                self.status = f"⚠️ Falha ao conectar Hugging Face: {e}"

        else:
            self.status = "⚠️ Nenhum modelo de IA disponível"

    # =======================================================
    # EXTRAÇÃO COMPLETA DE NOTA FISCAL
    # =======================================================
    def extrair_nf_completa(self, texto: str) -> Dict[str, Any]:
        """
        Utiliza o modelo de IA para identificar itens e impostos
        em um texto completo de DANFE.
        """
        if not texto or not self.model:
            return {"erro": "IA não inicializada ou texto vazio"}

        try:
            prompt = f"""
            Analise a DANFE a seguir e extraia os dados abaixo em formato JSON:
            - Itens (descrição, quantidade, valor unitário, valor total)
            - Impostos (ICMS, IPI, PIS, COFINS, regime tributário)
            - Se um campo não estiver presente, use null.
            DANFE:
            {texto}
            """

            resposta = ""

            if self.modelo_escolhido == "gemini":
                result = self.model.generate_content(prompt)
                resposta = (result.text or "").strip()

            elif self.modelo_escolhido == "openai":
                chat = self.model.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "Você é um especialista em DANFE e impostos."},
                        {"role": "user", "content": prompt},
                    ],
                )
                resposta = chat.choices[0].message.content.strip()

            elif self.modelo_escolhido == "huggingface":
                output = self.model(prompt[:4000], max_length=500, min_length=100, do_sample=False)
                if isinstance(output, list) and "summary_text" in output[0]:
                    resposta = output[0]["summary_text"]
                else:
                    resposta = str(output)

            else:
                return {"erro": "Modelo IA inválido ou não configurado"}

            # Normaliza JSON
            try:
                json_start = resposta.find("{")
                parsed = json.loads(resposta[json_start:])
                return parsed
            except Exception:
                return {"resposta_livre": resposta}

        except Exception as e:
            return {"erro": str(e)}

    # =======================================================
    # ANÁLISE EXECUTIVA (INSIGHTS)
    # =======================================================
    def analisar_texto(self, texto: str) -> str:
        """
        Executa uma análise textual de alto nível com base no modelo selecionado.
        Pode ser usado para gerar insights sobre dados fiscais.
        """
        if not texto or not self.model:
            return "❌ Nenhum texto fornecido ou modelo não inicializado."

        try:
            if self.modelo_escolhido == "gemini":
                result = self.model.generate_content(
                    f"Analise o seguinte texto com foco em padrões financeiros e fiscais:\n\n{texto}"
                )
                return (result.text or "").strip()

            elif self.modelo_escolhido == "openai":
                chat = self.model.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "Você é um analista tributário sênior."},
                        {"role": "user", "content": f"Analise este texto e destaque tendências e anomalias:\n\n{texto}"},
                    ],
                )
                return chat.choices[0].message.content.strip()

            elif self.modelo_escolhido == "huggingface":
                resumo = self.model(texto[:4000], max_length=200, min_length=50, do_sample=False)
                if isinstance(resumo, list) and "summary_text" in resumo[0]:
                    return resumo[0]["summary_text"]
                return str(resumo)

            else:
                return "⚠️ Modelo de IA não configurado corretamente."

        except Exception as e:
            return f"❌ Erro ao processar análise de IA: {e}"
