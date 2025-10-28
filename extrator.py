from typing import Any, Optional
import os, io, re, requests, time
from pathlib import Path
from datetime import datetime
import numpy as np
import pdfplumber
import pandas as pd
from PIL import Image, ImageEnhance, ImageOps
import fitz  # PyMuPDF

# =============== CONFIG ===============
DEBUG = False
CNPJ_CACHE: dict[str, Optional[str]] = {}
EASY_OCR = None  # Inicializar a variável global para evitar erros

# =============== REGEX ===============
RE_MOEDA = re.compile(r"R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})")
RE_DATA = re.compile(r"\b\d{2}/\d{2}/\d{4}\b")

RE_NF_MAIN   = re.compile(r"NOTA\s+FISCAL\s+ELETR[ÔO]NICA\s*N[ºO]?\s*([\d\.]+)", re.I)
RE_NF_ALT    = re.compile(r"\b(?:NF-?E|N[ºO]|NUM(?:ERO)?|NRO)\s*[:\-]?\s*([\d\.]+)", re.I)
RE_NF_NUMERO = re.compile(r"N[ºO\.]?\s*[:\-]?\s*(\d{1,6})", re.I)

RE_SERIE      = re.compile(r"S[ÉE]RIE\s*[:\-]?\s*([0-9\.]{1,5})", re.I)
RE_SERIE_ALT  = re.compile(r"(?:^|\n)S[ÉE]RIE\s*[:\-]?\s*(\d+)", re.I)

RE_CNPJ_MASK   = re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")
RE_CNPJ_PLAIN  = re.compile(r"\b\d{14}\b")
RE_CPF_MASK    = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")
RE_CPF_PLAIN   = re.compile(r"\b\d{11}\b")

# =============== UTILS ===============
def carregar_easy_ocr():
    try:
        import easyocr
        reader = easyocr.Reader(['pt', 'en'], gpu=False)
        return reader
    except ImportError:
        return None
    
def somente_digitos(s: Any) -> str:
    s_str = str(s) if s is not None else ""
    return re.sub(r"\D", "", s_str or "")

def fmt_cnpj(cnpj_digits: str) -> str:
    d = somente_digitos(cnpj_digits)
    if len(d) != 14: return cnpj_digits
    return f"{d[0:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:14]}"

def fmt_cpf(cpf_digits: str) -> str:
    d = somente_digitos(cpf_digits)
    if len(d) != 11: return cpf_digits
    return f"{d[0:3]}.{d[3:6]}.{d[6:9]}-{d[9:11]}"

def achar_doc_em_linha(s: str) -> Optional[str]:
    m = RE_CNPJ_MASK.search(s) or RE_CPF_MASK.search(s)
    if m: return m.group(0)
    m = RE_CNPJ_PLAIN.search(s)
    if m: return fmt_cnpj(m.group(0))
    m = RE_CPF_PLAIN.search(s)
    if m: return fmt_cpf(m.group(0))
    return None

def moeda_to_float(s: Optional[str]) -> Optional[float]:
    if not s: return None
    try: return float(s.replace(".", "").replace(",", "."))
    except: return None

def pick_last_money_on_same_or_next_lines(linhas, idx, max_ahead=6):
    def pick(line):
        vals = RE_MOEDA.findall(line)
        vals = [v for v in vals if v != "0,00"]
        return vals[-1] if vals else None
    v = pick(linhas[idx])
    if v: return v
    for j in range(1, max_ahead + 1):
        k = idx + j
        if k >= len(linhas): break
        v = pick(linhas[k])
        if v: return v
    return None

# Consulta API para enriquecer nome emitente a partir do CNPJ
def consulta_cnpj_api(cnpj: str) -> Optional[str]:
    cnpj_digits = somente_digitos(cnpj)
    if cnpj_digits in CNPJ_CACHE:
        return CNPJ_CACHE[cnpj_digits]
    url = f"https://www.receitaws.com.br/v1/cnpj/{cnpj_digits}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict) and data.get("status") == "OK":
                nome_empresarial = data.get("nome")
                CNPJ_CACHE[cnpj_digits] = nome_empresarial
                return nome_empresarial
    except Exception as e:
        if DEBUG:
            print(f"[DEBUG] Erro na consulta do CNPJ {cnpj}: {e}")
    return None

