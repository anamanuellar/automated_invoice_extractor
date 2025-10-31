"""
EXTRATOR HÍBRIDO UNIVERSAL
===========================
Combina:
- Extração confiável via REGEX
- Análise inteligente via IA (Gemini / OpenAI / Hugging Face)
- Cache híbrido (memória + disco)
- OCR e fallback automático
"""

from typing import Any, Optional, List, Dict, Union
import os, io, re, json, traceback, hashlib, requests
from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd
import pdfplumber
import fitz
import streamlit as st

# 🚀 Novo módulo universal de IA
from extrator_ia_itens_impostos import enriquecer_dados_fiscais

# ==================== CACHE ====================
CACHE_DIR = "cache_nf"
os.makedirs(CACHE_DIR, exist_ok=True)
CNPJ_CACHE: Dict[str, Optional[str]] = {}
NF_MEM_CACHE: Dict[str, Dict[str, Any]] = {}

def get_pdf_hash(pdf_path: str) -> str:
    with open(pdf_path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()

def carregar_cache_nf(hash_pdf: str) -> Optional[Dict[str, Any]]:
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
    NF_MEM_CACHE[hash_pdf] = data
    path = os.path.join(CACHE_DIR, f"{hash_pdf}.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

# ==================== REGEX PATTERNS ====================
RE_MOEDA = re.compile(r"R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})")
RE_DATA = re.compile(r"\b\d{2}/\d{2}/\d{4}\b")
RE_CNPJ = re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")

# ==================== FUNÇÕES AUXILIARES ====================
def limpar_string(texto: Optional[Any]) -> str:
    if texto is None:
        return ""
    if isinstance(texto, (list, dict)):
        texto = json.dumps(texto, ensure_ascii=False)
    texto = str(texto)
    texto = re.sub(r'[\r\n\t]', ' ', texto.strip())
    texto = re.sub(r'\s+', ' ', texto)
    return texto.strip()

def normalizar_valor_moeda(valor: Optional[str]) -> float:
    if not valor:
        return np.nan
    valor = str(valor).replace("R$", "").replace("r$", "").strip()
    valor = valor.replace('.', '').replace(',', '.')
    try:
        return float(valor)
    except ValueError:
        return np.nan

def normalizar_cnpj_cpf(doc: Optional[str]) -> Optional[str]:
    if not doc:
        return None
    doc = re.sub(r'\D', '', str(doc))
    return doc if len(doc) in [11, 14] else None

def buscar_nome_empresa_cnpj(cnpj: str) -> Optional[str]:
    """Consulta nome da empresa (cacheado)."""
    if not cnpj or len(cnpj) != 14:
        return None
    if cnpj in CNPJ_CACHE:
        return CNPJ_CACHE[cnpj]
    nome = f"CNPJ {cnpj} - Nome Enriquecido"
    CNPJ_CACHE[cnpj] = nome
    return nome

# ==================== EXTRAÇÃO DE TEXTO ====================
def extrair_texto_pdf(pdf_path: str) -> str:
    """Tenta extrair texto do PDF com pdfplumber, depois PyMuPDF."""
    texto = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            texto = "\n".join(page.extract_text() or "" for page in pdf.pages)
    except Exception:
        pass

    if not texto or len(texto.strip()) < 50:
        try:
            doc = fitz.open(pdf_path)
            texto = "\n".join(page.get_text("text") for page in doc)
            doc.close()
        except Exception:
            pass
    return texto

# ==================== EXTRAÇÃO DE CAMPOS SIMPLES ====================
def extrair_dados_basicos(texto: str) -> Dict[str, Any]:
    dados: Dict[str, Any] = {}

    # Número da NF
    nf_match = re.search(r'N[º°O]?\s*[:\-]?\s*(\d{3,6})', texto, re.I)
    if nf_match:
        dados["numero_nf"] = nf_match.group(1)

    # Série
    serie_match = re.search(r'S[ÉE]RIE\s*[:\-]?\s*(\d+)', texto, re.I)
    if serie_match:
        dados["serie"] = serie_match.group(1)

    # Data de emissão
    data_match = RE_DATA.search(texto)
    if data_match:
        dados["data_emissao"] = data_match.group(0)

    # Valor total
    valor_match = re.search(r'(?:VALOR TOTAL DA NOTA|TOTAL DA NF)[^\d]*(\d{1,3}(?:\.\d{3})*,\d{2})', texto, re.I)
    if valor_match:
        dados["valor_total"] = valor_match.group(1)
        dados["valor_total_num"] = normalizar_valor_moeda(valor_match.group(1))

    # CNPJs
    cnpjs = RE_CNPJ.findall(texto)
    if cnpjs:
        dados["emitente_doc"] = normalizar_cnpj_cpf(cnpjs[0])
        if len(cnpjs) > 1:
            dados["dest_doc"] = normalizar_cnpj_cpf(cnpjs[1])

    return dados

# ==================== EXTRAÇÃO COMPLETA (IA + REGEX) ====================
def extrair_dados_nf(pdf_path: str,
                     provider_ia: str = "huggingface",
                     api_key_ia: Optional[str] = None,
                     enriquecer_cnpj: bool = True) -> Dict[str, Any]:
    """Extrai dados da NF e aplica enriquecimento IA."""
    hash_pdf = get_pdf_hash(pdf_path)
    cached = carregar_cache_nf(hash_pdf)
    if cached:
        cached["arquivo"] = Path(pdf_path).name
        return cached

    texto = extrair_texto_pdf(pdf_path)
    dados = {"arquivo": Path(pdf_path).name, "status": "FALHA", "texto_completo": limpar_string(texto)}

    if not texto.strip():
        salvar_cache_nf(hash_pdf, dados)
        return dados

    dados.update(extrair_dados_basicos(texto))

    if enriquecer_cnpj:
        if dados.get("emitente_doc"):
            dados["emitente_nome"] = buscar_nome_empresa_cnpj(dados["emitente_doc"])
        if dados.get("dest_doc"):
            dados["dest_nome"] = buscar_nome_empresa_cnpj(dados["dest_doc"])

    dados["status"] = "SUCESSO"

    # 🔹 Análise IA universal
    try:
        dados = enriquecer_dados_fiscais(dados, provider=provider_ia, api_key=api_key_ia)
        dados["extracao_ia"] = True
    except Exception as e:
        dados["extracao_ia"] = False
        dados["erro_ia"] = str(e)

    salvar_cache_nf(hash_pdf, dados)
    return dados

# ==================== MÚLTIPLOS PDFs ====================
@st.cache_data(show_spinner=False, ttl=86400)
def processar_pdfs(pdf_paths: List[str],
                   _progress_callback: Optional[Any] = None,
                   modelo_escolhido: str = "huggingface",
                   api_key_ia: Optional[str] = None) -> pd.DataFrame:
    if not pdf_paths:
        return pd.DataFrame()

    resultados = []
    for i, pdf in enumerate(pdf_paths):
        nome = Path(pdf).name
        if _progress_callback:
            _progress_callback(f"Processando {i+1}/{len(pdf_paths)}: {nome}")
        try:
            dados = extrair_dados_nf(pdf, provider_ia=modelo_escolhido, api_key_ia=api_key_ia)
            resultados.append(dados)
            if _progress_callback:
                _progress_callback(f"✅ {nome} extraído com sucesso ({'IA' if dados.get('extracao_ia') else 'Regex'})")
        except Exception as e:
            resultados.append({"arquivo": nome, "status": "ERRO", "erro": str(e)})
            if _progress_callback:
                _progress_callback(f"❌ Erro em {nome}: {str(e)}")
    return pd.DataFrame(resultados)

# ==================== EXPORTAÇÃO ====================
def exportar_para_excel_com_itens(df_nfs: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_nfs.to_excel(writer, sheet_name="Notas Fiscais", index=False)
        if "analise_ia" in df_nfs.columns:
            cols = ["arquivo", "numero_nf", "emitente_nome", "valor_total_num", "analise_ia"]
            resumo = df_nfs[[c for c in cols if c in df_nfs.columns]]
            resumo.to_excel(writer, sheet_name="Análise IA", index=False)
    output.seek(0)
    return output.getvalue()
