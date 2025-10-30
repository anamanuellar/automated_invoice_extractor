"""
EXTRATOR HÍBRIDO OTIMIZADO
===========================
Combina:
- REGEX confiável do código anterior (extração básica)
- IA Generativa para complexo (itens e impostos)
- Cache híbrido (disco + memória)
- OCR como fallback

Mantém taxa alta de extração de campo simples (NF, emitente, etc)
"""

from typing import Any, Optional, List, Dict, Union
import os
import io
import re
import json
import traceback
import hashlib
import time
import requests
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import pdfplumber
import fitz
import streamlit as st

# Importar módulos locais
try:
    from extrator_ia_itens_impostos import ExtractorIA, GEMINI_DISPONIVEL
    IA_DISPONIVEL = True
except ImportError:
    IA_DISPONIVEL = False
    GEMINI_DISPONIVEL = False

# ==================== CACHE HÍBRIDO ====================

CACHE_DIR = "cache_nf"
os.makedirs(CACHE_DIR, exist_ok=True)

CNPJ_CACHE: Dict[str, Optional[str]] = {}
NF_MEM_CACHE: Dict[str, Dict[str, Any]] = {}


def get_pdf_hash(pdf_path: str) -> str:
    """Gera hash MD5 único do conteúdo do PDF"""
    with open(pdf_path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def carregar_cache_nf(hash_pdf: str) -> Optional[Dict[str, Any]]:
    """Carrega resultado do cache (memória → disco)"""
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
    """Salva resultado no cache"""
    NF_MEM_CACHE[hash_pdf] = data
    path = os.path.join(CACHE_DIR, f"{hash_pdf}.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Erro ao salvar cache: {e}")


# ==================== REGEX PATTERNS (DO CÓDIGO ANTIGO - CONFIÁVEL) ====================

RE_MOEDA = re.compile(r"R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})")
RE_DATA = re.compile(r"\b\d{2}/\d{2}/\d{4}\b")

RE_NF_MAIN = re.compile(r"NOTA\s+FISCAL\s+ELETR[ÔO]NICA\s*N[ºO]?\s*([\d\.]+)", re.I)
RE_NF_ALT = re.compile(r"\b(?:NF-?E|N[ºO]|NUM(?:ERO)?|NRO)\s*[:\-]?\s*([\d\.]+)", re.I)
RE_NF_NUMERO = re.compile(r"N[ºO\.]?\s*[:\-]?\s*(\d{1,6})", re.I)

RE_SERIE = re.compile(r"S[ÉE]RIE\s*[:\-]?\s*([0-9\.]{1,5})", re.I)
RE_SERIE_ALT = re.compile(r"(?:^|\n)S[ÉE]RIE\s*[:\-]?\s*(\d+)", re.I)

RE_CNPJ_MASK = re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")
RE_CNPJ_PLAIN = re.compile(r"\b\d{14}\b")
RE_CPF_MASK = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")
RE_CPF_PLAIN = re.compile(r"\b\d{11}\b")


# ==================== FUNÇÕES AUXILIARES ====================

def limpar_string(texto: Optional[Any]) -> str:
    """Limpa e normaliza texto"""
    if texto is None:
        return ""
    
    if isinstance(texto, (list, dict)):
        items = texto if isinstance(texto, list) else [str(texto)]
        temp_content = " ".join(str(item) for item in items)
    else:
        temp_content = str(texto)
    
    texto_str = temp_content.strip()
    texto_str = re.sub(r'[\r\n\t]', ' ', texto_str)
    texto_str = re.sub(r'\s+', ' ', texto_str)
    
    return texto_str.strip()


def normalizar_valor_moeda(valor: Optional[str]) -> Union[float, Any]:
    """Converte R$ 1.234,56 para float 1234.56"""
    if valor is None:
        return np.nan
    
    valor_str = str(valor).replace("R$", "").replace("r$", "").strip()
    valor_str = valor_str.replace('.', '').replace(',', '.').strip()
    
    try:
        return float(valor_str)
    except ValueError:
        return np.nan


def normalizar_cnpj_cpf(doc: Optional[str]) -> Optional[str]:
    """Remove pontuações de CNPJ/CPF"""
    if doc is None:
        return None
    
    doc_clean = re.sub(r'[^0-9]', '', str(doc))
    return doc_clean if len(doc_clean) in [11, 14] else None


def extrair_doc_em_linha(s: str) -> Optional[str]:
    """Extrai CNPJ ou CPF de uma linha"""
    m = RE_CNPJ_MASK.search(s) or RE_CPF_MASK.search(s)
    if m:
        return m.group(0)
    m = RE_CNPJ_PLAIN.search(s)
    if m:
        doc_clean = m.group(0)
        if len(doc_clean) == 14:
            return f"{doc_clean[0:2]}.{doc_clean[2:5]}.{doc_clean[5:8]}/{doc_clean[8:12]}-{doc_clean[12:14]}"
    m = RE_CPF_PLAIN.search(s)
    if m:
        cpf_clean = m.group(0)
        if len(cpf_clean) == 11:
            return f"{cpf_clean[0:3]}.{cpf_clean[3:6]}.{cpf_clean[6:9]}-{cpf_clean[9:11]}"
    return None


def pick_last_money_on_same_or_next_lines(linhas: List[str], idx: int, max_ahead: int = 6) -> Optional[str]:
    """Pega último valor monetário em linhas seguintes"""
    def pick(line):
        vals = RE_MOEDA.findall(line)
        vals = [v for v in vals if v != "0,00"]
        return vals[-1] if vals else None
    
    v = pick(linhas[idx])
    if v:
        return v
    
    for j in range(1, max_ahead + 1):
        k = idx + j
        if k >= len(linhas):
            break
        v = pick(linhas[k])
        if v:
            return v
    
    return None


# ==================== CONSULTA DE CNPJ (ENRIQUECIMENTO) ====================

CACHE_CNPJ_FILE = "cache_cnpj.json"

def carregar_cache_cnpj() -> Dict[str, Optional[str]]:
    """Carrega cache persistente de CNPJs"""
    if os.path.exists(CACHE_CNPJ_FILE):
        try:
            with open(CACHE_CNPJ_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def salvar_cache_cnpj(cache: Dict[str, Optional[str]]) -> None:
    """Salva cache persistente de CNPJs"""
    try:
        with open(CACHE_CNPJ_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def consulta_cnpj_api(cnpj: str, cache: Dict[str, Optional[str]]) -> Optional[str]:
    """
    Consulta nome empresarial do CNPJ usando ReceitaWS e BrasilAPI como fallback.
    """
    cnpj_digits = re.sub(r'[^0-9]', '', cnpj)
    
    if len(cnpj_digits) != 14:
        return None
    
    # Verifica cache
    if cnpj_digits in cache:
        return cache[cnpj_digits]
    
    nome_empresarial = None
    
    # 1️⃣ Tenta ReceitaWS
    try:
        url = f"https://www.receitaws.com.br/v1/cnpj/{cnpj_digits}"
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict) and data.get("status") == "OK":
                nome_empresarial = data.get("nome")
    except Exception:
        pass
    
    # 2️⃣ Fallback: BrasilAPI
    if not nome_empresarial:
        try:
            url_brasil = f"https://brasilapi.com.br/api/cnpj/v1/{cnpj_digits}"
            resp = requests.get(url_brasil, timeout=5)
            
            if resp.status_code == 200:
                data_brasil = resp.json()
                nome_empresarial = data_brasil.get("razao_social") or data_brasil.get("nome_fantasia")
        except Exception:
            pass
    
    # Atualiza cache
    cache[cnpj_digits] = nome_empresarial
    salvar_cache_cnpj(cache)
    
    return nome_empresarial


# ==================== EXTRAÇÃO DE TEXTO ====================

def extrair_texto_pdfplumber(pdf_path: str) -> str:
    """Extrai texto com pdfplumber"""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            texto = ""
            for page in pdf.pages:
                texto += page.extract_text() or ""
            return texto
    except Exception:
        return ""


def extrair_texto_pymupdf(pdf_path: str) -> str:
    """Extrai texto com PyMuPDF como fallback"""
    try:
        doc = fitz.open(pdf_path)
        texto = ""
        for page in doc:
            page_text = page.get_text()
            if isinstance(page_text, str):
                texto += page_text
            else:
                texto += str(page_text or "")
        doc.close()
        return texto
    except Exception:
        return ""


def extrair_texto_completo(pdf_path: str) -> str:
    """Extrai texto usando melhor método disponível"""
    # Tenta pdfplumber primeiro (mais confiável)
    texto = extrair_texto_pdfplumber(pdf_path)
    
    # Fallback para PyMuPDF
    if not texto or len(texto.strip()) < 50:
        texto = extrair_texto_pymupdf(pdf_path)
    
    return texto


# ==================== EXTRAÇÃO DE DADOS CAPA (REGEX - CONFIÁVEL) ====================

def extrair_numero_nf(texto: str) -> Optional[str]:
    """Extrai número da NF - lógica do backup mantida"""
    linhas = texto.split("\n")
    
    for ln in linhas:
        # Procura "N°." ou "Nº" com números após
        m = re.search(r"N[°ºO]\.\s*[:\-]?\s*(\d{3}\.\d{3}\.\d{3,6})", ln)
        if m:
            cand = m.group(1).replace(".", "")
            try:
                val = int(cand)
                numero_nf = str(val % 1000000).lstrip("0") or "0"
                return numero_nf
            except:
                pass
        
        # Fallback: procura "Nº:" com menos restrições
        m = re.search(r"N[°ºO]\s*[:\-]?\s*(\d{1,6})(?:\D|$)", ln)
        if m:
            cand = m.group(1)
            try:
                val = int(cand)
                if 1 <= val <= 999999:
                    return str(val)
            except:
                pass
    
    return None


def extrair_serie(texto: str) -> Optional[str]:
    """Extrai série da NF"""
    linhas = texto.split("\n")
    
    for ln in linhas:
        m = RE_SERIE.search(ln)
        if m:
            return m.group(1)
        
        m = RE_SERIE_ALT.search(ln)
        if m:
            return m.group(1)
    
    return None


def extrair_data_emissao(texto: str) -> Optional[str]:
    """Extrai data de emissão"""
    linhas = texto.split("\n")
    
    for ln in linhas:
        md = RE_DATA.search(ln)
        if md:
            dd, mm, yyyy = md.group(0).split("/")
            try:
                if 2006 <= int(yyyy) <= 2035:
                    return md.group(0)
            except:
                pass
    
    return None


def extrair_cnpj_emitente(texto: str) -> Optional[str]:
    """Extrai CNPJ do emitente (primeiro CNPJ encontrado)"""
    cnpjs = re.findall(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b", texto)
    if cnpjs:
        return cnpjs[0]
    
    return None


def extrair_nome_emitente(texto: str, cnpj_emit: Optional[str]) -> Optional[str]:
    """Extrai nome do emitente - melhorado com busca por IDENTIFICAÇÃO DO EMITENTE"""
    if not cnpj_emit:
        return None
    
    linhas = texto.split("\n")
    
    # Estratégia 1: Procura pela label "IDENTIFICAÇÃO DO EMITENTE" ou "EMITENTE"
    for i, ln in enumerate(linhas):
        if "IDENTIFICAÇÃO DO EMITENTE" in ln.upper():
            for j in range(i + 1, min(i + 5, len(linhas))):
                nome_cand = linhas[j].strip()
                if (nome_cand and 
                    len(nome_cand) > 5 and 
                    nome_cand.upper() not in ["DANFE", "DOCUMENTO AUXILIAR DA NOTA FISCAL ELETRÔNICA"] and
                    not any(k in nome_cand.upper() for k in ["CNPJ", "ENDEREÇO", "CEP", "FONE"])):
                    return nome_cand
    
    # Estratégia 2: Procura antes do CNPJ (fallback original)
    idx = texto.find(cnpj_emit)
    if idx != -1:
        trecho_antes = texto[max(0, idx - 300):idx].strip()
        linhas_antes = trecho_antes.split("\n")
        
        for linha in reversed(linhas_antes):
            linha_limpa = linha.strip()
            if (linha_limpa and 
                not any(k in linha_limpa.upper() for k in ["CNPJ", "CPF", "ENDEREÇO", "RAZÃO", "NOTA", "EMITENTE", "DANFE", "ELETR"]) and
                len(linha_limpa) > 5):
                
                alpha_count = sum(c.isalpha() for c in linha_limpa)
                if alpha_count >= max(3, len(linha_limpa) // 2):
                    return linha_limpa
    
    return None


def extrair_cnpj_destinatario(texto: str) -> Optional[str]:
    """Extrai CNPJ do destinatário - lógica EXATA do backup"""
    linhas = texto.split("\n")
    
    for i, ln in enumerate(linhas):
        up = ln.upper()
        if "DESTINATÁRIO" in up or "REMETENTE" in up:
            for j in range(i + 1, min(i + 6, len(linhas))):
                linha_dest = linhas[j]
                doc = extrair_doc_em_linha(linha_dest)
                if doc and len(normalizar_cnpj_cpf(doc) or "") == 14:
                    return doc
    
    return None


def extrair_nome_destinatario(texto: str) -> Optional[str]:
    """Extrai nome do destinatário - lógica EXATA do backup (antes do CNPJ)"""
    linhas = texto.split("\n")
    
    for i, ln in enumerate(linhas):
        up = ln.upper()
        if "DESTINATÁRIO" in up or "REMETENTE" in up:
            for j in range(i + 1, min(i + 6, len(linhas))):
                linha_dest = linhas[j]
                doc_dest = extrair_doc_em_linha(linha_dest)
                if doc_dest and len(normalizar_cnpj_cpf(doc_dest) or "") == 14:
                    # Extrai o texto ANTES do CNPJ na mesma linha
                    partes = linha_dest.split(doc_dest)
                    if partes[0].strip():
                        nome = partes[0].strip()
                        if len(nome) > 3:
                            return nome
    
    return None


def extrair_valor_total(texto: str) -> Optional[str]:
    """Extrai valor total da NF - lógica EXATA do backup"""
    linhas = texto.split("\n")
    
    for i, ln in enumerate(linhas):
        up = ln.upper()
        
        # Procura por "VALOR TOTAL DA NOTA"
        if "VALOR TOTAL DA NOTA" in up:
            v = pick_last_money_on_same_or_next_lines(linhas, i, 3)
            if v:
                return v
        
        # Procura por "V. TOTAL" combinado com "PRODUTOS"
        if "V. TOTAL" in up and "PRODUTOS" in up:
            v = pick_last_money_on_same_or_next_lines(linhas, i, 2)
            if v:
                return v
    
    return None


# ==================== EXTRAÇÃO COMPLETA (CAPA) ====================

def extrair_dados_nf(
    pdf_path: str,
    enriquecer_cnpj: bool = True,
    api_key_gemini: Optional[str] = None
) -> Dict[str, Any]:
    """
    Função principal para extrair dados de uma NF-e em PDF.
    
    Usa:
    - REGEX para dados simples (NF, série, data, CNPJ) - Confiável
    - IA GENERATIVA para itens e impostos (se chave fornecida)
    
    Args:
        pdf_path: Caminho do PDF
        enriquecer_cnpj: Se deve buscar nome via CNPJ
        api_key_gemini: Chave da API Gemini (opcional)
    
    Returns:
        Dict com dados extraídos
    """
    
    hash_pdf = get_pdf_hash(pdf_path)
    cached_data = carregar_cache_nf(hash_pdf)
    
    if cached_data:
        cached_data["arquivo"] = Path(pdf_path).name
        return cached_data
    
    nome_arquivo = Path(pdf_path).name
    
    dados: Dict[str, Any] = {
        "arquivo": nome_arquivo,
        "status": "FALHA NA EXTRAÇÃO"
    }
    
    # 1. EXTRAÇÃO DE TEXTO
    texto_completo = extrair_texto_completo(pdf_path)
    dados["texto_completo"] = limpar_string(texto_completo)
    
    if not dados["texto_completo"]:
        salvar_cache_nf(hash_pdf, dados)
        return dados
    
    # 2. EXTRAÇÃO COM REGEX (dados simples - CONFIÁVEL)
    
    # Número da NF
    dados["numero_nf"] = extrair_numero_nf(dados["texto_completo"])
    
    # Série
    dados["serie"] = extrair_serie(dados["texto_completo"])
    
    # Data de emissão
    dados["data_emissao"] = extrair_data_emissao(dados["texto_completo"])
    
    # CNPJ Emitente
    dados["emitente_doc"] = extrair_cnpj_emitente(dados["texto_completo"])
    
    # Nome Emitente
    dados["emitente_nome"] = extrair_nome_emitente(
        dados["texto_completo"],
        dados["emitente_doc"]
    )
    
    # CNPJ Destinatário
    dados["dest_doc"] = extrair_cnpj_destinatario(dados["texto_completo"])
    
    # Nome Destinatário
    dados["dest_nome"] = extrair_nome_destinatario(dados["texto_completo"])
    
    # Valor total
    valor_total_str = extrair_valor_total(dados["texto_completo"])
    dados["valor_total"] = valor_total_str
    dados["valor_total_num"] = normalizar_valor_moeda(valor_total_str) if valor_total_str else np.nan
    
    # 3.5 ENRIQUECIMENTO COM CNPJ (opcional)
    if enriquecer_cnpj:
        cache_cnpj = carregar_cache_cnpj()
        
        # Enriquece emitente
        if dados.get("emitente_doc"):
            emitente_doc = dados.get("emitente_doc")
            if emitente_doc and not dados.get("emitente_nome"):
                nome_emit = consulta_cnpj_api(emitente_doc, cache_cnpj)
                if nome_emit:
                    dados["emitente_nome"] = nome_emit
        
        # Enriquece destinatário
        if dados.get("dest_doc"):
            dest_doc = dados.get("dest_doc")
            if dest_doc and not dados.get("dest_nome"):
                nome_dest = consulta_cnpj_api(dest_doc, cache_cnpj)
                if nome_dest:
                    dados["dest_nome"] = nome_dest
    
    # 4. EXTRAÇÃO COM IA (dados complexos - OPCIONAL)
    dados["extracao_ia"] = False
    
    if api_key_gemini and IA_DISPONIVEL and GEMINI_DISPONIVEL:
        try:
            extractor_ia = ExtractorIA(api_key_gemini)  # type: ignore
            
            if extractor_ia.model is not None and "CONECTADO" in extractor_ia.status:
                resultado_ia = extractor_ia.extrair_nf_completa(dados["texto_completo"])
                
                dados["itens"] = resultado_ia.get("itens", [])
                dados["impostos"] = resultado_ia.get("impostos", {})
                dados["extracao_ia"] = True
                
                # Extrai valores dos impostos
                if resultado_ia.get("impostos"):
                    impostos = resultado_ia["impostos"]
                    dados["valor_icms"] = impostos.get("valor_icms", 0)
                    dados["valor_ipi"] = impostos.get("valor_ipi", 0)
                    dados["valor_pis"] = impostos.get("valor_pis", 0)
                    dados["valor_cofins"] = impostos.get("valor_cofins", 0)
                    dados["regime_tributario"] = impostos.get("regime_tributario", "normal")
        
        except Exception as e:
            dados["extracao_ia"] = False
            dados["erro_ia"] = str(e)
            if os.environ.get("DEBUG"):
                print(f"Erro ao usar IA: {e}")
    
    # 5. SALVA NO CACHE
    salvar_cache_nf(hash_pdf, dados)
    return dados


# ==================== PROCESSAMENTO DE MÚLTIPLOS PDFS ====================

@st.cache_data(show_spinner=False, ttl=86400)
def processar_pdfs(
    pdf_paths: List[str],
    _progress_callback: Optional[Any] = None,
    api_key_gemini: Optional[str] = None
) -> pd.DataFrame:
    """
    Processa uma lista de PDFs e retorna DataFrame.
    
    Args:
        pdf_paths: Lista de caminhos dos PDFs
        _progress_callback: Função de callback para progresso
        api_key_gemini: Chave da API Gemini (opcional)
    
    Returns:
        DataFrame com dados extraídos
    """
    if not pdf_paths:
        return pd.DataFrame()
    
    notas_fiscais_extraidas: List[Dict[str, Any]] = []
    
    for i, pdf_path in enumerate(pdf_paths):
        nome_arquivo = Path(pdf_path).name
        
        if _progress_callback:
            total_files = len(pdf_paths)
            message = f"Processando arquivo {i+1} de {total_files}: {nome_arquivo}"
            _progress_callback(message)
        
        try:
            dados_nf = extrair_dados_nf(
                pdf_path,
                api_key_gemini=api_key_gemini
            )
            notas_fiscais_extraidas.append(dados_nf)
            
            if _progress_callback:
                metodo = "IA+REGEX" if dados_nf.get("extracao_ia") else "REGEX"
                _progress_callback(f"✅ Extração de {nome_arquivo} concluída ({metodo})")
        
        except Exception as e:
            dados_falha = {
                "arquivo": nome_arquivo,
                "status": "ERRO INTERNO",
                "detalhe_erro": str(e),
                "traceback": traceback.format_exc(),
            }
            notas_fiscais_extraidas.append(dados_falha)
            
            if _progress_callback:
                _progress_callback(f"❌ Falha crítica em {nome_arquivo}: {str(e)}")
    
    if notas_fiscais_extraidas:
        df_resultados = pd.DataFrame(notas_fiscais_extraidas)
        return df_resultados
    else:
        return pd.DataFrame()


# ==================== EXPORTAÇÃO ====================

def exportar_para_excel_com_itens(df_nfs: pd.DataFrame) -> bytes:
    """Exporta DataFrame para Excel com múltiplas abas"""
    output = io.BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        
        # 1. Aba de Notas Fiscais
        df_nfs.to_excel(writer, sheet_name='Notas Fiscais', index=False)
        
        # 2. Aba de Itens (se extraídos com IA)
        todos_itens = []
        for _, row in df_nfs.iterrows():
            itens_nf = row.get("itens")
            if isinstance(itens_nf, list):
                for item in itens_nf:
                    item["numero_nf"] = row.get("numero_nf")
                    item["arquivo"] = row.get("arquivo")
                    todos_itens.append(item)
        
        if todos_itens:
            pd.DataFrame(todos_itens).to_excel(writer, sheet_name="Itens", index=False)
    
    output.seek(0)
    return output.getvalue()


def gerar_relatorio_pdf(df_resumo: pd.DataFrame) -> None:
    """Gera relatório PDF"""
    from fpdf import FPDF
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, "Resumo da Análise Fiscal", ln=True, align="C")
    pdf.ln(10)
    pdf.set_font("Arial", size=10)
    
    for i, row in df_resumo.iterrows():
        for col, val in row.items():
            val_str = str(val)
            
            if isinstance(val, (bytes, bytearray)):
                try:
                    val_str = val.decode('utf-8')
                except UnicodeDecodeError:
                    val_str = f"<{val.__class__.__name__} - {len(val)} bytes (Não Imprimível)>"
            
            pdf.cell(0, 8, f"{col}: {val_str}", ln=True)
        
        pdf.ln(5)
    
    pdf.output("resumo_analise.pdf")
    st.success("📄 PDF gerado com sucesso: resumo_analise.pdf")