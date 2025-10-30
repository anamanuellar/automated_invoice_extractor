from typing import Any, Optional, Union, List, Dict, cast
import os
import io
import re
import requests
import time
from pathlib import Path
from datetime import datetime
import numpy as np
import pdfplumber
import pandas as pd
from PIL import Image
import fitz
from codigos_fiscais import analisar_nf
from codigos_fiscais_destinatario import analisar_nf_como_destinatario, gerar_resumo_analise
import json
import traceback
import hashlib
import streamlit as st

# ==================== CACHE HÍBRIDO (DISCO + MEMÓRIA + STREAMLIT) ====================

CACHE_DIR: str = "cache_nf"
os.makedirs(CACHE_DIR, exist_ok=True)

CNPJ_CACHE: Dict[str, Optional[str]] = {}
NF_MEM_CACHE: Dict[str, Dict[str, Any]] = {}


def get_pdf_hash(pdf_path: str) -> str:
    """Gera um hash MD5 único do conteúdo do PDF"""
    with open(pdf_path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def carregar_cache_nf(hash_pdf: str) -> Optional[Dict[str, Any]]:
    """Tenta carregar o resultado do cache em disco"""
    if hash_pdf in NF_MEM_CACHE:
        return NF_MEM_CACHE[hash_pdf]

    path: str = os.path.join(CACHE_DIR, f"{hash_pdf}.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data: Dict[str, Any] = json.load(f)
                NF_MEM_CACHE[hash_pdf] = data
                return data
        except Exception:
            return None
    return None


def salvar_cache_nf(hash_pdf: str, data: Dict[str, Any]) -> None:
    """Salva o resultado no cache em disco e memória"""
    NF_MEM_CACHE[hash_pdf] = data
    
    path: str = os.path.join(CACHE_DIR, f"{hash_pdf}.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Erro ao salvar cache: {e}")


# ==================== FUNÇÕES AUXILIARES ====================

def limpar_string(texto: Optional[Any]) -> str:
    """Remove caracteres indesejados, normaliza a string e lida com tipos não-string."""
    
    if texto is None:
        return ""
    
    # Converte para string com tratamento de tipos complexos
    temp_content: str
    if isinstance(texto, (list, dict)):
        # Para list ou dict, converte cada item para string
        items: Union[list, List[str]] = texto if isinstance(texto, list) else [str(texto)]
        temp_content = " ".join(str(item) for item in items)
    else:
        # Para outros tipos (str, int, etc), converte diretamente
        temp_content = str(texto)
    
    # Processamento de limpeza
    texto_str: str = temp_content.strip()
    texto_str = re.sub(r'[\r\n\t]', ' ', texto_str)
    texto_str = re.sub(r'\s+', ' ', texto_str)
    
    return texto_str.strip()


def normalizar_valor_moeda(valor: Optional[str]) -> Union[float, Any]:
    """Converte string de moeda (R$ 1.234,56) para float (1234.56)."""
    if valor is None:
        return np.nan
    
    valor_str: str = str(valor).replace("R$", "").replace("r$", "").strip()
    valor_str = valor_str.replace('.', '').replace(',', '.').strip()
    
    try:
        return float(valor_str)
    except ValueError:
        return np.nan


def normalizar_cnpj_cpf(doc: Optional[str]) -> Optional[str]:
    """Remove pontuações de CNPJ/CPF."""
    if doc is None:
        return None
    
    doc_clean: str = re.sub(r'[^0-9]', '', str(doc))
    return doc_clean if len(doc_clean) in [11, 14] else None


# ==================== FUNÇÃO DE ENRIQUECIMENTO (CNPJ) ====================

def buscar_nome_empresa_cnpj(cnpj: str) -> Optional[str]:
    """Busca o nome da empresa usando CNPJ (simulado/cacheado)."""
    if not cnpj or len(cnpj) != 14:
        return None

    if cnpj in CNPJ_CACHE:
        return CNPJ_CACHE[cnpj]

    # Simulação
    nome: str
    if cnpj == "00000000000191":
        nome = "EMPRESA SIMULADA DE TI LTDA"
    elif cnpj == "10101010101010":
        nome = "FORNECEDOR DE MATERIAIS S.A."
    else:
        nome = f"CNPJ {cnpj} - Nome Enriquecido"
    
    CNPJ_CACHE[cnpj] = nome
    return nome


# ==================== OCR E PRÉ-PROCESSAMENTO (PyMuPDF) ====================

def ocr_pdf_pymupdf(pdf_path: str) -> str:
    """Realiza OCR e extração de texto usando PyMuPDF (fitz) para PDFs digitalizados."""
    documento = fitz.open(pdf_path)
    texto_completo: List[str] = []
    
    for page_num in range(documento.page_count):
        pagina = documento.load_page(page_num)
        
        # Extrai texto puro
        texto_raw: Any = pagina.get_text("text")
        texto: str = texto_raw if isinstance(texto_raw, str) else ""
        
        # Se texto curto, tenta OCR
        if len(texto.strip()) < 50:
            try:
                texto_ocr_raw: Any = pagina.get_text(
                    "text",
                    flags=fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_PRESERVE_LIGATURES
                )
                texto_ocr: str = texto_ocr_raw if isinstance(texto_ocr_raw, str) else ""
                if len(texto_ocr.strip()) > len(texto.strip()):
                    texto = texto_ocr
            except Exception:
                pass
                
        texto_completo.append(texto)
        
    documento.close()
    return "\n".join(texto_completo)


# ==================== EXTRAÇÃO PRINCIPAL (PDFPLUMBER/RE) ====================

def extrair_dados_nf(pdf_path: str, enriquecer_cnpj: bool = True) -> Dict[str, Any]:
    """
    Função principal para extrair dados de uma única NF-e em PDF.
    """
    
    hash_pdf: str = get_pdf_hash(pdf_path)
    cached_data: Optional[Dict[str, Any]] = carregar_cache_nf(hash_pdf)
    
    if cached_data:
        cached_data["arquivo"] = Path(pdf_path).name 
        return cached_data

    dados: Dict[str, Any] = {
        "arquivo": Path(pdf_path).name,
        "status": "FALHA NA EXTRAÇÃO"
    }
    
    # 1. Extração de texto
    texto_completo: str = ocr_pdf_pymupdf(pdf_path)
    
    if not texto_completo.strip():
        with pdfplumber.open(pdf_path) as pdf:
            texto_completo = "\n".join(
                page.extract_text() or "" for page in pdf.pages
            )
    
    dados["texto_completo"] = limpar_string(texto_completo)

    if not dados["texto_completo"]:
        salvar_cache_nf(hash_pdf, dados)
        return dados
    
    # 2. Extração usando Regex
    
    # Número e série da NF
    nf_match = re.search(
        r'Nº\s+(\d+)\s+Série\s+(\d+)',
        dados["texto_completo"],
        re.IGNORECASE
    )
    if nf_match:
        dados["numero_nf"] = limpar_string(nf_match.group(1))
        dados["serie"] = limpar_string(nf_match.group(2))
        
    # Data de emissão
    data_match = re.search(
        r'Data de Emissão:\s*(\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2})',
        dados["texto_completo"],
        re.IGNORECASE
    )
    if data_match:
        data_str: str = data_match.group(1).replace('-', '/')
        dados["data_emissao"] = limpar_string(data_str)
        try:
            dados["data_emissao_obj"] = datetime.strptime(
                data_str, '%d/%m/%Y'
            ).strftime('%Y-%m-%d')
        except ValueError:
            dados["data_emissao_obj"] = None

    # Valor total
    valor_match = re.search(
        r'(?:VALOR TOTAL DA NOTA|TOTAL DA NOTA|VALOR TOTAL NF|TOTAL DA NF)[^\d]*R?\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})',
        dados["texto_completo"],
        re.IGNORECASE
    )
    if valor_match:
        valor_str: str = valor_match.group(1)
        dados["valor_total"] = limpar_string(valor_str)
        dados["valor_total_num"] = normalizar_valor_moeda(valor_str)
    
    # CNPJs
    cnpj_matches: List[str] = re.findall(
        r'\b(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})\b',
        dados["texto_completo"]
    )
    
    # CNPJ do Emitente
    cnpj_emit_match = re.search(
        r'(?:CNPJ|CPF|INSCRIÇÃO)\s*DO\s*EMITENTE:\s*(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})',
        dados["texto_completo"],
        re.IGNORECASE
    )
    
    if cnpj_emit_match:
        dados["emitente_doc"] = normalizar_cnpj_cpf(cnpj_emit_match.group(1))
    elif cnpj_matches:
        dados["emitente_doc"] = normalizar_cnpj_cpf(cnpj_matches[0])
        
    # CNPJ do Destinatário
    cnpj_dest_match = re.search(
        r'(?:CNPJ|CPF|INSCRIÇÃO)\s*DO\s*DESTINATÁRIO:\s*(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})',
        dados["texto_completo"],
        re.IGNORECASE
    )
    
    if cnpj_dest_match:
        dados["dest_doc"] = normalizar_cnpj_cpf(cnpj_dest_match.group(1))
    elif len(cnpj_matches) > 1:
        dados["dest_doc"] = normalizar_cnpj_cpf(cnpj_matches[1])

    # 3. Enriquecimento de Nomes - CORRIGIDO PARA PYLANCE
    if enriquecer_cnpj:
        emitente_doc: Optional[str] = dados.get("emitente_doc")
        if emitente_doc and isinstance(emitente_doc, str):
            nome_emit: Optional[str] = buscar_nome_empresa_cnpj(emitente_doc)
            if nome_emit:
                dados["emitente_nome"] = nome_emit
        
        dest_doc: Optional[str] = dados.get("dest_doc")
        if dest_doc and isinstance(dest_doc, str):
            nome_dest: Optional[str] = buscar_nome_empresa_cnpj(dest_doc)
            if nome_dest:
                dados["dest_nome"] = nome_dest
            
    # Fallback
    if not dados.get("emitente_nome"):
        dados["emitente_nome"] = "Emitente não encontrado"

    if not dados.get("dest_nome"):
        dados["dest_nome"] = "Destinatário não encontrado"
    
    # 4. Dados fiscais
    cfop_match = re.search(r'CFOP:\s*(\d{4})', dados["texto_completo"], re.IGNORECASE)
    if cfop_match:
        dados["cfop"] = cfop_match.group(1)

    cst_match = re.search(r'CST:\s*(\d{3})', dados["texto_completo"], re.IGNORECASE)
    if cst_match:
        dados["cst"] = cst_match.group(1)
        
    csosn_match = re.search(r'CSOSN:\s*(\d{4})', dados["texto_completo"], re.IGNORECASE)
    if csosn_match:
        dados["csosn"] = csosn_match.group(1)
        
    ncm_match = re.search(r'NCM:\s*(\d{8})', dados["texto_completo"], re.IGNORECASE)
    if ncm_match:
        dados["ncm"] = ncm_match.group(1)
    
    # Status de sucesso
    valor_num: Union[float, Any] = dados.get("valor_total_num")
    if dados.get("numero_nf") and valor_num is not np.nan:
        dados["status"] = "SUCESSO"
        
    # 5. Salva no cache
    salvar_cache_nf(hash_pdf, dados)
    return dados


# ==================== PROCESSAMENTO DE MÚLTIPLOS PDFS ====================

def processar_pdfs(
    pdf_paths: List[str],
    _progress_callback: Optional[Any] = None
) -> pd.DataFrame:
    """
    Processa uma lista de caminhos de PDFs e retorna um DataFrame com os resultados.
    """
    if not pdf_paths:
        return pd.DataFrame()
    
    notas_fiscais_extraidas: List[Dict[str, Any]] = []

    for i, pdf_path in enumerate(pdf_paths):
        
        nome_arquivo: str = Path(pdf_path).name
        
        if _progress_callback:
            total_files: int = len(pdf_paths)
            message: str = f"Processando arquivo {i+1} de {total_files}: {nome_arquivo}"
            _progress_callback(message)

        try:
            dados_nf: Dict[str, Any] = extrair_dados_nf(pdf_path)
            notas_fiscais_extraidas.append(dados_nf)
            
            if _progress_callback:
                _progress_callback(f"✅ Extração de {nome_arquivo} concluída.")

        except Exception as e:
            dados_falha: Dict[str, Any] = {
                "arquivo": nome_arquivo,
                "status": "ERRO INTERNO",
                "detalhe_erro": str(e),
                "traceback": traceback.format_exc(),
            }
            notas_fiscais_extraidas.append(dados_falha)
            
            if _progress_callback:
                _progress_callback(f"❌ Falha crítica em {nome_arquivo}: {str(e)}")

    if notas_fiscais_extraidas:
        df_resultados: pd.DataFrame = pd.DataFrame(notas_fiscais_extraidas)
        return df_resultados
    else:
        return pd.DataFrame()


# ==================== FUNÇÕES DE EXPORTAÇÃO ====================

def exportar_para_excel_com_itens(df_nfs: pd.DataFrame) -> bytes:
    """
    Exporta o DataFrame de notas fiscais para um arquivo Excel
    com várias abas (NFs e Análise Fiscal).
    """
    output: io.BytesIO = io.BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        
        # 1. Aba de Notas Fiscais
        df_nfs.to_excel(writer, sheet_name='Notas Fiscais', index=False)

        # 2. Aba de Análise Fiscal
        analises: List[Dict[str, Any]] = []
        
        for _, row in df_nfs.iterrows():
            
            regime_destinatario: str = str(row.get("regime_dest", "normal"))
            regime_emitente: str = str(row.get("regime_emit", "simples"))
            
            try:
                analise: Dict[str, Any] = analisar_nf_como_destinatario(
                    cfop=str(row.get("cfop", "")),
                    ncm=str(row.get("ncm", "")),
                    csosn_ou_cst_recebido=str(row.get("csosn") or row.get("cst") or ""),
                    regime_destinatario=regime_destinatario,
                    regime_emitente=regime_emitente,
                    uf_origem="BA",
                    valor_total=float(row.get("valor_total_num", 0.0))
                )
            except Exception:
                analise = {
                    "conformidade": "ERRO",
                    "credito_icms": {"valor": 0.0, "direito": False},
                    "credito_pis": {"valor": 0.0, "direito": False},
                    "credito_cofins": {"valor": 0.0, "direito": False}
                }

            credito_icms: float = 0.0
            credito_pis: float = 0.0
            credito_cofins: float = 0.0
            
            if analise.get("credito_icms"):
                credito_icms = float(analise["credito_icms"].get("valor", 0.0))
            if analise.get("credito_pis"):
                credito_pis = float(analise["credito_pis"].get("valor", 0.0))
            if analise.get("credito_cofins"):
                credito_cofins = float(analise["credito_cofins"].get("valor", 0.0))
            
            analises.append({
                "arquivo": str(row.get("arquivo", "")),
                "numero_nf": str(row.get("numero_nf", "")),
                "emitente_nome": str(row.get("emitente_nome", "")),
                "dest_nome": str(row.get("dest_nome", "")),
                "regime_emit": regime_emitente,
                "regime_dest": regime_destinatario,
                "conformidade": str(analise.get("conformidade", "DESCONHECIDO")),
                "credito_icms": credito_icms,
                "credito_pis": credito_pis,
                "credito_cofins": credito_cofins,
            })
        
        if analises:
            pd.DataFrame(analises).to_excel(writer, sheet_name="Análise Fiscal", index=False)

    output.seek(0)
    return output.getvalue()


def gerar_relatorio_pdf(df_resumo: pd.DataFrame) -> None:
    """Gera relatório PDF a partir do DataFrame."""
    from fpdf import FPDF

    pdf: FPDF = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, "Resumo da Análise Fiscal", ln=True, align="C")
    pdf.ln(10)
    pdf.set_font("Arial", size=10)

    for i, row in df_resumo.iterrows():
        for col, val in row.items():
            
            val_str: str = str(val)
            
            if isinstance(val, (bytes, bytearray)):
                try:
                    val_str = val.decode('utf-8')
                except UnicodeDecodeError:
                    val_str = f"<{val.__class__.__name__} - {len(val)} bytes (Não Imprimível)>"
            
            pdf.cell(0, 8, f"{col}: {val_str}", ln=True)

        pdf.ln(5)

    pdf.output("resumo_analise.pdf")
    st.success("📄 PDF gerado com sucesso: resumo_analise.pdf")


# ==================== MAIN ====================

if __name__ == "__main__":
    print("Módulo extrator carregado. Execute via Streamlit.")