# =============== EXTRAÇÃO DE TEXTO ===============
def extrair_capa_de_texto(texto: str) -> dict:
    numero_nf: Optional[str] = None
    serie: Optional[str] = None
    emitente_doc: Optional[str] = None
    emitente_nome: Optional[str] = None
    dest_nome: Optional[str] = None
    dest_doc: Optional[str] = None
    data_emissao: Optional[str] = None
    valor_total: Optional[str] = None

    linhas = texto.split("\n")

    # -------- NF Número/Série --------
    for ln in linhas:
        if not numero_nf:
            m = re.search(r"N[°ºO]\.\s*[:\-]?\s*(\d{3}\.\d{3}\.\d{3,6})", ln)
            if m:
                cand = m.group(1).replace(".", "")
                try:
                    val = int(cand)
                    numero_nf = str(val % 1000000).lstrip("0") or "0"
                except:
                    pass
            if not numero_nf:
                m = re.search(r"N[°ºO]\s*[:\-]?\s*(\d{1,6})(?:\D|$)", ln)
                if m:
                    cand = m.group(1)
                    try:
                        val = int(cand)
                        if 1 <= val <= 999999:
                            numero_nf = str(val)
                    except:
                        pass
        if not serie:
            m = RE_SERIE.search(ln)
            if m:
                serie = m.group(1)
            if not serie:
                m = RE_SERIE_ALT.search(ln)
                if m:
                    serie = m.group(1)

    # -------- EMITENTE --------
    emitente_nome = None
    if emitente_doc is not None:
        nome_api = consulta_cnpj_api(emitente_doc)
        if nome_api:
            emitente_nome = nome_api


    # -------- DESTINATÁRIO --------
    for i, ln in enumerate(linhas):
        up = ln.upper()
        if "DESTINATÁRIO" in up or "REMETENTE" in up:
            for j in range(i + 1, min(i + 6, len(linhas))):
                linha_dest = linhas[j]
                doc_dest = achar_doc_em_linha(linha_dest)
                if doc_dest and len(somente_digitos(doc_dest)) == 14:
                    dest_doc = doc_dest
                    partes = linha_dest.split(doc_dest)
                    if partes[0].strip():
                        dest_nome = partes[0].strip()

    # -------- DATA DE EMISSÃO --------
    for ln in linhas:
        if not data_emissao:
            md = RE_DATA.search(ln)
            if md:
                dd, mm, yyyy = md.group(0).split("/")
                try:
                    if 2006 <= int(yyyy) <= 2035:
                        data_emissao = md.group(0)
                except:
                    pass

    # -------- VALOR TOTAL --------
    for i, ln in enumerate(linhas):
        up = ln.upper()
        if "VALOR TOTAL DA NOTA" in up:
            v = pick_last_money_on_same_or_next_lines(linhas, i, 3)
            if v:
                valor_total = v
                break
        if not valor_total and "V. TOTAL" in up and "PRODUTOS" in up:
            v = pick_last_money_on_same_or_next_lines(linhas, i, 2)
            if v:
                valor_total = v

    resultado = {
        "numero_nf": numero_nf,
        "serie": serie,
        "emitente_doc": emitente_doc,
        "emitente_nome": emitente_nome,
        "dest_doc": dest_doc,
        "dest_nome": dest_nome,
        "data_emissao": data_emissao,
        "valor_total": valor_total,
        "valor_total_num": moeda_to_float(valor_total),
    }
    return resultado

def extrair_texto_ocr(arquivo_pdf, progress_callback=None):

    global EASY_OCR
    if EASY_OCR is None:
        EASY_OCR = carregar_easy_ocr()
        if EASY_OCR is None:
            raise Exception("EasyOCR não está instalado ou configurado.")

    texto_total = ""
    doc = fitz.open(arquivo_pdf)
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        pix = page.get_pixmap(dpi=300)
        img = Image.open(io.BytesIO(pix.tobytes()))
        result = EASY_OCR.readtext(np.array(img), detail=0, paragraph=True)
        if isinstance(result, list):
            textos = []
            for item in result:
                if isinstance(item, str):
                    textos.append(item)
                elif isinstance(item, (list, tuple)) and len(item) >= 2:
                    textos.append(str(item[1]))
                elif isinstance(item, dict) and "text" in item:
                    textos.append(item["text"])
            texto_page = " ".join(textos)
        else:
            texto_page = str(result)

        texto_total += texto_page + "\n"

        if progress_callback:
            progress_callback(f"OCR: página {page_num+1}/{len(doc)}")

    return texto_total


def extrair_capa_de_pdf(arquivo_pdf: str, progress_callback=None) -> dict:
    nome_arquivo = Path(arquivo_pdf).name
    try:
        with pdfplumber.open(arquivo_pdf) as pdf:
            for page in pdf.pages:
                txt = page.extract_text() or ""
                if txt and len(txt.strip()) > 100:
                    dados = extrair_capa_de_texto(txt)
                    if any([dados["numero_nf"], dados["emitente_doc"], dados["dest_doc"], dados["valor_total"]]):
                        if progress_callback:
                            progress_callback(f"✅ pdfplumber: {nome_arquivo}")
                        return {"arquivo": nome_arquivo, **dados}
    except:
        pass

    try:
        if progress_callback:
            progress_callback(f"🔄 OCR: {nome_arquivo}")
        texto_ocr = extrair_texto_ocr(arquivo_pdf, progress_callback)
        if texto_ocr and len(texto_ocr.strip()) > 100:
            dados = extrair_capa_de_texto(texto_ocr)
            if any([dados["numero_nf"], dados["emitente_doc"], dados["dest_doc"], dados["valor_total"]]):
                if progress_callback:
                    progress_callback(f"✅ OCR: {nome_arquivo}")
                return {"arquivo": nome_arquivo, **dados}
    except Exception as e:
        if progress_callback:
            progress_callback(f"❌ {e}")

    vazio = {k: None for k in [
        "numero_nf","serie","emitente_doc","emitente_nome",
        "dest_doc","dest_nome","data_emissao","valor_total","valor_total_num"
    ]}
    return {"arquivo": nome_arquivo, **vazio}


def processar_pdfs(arquivos_pdf: list, progress_callback=None) -> pd.DataFrame:
    regs = []
    for i, pdf_path in enumerate(arquivos_pdf, 1):
        if progress_callback:
            progress_callback(f"[{i}/{len(arquivos_pdf)}] {Path(pdf_path).name}")
        regs.append(extrair_capa_de_pdf(pdf_path, progress_callback))
    df = pd.DataFrame(regs).drop_duplicates(subset=["arquivo"], keep="first")
    try:
        df["_ordem"] = pd.to_datetime(df["data_emissao"], format="%d/%m/%Y", errors="coerce")
        df = df.sort_values(by=["_ordem","arquivo"], na_position="last").drop(columns=["_ordem"])
    except:
        pass
    return df


def exportar_para_excel(df: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    df.to_excel(output, index=False, engine='openpyxl')
    output.seek(0)
    return output.getvalue()
