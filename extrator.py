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
import time
from pathlib import Path
from datetime import datetime
import requests
import numpy as np
import pandas as pd
import pdfplumber
import fitz  # PyMuPDF
import streamlit as st
from extrator_ia_itens_impostos import ExtractorIA

# ===================== ENRIQUECIMENTO FISCAL VIA API =====================
try:
    from enriquecedor_fiscal_api import enriquecer_dataframe_fiscal, validar_nfs_com_ia_enriquecida
    ENRIQUECEDOR_DISPONIVEL = True
except ImportError:
    ENRIQUECEDOR_DISPONIVEL = False
    enriquecer_dataframe_fiscal = None
    validar_nfs_com_ia_enriquecida = None
    print("⚠️ Enriquecedor fiscal não disponível")



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


# ===================== REGEX DE CAMPOS =====================
RE_NUMERO = re.compile(
    r"N[°ºO]?[:\.]?\s*(?:000\.)?(\d{3}(?:\.\d{3})*(?:\.\d{3})?)",
    re.IGNORECASE
)
RE_SERIE = re.compile(r"S[ÉE]RIE\s*[:\-]?\s*(\d+)")
RE_CNPJ = re.compile(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b")
RE_VALOR_TOTAL = re.compile(
    r"(?:VALOR\s*(?:TOTAL(?:\s*DA\s*NOTA)?|DA\s*NF|NF)?|V\.?\s*TOTAL)[^\d]{0,10}(\d{1,3}(?:\.\d{3})*,\d{2})",
    re.IGNORECASE
)
RE_DATA = re.compile(r"\b\d{2}/\d{2}/\d{4}\b")
RE_MOEDA = re.compile(r"R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})")

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
    """
    Converte string de moeda brasileira para float.
    Padrão: 1.234.567,89 → 1234567.89
    """
    if not valor:
        return np.nan
    
    valor_str = str(valor).strip()
    valor_str = valor_str.replace("R$", "").replace("r$", "").strip()
    
    # Remove TODOS os pontos (milhar)
    valor_str = valor_str.replace(".", "")
    
    # Troca vírgula decimal por ponto
    valor_str = valor_str.replace(",", ".")
    
    try:
        return float(valor_str)
    except (ValueError, TypeError):
        return np.nan
    
def pick_first_money_on_same_or_next_lines(linhas: list, idx: int, max_ahead: int = 3) -> Optional[str]:
    """
    Procura por PRIMEIRO valor monetário na linha atual ou nas próximas linhas.
    IMPORTANTE: Pega o PRIMEIRO valor (não o último) para evitar pegar valores
    de linhas de informações complementares.
    
    Args:
        linhas: Lista de linhas de texto
        idx: Índice da linha atual
        max_ahead: Número máximo de linhas à frente para procurar (padrão: 3)
    
    Returns:
        String com valor em formato brasileiro (ex: "4.500,00") ou None
    """
    # Procura apenas nas próximas linhas (não inclui linha atual para evitar "VALOR TOTAL DA NOTA" etc)
    for j in range(idx, min(idx + max_ahead, len(linhas))):
        linha = linhas[j]
        # Procura valores na linha
        vals = RE_MOEDA.findall(linha)
        # Filtra zeros e retorna o PRIMEIRO valor significativo
        vals = [v for v in vals if v != "0,00"]
        if vals:
            return vals[0]  # ← PRIMEIRO (não último!)
    
    return None


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
        resp = requests.get(url_brasil, timeout=6 )
        if resp.status_code == 200:
            data = resp.json()
            nome_empresarial = data.get("razao_social") or data.get("nome_fantasia")
    except Exception:
        pass

    # 2️⃣ ReceitaWS (fallback)
    if not nome_empresarial:
        try:
            url_receita = f"https://www.receitaws.com.br/v1/cnpj/{cnpj_digits}"
            resp = requests.get(url_receita, timeout=6 )
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

# ===================== EXTRAÇÃO DE CAMPOS VIA REGEX =====================

def extrair_numero_nf(texto: str) -> Optional[str]:
    """
    Extrai número da NF com melhor precisão.
    
    Padrões esperados:
    - Nº.: 000.000.008
    - NF: 00008
    - Número NF: 8
    """
    
    if not texto:
        return None
    
    # Estratégia 1: Procura por padrão formatado "Nº.: XXX.XXX.XXX"
    padroes = [
        # Padrão DANFE: "Nº.: 000.000.008" com espaços flexíveis
        r"N[°ºO]?\.?\s*[:\.]?\s*(\d{3}\.\d{3}\.\d{3})",
        # Padrão com pontos: 000.000.008 ou 000.016.944
        r"N[°ºO]?[:\.\s]*(\d{3}\.\d{3}\.\d{3})",
        # Número simples 4-6 dígitos entre separadores
        r"N[°ºO]?[:\.]?\s*(\d{6})(?:\s|$|,)",
        # Fallback final
        r"N[°ºO]?[:\.]?\s*(\d{3,6})(?:\s|$|\.)",
    ]
    
    for padrao in padroes:
        matches = re.finditer(padrao, texto, re.IGNORECASE | re.MULTILINE)
        for m in matches:
            numero = m.group(1).strip() if m.lastindex else m.group(0)
            if numero:
                return numero
    
    return None

def extrair_serie(texto: str) -> Optional[str]:
    """Extrai a série da NF com fallback baseado em posição."""
    m = re.search(r"S[ÉE]RIE\s*[:\-]?\s*(\d{1,4})", texto, re.IGNORECASE)
    if m:
        return m.group(1).strip()

    # fallback — busca próximo do número da NF
    linhas = texto.split("\n")
    for i, l in enumerate(linhas):
        if "SÉRIE" in l.upper() and i + 1 < len(linhas):
            prox = re.findall(r"\d{1,4}", linhas[i + 1])
            if prox:
                return prox[0]
    return None


def extrair_data_emissao(texto: str) -> Optional[str]:
    """Extrai a data de emissão (DD/MM/AAAA)."""
    match = RE_DATA.search(texto)
    if match:
        return match.group(0).strip()
    return None


def extrair_cnpj_emitente(texto: str) -> Optional[str]:
    """Extrai o CNPJ do emitente (primeiro CNPJ encontrado)."""
    matches = RE_CNPJ.findall(texto)
    if matches:
        return matches[0].strip()
    return None


def extrair_nome_emitente(texto: str, cnpj_emitente: Optional[str] = None) -> Optional[str]:
    """Tenta identificar o nome do emitente com base no CNPJ e no contexto."""
    if not cnpj_emitente:
        return None

    # Captura até 100 caracteres antes do CNPJ
    idx = texto.find(cnpj_emitente)
    if idx != -1:
        trecho_antes = texto[max(0, idx - 120):idx]
        linhas = trecho_antes.split("\n")
        for linha in reversed(linhas):
            linha = linha.strip()
            if len(linha) > 5 and not any(x in linha.upper() for x in ["CNPJ", "ENDEREÇO", "INSCRIÇÃO", "NOTA"]):
                return linha
    return None


def extrair_cnpj_destinatario(texto: str) -> Optional[str]:
    """Extrai o CNPJ do destinatário (segundo CNPJ encontrado)."""
    matches = RE_CNPJ.findall(texto)
    if len(matches) > 1:
        return matches[1].strip()
    return None


def extrair_nome_destinatario(texto: str) -> Optional[str]:
    """Tenta identificar o nome do destinatário com base em palavras-chave."""
    linhas = texto.split("\n")
    for i, linha in enumerate(linhas):
        if "DESTINAT" in linha.upper():
            for j in range(i + 1, min(i + 5, len(linhas))):
                nome_candidato = linhas[j].strip()
                if len(nome_candidato) > 5 and not any(x in nome_candidato.upper() for x in ["CNPJ", "ENDEREÇO", "INSCRIÇÃO"]):
                    return nome_candidato
    return None

def extrair_valor_total(texto: str) -> Optional[str]:
    """Extrai o ÚLTIMO valor monetário após 'VALOR TOTAL DA NOTA'"""
    
    if not texto or "VALOR TOTAL DA NOTA" not in texto:
        return None
    
    # Encontra a posição de "VALOR TOTAL DA NOTA"
    pos = texto.find("VALOR TOTAL DA NOTA")
    
    # Pega tudo após essa posição até "TRANSPORTADOR"
    trecho = texto[pos:texto.find("TRANSPORTADOR", pos)]
    
    # Encontra TODOS os valores monetários
    RE_MOEDA = re.compile(r"(\d{1,3}(?:\.\d{3})*,\d{2})")
    valores = RE_MOEDA.findall(trecho)
    
    # Filtra zeros e retorna o ÚLTIMO valor significativo
    valores = [v for v in valores if v != "0,00"]
    
    return valores[-1] if valores else None
    


def extrair_dados_nf(
    pdf_path: str,
    enriquecer_cnpj: bool = True,         # ✅ adiciona suporte ao enriquecimento via API
    api_key_gemini: Optional[str] = None  # ✅ adiciona suporte a IA (Gemini/OpenAI)
) -> Dict[str, Any]:
    """
    Extrai dados de uma NF-e em PDF.
    
    Combina extração tradicional via regex e, opcionalmente, IA para campos avançados.
    """

    hash_pdf = get_pdf_hash(pdf_path)
    cached_data = carregar_cache_nf(hash_pdf)

    if cached_data:
        cached_data["arquivo"] = Path(pdf_path).name
        return cached_data

    nome_arquivo = Path(pdf_path).name
    dados: Dict[str, Any] = {"arquivo": nome_arquivo, "status": "FALHA NA EXTRAÇÃO"}

    # 1️⃣ Extração do texto (OCR + pdfplumber)
    texto_completo = extrair_texto_completo(pdf_path)
    dados["texto_completo"] = limpar_string(texto_completo)

    if not dados["texto_completo"]:
        salvar_cache_nf(hash_pdf, dados)
        return dados

    # 2️⃣ Extração tradicional (regex confiável)
    dados["numero_nf"] = extrair_numero_nf(dados["texto_completo"])
    dados["serie"] = extrair_serie(dados["texto_completo"])
    dados["data_emissao"] = extrair_data_emissao(dados["texto_completo"])
    dados["emitente_doc"] = extrair_cnpj_emitente(dados["texto_completo"])
    dados["emitente_nome"] = extrair_nome_emitente(dados["texto_completo"], dados["emitente_doc"])
    dados["dest_doc"] = extrair_cnpj_destinatario(dados["texto_completo"])
    dados["dest_nome"] = extrair_nome_destinatario(dados["texto_completo"])

    valor_total_str = extrair_valor_total(dados["texto_completo"])
    dados["valor_total"] = valor_total_str
    dados["valor_total_num"] = normalizar_valor_moeda(valor_total_str) if valor_total_str else np.nan

    # 3️⃣ Enriquecimento de CNPJ (opcional)
    if enriquecer_cnpj:
        cache_cnpj = carregar_cache_cnpj()

        emitente_doc = dados.get("emitente_doc")
        dest_doc = dados.get("dest_doc")

        if isinstance(emitente_doc, str) and emitente_doc.strip():
            nome_emit = consulta_cnpj_api(emitente_doc, cache_cnpj)
            if nome_emit:
                dados["emitente_nome"] = nome_emit

        if isinstance(dest_doc, str) and dest_doc.strip():
            nome_dest = consulta_cnpj_api(dest_doc, cache_cnpj)
            if nome_dest:
                dados["dest_nome"] = nome_dest

    # 4️⃣ IA opcional para itens e impostos (se houver API configurada)
    dados["extracao_ia"] = False
    if api_key_gemini:
        try:
            from extrator_ia_itens_impostos import ExtractorIA, GEMINI_DISPONIVEL

            if GEMINI_DISPONIVEL:
                extractor_ia = ExtractorIA(api_key_gemini)
                # Suporta diferentes nomes de método na implementação de ExtractorIA
                # tenta métodos comuns: extrair_nf_completa, extrair, extrair_nf, extrair_completa
                metodo = None
                for nome in ("extrair_nf_completa", "extrair", "extrair_nf", "extrair_completa"):
                    if hasattr(extractor_ia, nome):
                        metodo = getattr(extractor_ia, nome)
                        break
                if metodo is None:
                    raise AttributeError("ExtractorIA não possui método de extração conhecido (procure por extrair_nf_completa/extrair/extrair_nf)")

                resultado_ia = metodo(dados["texto_completo"]) or {}
                
                # CORREÇÃO: Adiciona o parsing do JSON retornado pela IA
                json_string = resultado_ia.get("resposta", "")
                if json_string:
                    try:
                        # Tenta extrair o bloco JSON se a IA o envolveu em markdown (ex: ```json{...}```)
                        json_match = re.search(r"```json\s*([\s\S]*?)\s*```", json_string)
                        if json_match:
                            json_string = json_match.group(1)
                        
                        # Tenta fazer o parsing do JSON
                        resultado_ia_parsed = json.loads(json_string)
                        
                        dados["itens"] = resultado_ia_parsed.get("itens", [])
                        dados["impostos"] = resultado_ia_parsed.get("impostos", {})
                        dados["extracao_ia"] = True
                    except json.JSONDecodeError:
                        dados["erro_ia"] = "Falha ao decodificar JSON da IA. Conteúdo: " + json_string[:100]
                        dados["extracao_ia"] = False
                # FIM DA CORREÇÃO

        except Exception as e:
            dados["erro_ia"] = str(e)
            dados["extracao_ia"] = False

    # 5️⃣ Finaliza e salva no cache
    dados["status"] = "SUCESSO"
    salvar_cache_nf(hash_pdf, dados)
    return dados


# ==================== PROCESSAMENTO DE MÚLTIPLOS PDFS ====================

def processar_pdfs(
    pdf_paths: List[str],
    _progress_callback: Optional[Any] = None,
    api_key_gemini: Optional[str] = None  # ✅ Adicionado
) -> pd.DataFrame:
    """
    Processa uma lista de caminhos de PDFs e retorna um DataFrame com os resultados.

    Args:
        pdf_paths: lista de arquivos PDF das notas fiscais
        _progress_callback: função opcional para reportar progresso (ex: st.info)
        api_key_gemini: chave da API Gemini (ou outro modelo de IA) para análise avançada opcional
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
            # ✅ Repassa a chave da IA para o extrator principal
            dados_nf = extrair_dados_nf(
                pdf_path,
                enriquecer_cnpj=True,
                api_key_gemini=api_key_gemini
            )

            notas_fiscais_extraidas.append(dados_nf)

            if _progress_callback:
                metodo = "IA+REGEX" if dados_nf.get("extracao_ia") else "REGEX"
                _progress_callback(f"✅ Extração concluída ({metodo}): {nome_arquivo}")

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

    # ✅ Retorna DataFrame com todos os resultados
    if notas_fiscais_extraidas:
        df_resultados = pd.DataFrame(notas_fiscais_extraidas)
        
        # ===================== ENRIQUECIMENTO FISCAL VIA API =====================
        if ENRIQUECEDOR_DISPONIVEL and enriquecer_dataframe_fiscal is not None:
            try:
                if _progress_callback:
                    _progress_callback("🌐 Enriquecendo dados fiscais via API...")
                
                df_resultados = enriquecer_dataframe_fiscal(
                    df_resultados,
                    coluna_cnpj="emitente_doc"
                )
                
                if _progress_callback:
                    _progress_callback("✅ Enriquecimento fiscal concluído")
                    
            except Exception as e:
                if _progress_callback:
                    _progress_callback(f"⚠️ Erro ao enriquecer dados: {str(e)}")
        
        return df_resultados
    else:
        return pd.DataFrame()



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