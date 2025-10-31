"""
EXTRATOR DE NOTAS FISCAIS (HÍBRIDO INTELIGENTE)
================================================
→ Extrai dados de DANFEs (PDF) via Regex + OCR + IA opcional.
→ Suporta Gemini, OpenAI ou HuggingFace.
→ Cache híbrido (memória + disco).
→ Compatível com Streamlit.
"""

from typing import Any, Optional, List, Dict
import os
import io
import re
import json
import traceback
import hashlib
from pathlib import Path
from datetime import datetime
import requests
import numpy as np
import pandas as pd
import pdfplumber
import fitz  # PyMuPDF
import streamlit as st

# ===================== IA OPCIONAL =====================
ExtractorIA: Optional[Any] = None
try:
    from extrator_ia_itens_impostos import ExtractorIA, GEMINI_DISPONIVEL
    IA_DISPONIVEL = True
except ImportError:
    IA_DISPONIVEL = False
    GEMINI_DISPONIVEL = False

# ===================== CACHE =====================
CACHE_DIR = "cache_nf"
os.makedirs(CACHE_DIR, exist_ok=True)

NF_MEM_CACHE: Dict[str, Dict[str, Any]] = {}


def get_pdf_hash(pdf_path: str) -> str:
    """Gera hash MD5 único para cache."""
    with open(pdf_path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def carregar_cache_nf(hash_pdf: str) -> Optional[Dict[str, Any]]:
    """Carrega resultado do cache (memória → disco)."""
    if hash_pdf in NF_MEM_CACHE:
        return NF_MEM_CACHE[hash_pdf]

    path = os.path.join(CACHE_DIR, f"{hash_pdf}.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                NF_MEM_CACHE[hash_pdf] = data
                return data
        except Exception:
            return None
    return None


def salvar_cache_nf(hash_pdf: str, data: Dict[str, Any]) -> None:
    """Salva resultado no cache."""
    NF_MEM_CACHE[hash_pdf] = data
    path = os.path.join(CACHE_DIR, f"{hash_pdf}.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Erro ao salvar cache: {e}")


# ===================== FUNÇÕES AUXILIARES =====================

def limpar_string(texto: Optional[Any]) -> str:
    """Limpa e normaliza texto de qualquer tipo."""
    if texto is None:
        return ""
    if isinstance(texto, (list, dict)):
        texto = " ".join(str(item) for item in texto) if isinstance(texto, list) else str(texto)
    texto_str = str(texto).strip()
    texto_str = re.sub(r'[\r\n\t]', ' ', texto_str)
    texto_str = re.sub(r'\s+', ' ', texto_str)
    return texto_str.strip()


def normalizar_valor_moeda(valor: Optional[str]) -> float:
    """Converte R$ 1.234,56 → 1234.56."""
    if not valor:
        return np.nan
    valor_str = str(valor).replace("R$", "").replace("r$", "").replace('.', '').replace(',', '.').strip()
    try:
        return float(valor_str)
    except ValueError:
        return np.nan


# ===================== OCR E EXTRAÇÃO DE TEXTO =====================

def extrair_texto_pdfplumber(pdf_path: str) -> str:
    """Extrai texto com pdfplumber (preferencial)."""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            texto = ""
            for page in pdf.pages:
                texto += page.extract_text() or ""
            return texto
    except Exception:
        return ""


def extrair_texto_pymupdf(pdf_path: str) -> str:
    """Extrai texto com PyMuPDF (fallback OCR)."""
    try:
        doc = fitz.open(pdf_path)
        texto = ""
        for page in doc:
            page_text = page.get_text("text") or ""
            texto += str(page_text)
        doc.close()
        return texto
    except Exception:
        return ""


def extrair_texto_completo(pdf_path: str) -> str:
    """Escolhe o melhor método de extração."""
    texto = extrair_texto_pdfplumber(pdf_path)
    if not texto or len(texto.strip()) < 50:
        texto = extrair_texto_pymupdf(pdf_path)
    return texto


# ===================== REGEX DE CAMPOS =====================
RE_NUMERO = re.compile(r"N[°ºO]?\s*[:\-]?\s*(\d{1,6})")
RE_SERIE = re.compile(r"S[ÉE]RIE\s*[:\-]?\s*(\d+)")
RE_CNPJ = re.compile(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b")
RE_VALOR_TOTAL = re.compile(
    r"(?:VALOR TOTAL DA NOTA|TOTAL DA NOTA|VALOR TOTAL NF|TOTAL DA NF)[^\d]*(\d{1,3}(?:\.\d{3})*,\d{2})",
    re.IGNORECASE,
)
RE_DATA = re.compile(r"\b\d{2}/\d{2}/\d{4}\b")


# ===================== ENRIQUECIMENTO VIA CNPJ (API) =====================

CACHE_CNPJ_FILE = "cache_cnpj.json"

def carregar_cache_cnpj() -> Dict[str, Optional[str]]:
    """Carrega cache persistente de CNPJs."""
    if os.path.exists(CACHE_CNPJ_FILE):
        try:
            with open(CACHE_CNPJ_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def salvar_cache_cnpj(cache: Dict[str, Optional[str]]) -> None:
    """Salva cache de CNPJs localmente."""
    try:
        with open(CACHE_CNPJ_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def consulta_cnpj_api(cnpj: str, cache: Dict[str, Optional[str]]) -> Optional[str]:
    """
    Consulta nome empresarial do CNPJ usando APIs públicas:
    1. BrasilAPI (preferencial)
    2. ReceitaWS (fallback)
    """
    cnpj_digits = re.sub(r'[^0-9]', '', cnpj)
    if len(cnpj_digits) != 14:
        return None

    # Verifica cache
    if cnpj_digits in cache:
        return cache[cnpj_digits]

    nome_empresarial = None

    # 1️⃣ BrasilAPI
    try:
        url_brasil = f"https://brasilapi.com.br/api/cnpj/v1/{cnpj_digits}"
        resp = requests.get(url_brasil, timeout=6)
        if resp.status_code == 200:
            data = resp.json()
            nome_empresarial = data.get("razao_social") or data.get("nome_fantasia")
    except Exception:
        pass

    # 2️⃣ ReceitaWS (fallback)
    if not nome_empresarial:
        try:
            url_receita = f"https://www.receitaws.com.br/v1/cnpj/{cnpj_digits}"
            resp = requests.get(url_receita, timeout=6)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "OK":
                    nome_empresarial = data.get("nome")
        except Exception:
            pass

    # Atualiza cache
    cache[cnpj_digits] = nome_empresarial
    salvar_cache_cnpj(cache)
    return nome_empresarial



# ===================== EXTRAÇÃO PRINCIPAL =====================

def extrair_dados_nf(pdf_path: str, api_key: Optional[str] = None, provider: Optional[str] = None) -> Dict[str, Any]:
    """Extrai dados da NF (Regex + IA opcional)."""
    hash_pdf = get_pdf_hash(pdf_path)
    cached = carregar_cache_nf(hash_pdf)
    if cached:
        cached["arquivo"] = Path(pdf_path).name
        return cached

    nome_arquivo = Path(pdf_path).name
    dados: Dict[str, Any] = {"arquivo": nome_arquivo, "status": "FALHA NA EXTRAÇÃO"}

    texto = extrair_texto_completo(pdf_path)
    dados["texto_completo"] = limpar_string(texto)
    if not dados["texto_completo"]:
        salvar_cache_nf(hash_pdf, dados)
        return dados

    # ===== Regex básica (segura) =====
    m_numero = RE_NUMERO.search(texto)
    m_serie = RE_SERIE.search(texto)
    m_data = RE_DATA.search(texto)
    m_valor = RE_VALOR_TOTAL.search(texto)

    dados["numero_nf"] = m_numero.group(1) if m_numero else None
    dados["serie"] = m_serie.group(1) if m_serie else None
    dados["data_emissao"] = m_data.group(0) if m_data else None

    if m_valor:
        valor_str = m_valor.group(1)
        dados["valor_total"] = valor_str
        dados["valor_total_num"] = normalizar_valor_moeda(valor_str)
    else:
        dados["valor_total"] = None
        dados["valor_total_num"] = np.nan

    cnpjs = RE_CNPJ.findall(texto)
    if cnpjs:
        dados["emitente_doc"] = cnpjs[0]
        if len(cnpjs) > 1:
            dados["dest_doc"] = cnpjs[1]

    # === Enriquecimento automático de nomes ===
    cache_cnpj = carregar_cache_cnpj()

    emitente_doc = dados.get("emitente_doc")
    dest_doc = dados.get("dest_doc")

    if emitente_doc:
        nome_emitente = consulta_cnpj_api(emitente_doc, cache_cnpj)
        if nome_emitente:
            dados["emitente_nome"] = nome_emitente

    if dest_doc:
        nome_dest = consulta_cnpj_api(dest_doc, cache_cnpj)
        if nome_dest:
            dados["dest_nome"] = nome_dest



    # ===== IA Opcional =====
    dados["extracao_ia"] = False
    if IA_DISPONIVEL and api_key and ExtractorIA is not None:
        try:
            extrator = ExtractorIA(provider=provider, api_key=api_key)
            resultado = extrator.extrair_nf_completa(dados["texto_completo"])
            dados["impostos"] = resultado.get("impostos", {})
            dados["itens"] = resultado.get("itens", [])
            dados["extracao_ia"] = True
        except Exception as e:
            dados["erro_ia"] = str(e)

    salvar_cache_nf(hash_pdf, dados)
    return dados


# ===================== PROCESSAMENTO EM LOTE =====================

@st.cache_data(show_spinner=False, ttl=86400)
def processar_pdfs(pdf_paths: List[str], _progress_callback: Optional[Any] = None,
                   api_key: Optional[str] = None, provider: Optional[str] = None) -> pd.DataFrame:
    """Processa múltiplos PDFs e retorna DataFrame consolidado."""
    if not pdf_paths:
        return pd.DataFrame()

    resultados = []
    for i, pdf in enumerate(pdf_paths):
        nome = Path(pdf).name
        if _progress_callback:
            _progress_callback(f"📄 Processando {i + 1}/{len(pdf_paths)}: {nome}")

        try:
            dados = extrair_dados_nf(pdf, api_key=api_key, provider=provider)
            resultados.append(dados)
            if _progress_callback:
                metodo = "IA" if dados.get("extracao_ia") else "Regex"
                _progress_callback(f"✅ {nome} processado via {metodo}")
        except Exception as e:
            resultados.append({"arquivo": nome, "erro": str(e)})
            if _progress_callback:
                _progress_callback(f"❌ Falha ao processar {nome}: {str(e)}")

    return pd.DataFrame(resultados)


# ===================== EXPORTAÇÃO =====================

def exportar_para_excel_com_itens(df: pd.DataFrame) -> bytes:
    """Exporta resultados para Excel (Notas + Itens)."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name="Notas Fiscais", index=False)
        itens = []
        for _, row in df.iterrows():
            if isinstance(row.get("itens"), list):
                for it in row["itens"]:
                    it["NF"] = row.get("numero_nf")
                    it["Arquivo"] = row.get("arquivo")
                    itens.append(it)
        if itens:
            pd.DataFrame(itens).to_excel(writer, sheet_name="Itens", index=False)
    output.seek(0)
    return output.getvalue()


def gerar_relatorio_pdf(df: pd.DataFrame) -> None:
    """Gera relatório simples em PDF."""
    from fpdf import FPDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, "Resumo da Análise Fiscal", ln=True, align="C")
    pdf.ln(10)
    pdf.set_font("Arial", size=10)
    for _, row in df.iterrows():
        for k, v in row.items():
            pdf.cell(0, 8, f"{k}: {v}", ln=True)
        pdf.ln(5)
    pdf.output("resumo_analise.pdf")
    st.success("📄 Relatório PDF gerado com sucesso!")
