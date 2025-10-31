"""
Módulo: extrator_ia_itens_impostos
----------------------------------
Versão final compatível com:
- Gemini (google-generativeai >= 0.7)
- OpenAI (openai >= 1.0)
- Hugging Face (gratuito)

Corrigido para não gerar warnings de Pylance.
"""

from typing import Dict, Any, Optional
import json
import re
import streamlit as st

# ===================== IMPORTS SEGUROS =====================

# Evita "possibly unbound" usando variáveis padrão None
genai = None
OpenAI = None
pipeline = None

# Gemini
try:
    import google.generativeai as genai  # type: ignore
    GEMINI_DISPONIVEL = True
except ImportError:
    GEMINI_DISPONIVEL = False

# OpenAI
try:
    from openai import OpenAI  # type: ignore
    OPENAI_DISPONIVEL = True
except ImportError:
    OPENAI_DISPONIVEL = False

# Hugging Face
try:
    from transformers import pipeline  # type: ignore
    HF_DISPONIVEL = True
except ImportError:
    HF_DISPONIVEL = False


# ===================== CLASSE PRINCIPAL =====================

class ExtractorIA:
    """
    Responsável por usar diferentes modelos de IA
    para extrair CFOP, NCM, CST e impostos de DANFEs.
    """

    def __init__(self, provider: str = "huggingface", api_key: Optional[str] = None):
        self.provider = provider.lower()
        self.api_key = api_key
        self.status = "INICIALIZANDO..."
        self.model: Optional[Any] = None
        self.client: Optional[Any] = None
        self.pipe: Optional[Any] = None

        # ========== GEMINI ==========
        if self.provider == "gemini" and GEMINI_DISPONIVEL and genai:
            if not self.api_key:
                raise ValueError("API Key do Gemini não fornecida.")
            try:
                if callable(getattr(genai, "configure", None)):
                    getattr(genai, "configure", lambda **_: None)(api_key=self.api_key)  # type: ignore
                self.model = getattr(genai, "GenerativeModel")("gemini-1.5-flash")
                self.status = "CONECTADO (Gemini)"
            except Exception as e:
                self.status = f"❌ Erro ao conectar Gemini: {e}"

        # ========== OPENAI ==========
        elif self.provider == "openai" and OPENAI_DISPONIVEL and OpenAI:
            if not self.api_key:
                raise ValueError("API Key da OpenAI não fornecida.")
            try:
                self.client = OpenAI(api_key=self.api_key)
                self.model = "gpt-4o-mini"  # nome do modelo
                self.status = "CONECTADO (OpenAI GPT-4o-mini)"
            except Exception as e:
                self.status = f"❌ Erro ao conectar OpenAI: {e}"

        # ========== HUGGING FACE ==========
        elif self.provider == "huggingface" and HF_DISPONIVEL and pipeline:
            try:
                self.pipe = pipeline("text2text-generation", model="google/flan-t5-base")
                self.status = "CONECTADO (Hugging Face)"
            except Exception as e:
                self.status = f"❌ Erro ao conectar Hugging Face: {e}"

        else:
            self.status = "❌ Nenhum modelo de IA disponível."

    # ---------------------------------------------------------

    def _formatar_prompt(self, texto: str) -> str:
        """Cria o prompt padronizado para qualquer modelo"""
        return (
            "Extraia do texto da nota fiscal (DANFE) os seguintes campos:\n"
            "CFOP, NCM, CST/CSOSN, ICMS, PIS e COFINS.\n\n"
            "Retorne em JSON no formato:\n"
            "{ 'cfop': '', 'ncm': '', 'cst': '', 'icms': '', 'pis': '', 'cofins': '' }\n\n"
            f"Texto:\n{texto[:5000]}"
        )

    # ---------------------------------------------------------

    def extrair_nf_completa(self, texto_nf: str) -> Dict[str, Any]:
        """Processa a DANFE usando o modelo configurado"""
        if not texto_nf or not isinstance(texto_nf, str):
            return {"erro": "Texto inválido ou vazio."}

        prompt = self._formatar_prompt(texto_nf)
        resposta: Optional[str] = None

        try:
            # GEMINI
            if self.provider == "gemini" and self.model and GEMINI_DISPONIVEL:
                result = self.model.generate_content(prompt)
                resposta = getattr(result, "text", None)
                if resposta:
                    resposta = resposta.strip()

            # OPENAI
            elif self.provider == "openai" and self.client and OPENAI_DISPONIVEL:
                completion = self.client.chat.completions.create(
                    model=self.model or "gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "Você é um analista fiscal especialista em DANFEs brasileiras."},
                        {"role": "user", "content": prompt}
                    ]
                )
                msg = completion.choices[0].message
                resposta = getattr(msg, "content", None)
                if resposta:
                    resposta = resposta.strip()

            # HUGGINGFACE
            elif self.provider == "huggingface" and self.pipe and HF_DISPONIVEL:
                result = self.pipe(prompt, max_new_tokens=250)
                if isinstance(result, list) and result:
                    resposta = result[0].get("generated_text", "").strip()

        except Exception as e:
            return {"erro": f"Falha na execução do modelo: {e}"}

        if not resposta:
            return {"erro": "Falha na resposta do modelo IA."}

        # Tenta converter resposta em JSON
        try:
            json_start = resposta.find("{")
            json_end = resposta.rfind("}") + 1
            json_text = resposta[json_start:json_end]
            parsed = json.loads(json_text)
        except Exception:
            parsed = {
                "texto_bruto": resposta,
                "cfop": self._match_first(r"\b\d{4}\b", resposta),
                "ncm": self._match_first(r"\b\d{8}\b", resposta),
                "cst": self._match_first(r"\b\d{3}\b", resposta),
            }

        return {
            "itens": [],
            "impostos": {
                "cfop": parsed.get("cfop"),
                "ncm": parsed.get("ncm"),
                "cst": parsed.get("cst"),
                "valor_icms": parsed.get("icms"),
                "valor_pis": parsed.get("pis"),
                "valor_cofins": parsed.get("cofins"),
            },
            "resposta_bruta": resposta,
        }

    # ---------------------------------------------------------
    def _match_first(self, pattern: str, text: str) -> Optional[str]:
        """Utilitário simples para buscar primeira ocorrência regex"""
        m = re.search(pattern, text or "")
        return m.group(0) if m else None


# ===================== TESTE LOCAL OPCIONAL =====================

if __name__ == "__main__":
    st.title("🔍 Teste do ExtractorIA")

    texto_exemplo = """
    DANFE - Documento Auxiliar da Nota Fiscal Eletrônica
    CFOP 5102, NCM 85044010, CST 060, ICMS 18%, PIS 1.65%, COFINS 7.6%
    """

    provedor = st.sidebar.selectbox("Selecione o provedor de IA", ["huggingface", "gemini", "openai"])
    chave = st.sidebar.text_input("API Key (quando aplicável)", type="password")

    try:
        extrator = ExtractorIA(provider=provedor, api_key=chave)
        st.info(f"Status: {extrator.status}")
        resultado = extrator.extrair_nf_completa(texto_exemplo)
        st.json(resultado)
    except Exception as e:
        st.error(f"Erro ao iniciar: {e}")
