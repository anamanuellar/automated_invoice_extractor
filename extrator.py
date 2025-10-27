# extrator_final.py - Extrator robusto para NFes (texto + imagem + OCR melhorado)
import os, io, re, requests, time
from pathlib import Path
from datetime import datetime
from typing import Any

import pdfplumber
import pandas as pd
from PIL import Image, ImageEnhance
import fitz  # PyMuPDF
import cv2
import numpy as np

# =============== CONFIG ===============
DEBUG = False
CNPJ_CACHE: dict[str, dict] = {}

# =============== REGEX ===============
RE_MOEDA = re.compile(r"R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})")
RE_DATA  = re.compile(r"\b\d{2}/\d{2}/\d{4}\b")

RE_NF_MAIN   = re.compile(r"NOTA\s+FISCAL\s+ELETR[ÔO]NICA\s*N[ºO]?\s*([\d\.]+)", re.I)
RE_NF_ALT    = re.compile(r"\b(?:NF-?E|N[ºO]|NUM(?:ERO)?|NRO)\s*[:\-]?\s*([\d\.]+)", re.I)
RE_NF_NUMERO = re.compile(r"N[ºO\.]?\s*[:\-]?\s*(\d{1,6})", re.I)

RE_SERIE   = re.compile(r"S[ÉE]RIE\s*[:\-]?\s*([0-9\.]{1,5})", re.I)
RE_SERIE_ALT = re.compile(r"(?:^|\n)S[ÉE]RIE\s*[:\-]?\s*(\d+)", re.I)

RE_CNPJ_MASK   = re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")
RE_CNPJ_PLAIN  = re.compile(r"\b\d{14}\b")
RE_CPF_MASK    = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")
RE_CPF_PLAIN   = re.compile(r"\b\d{11}\b")

IGNORAR_NOMES_EMIT = {
    "DANFE","DOCUMENTO","AUXILIAR","NOTA","FISCAL","ELETRÔNICA","ELETRONICA",
    "DOCUMENTO AUXILIAR DA","NOTA FISCAL","DOCUMENTO AUXILIAR"
}

HEADER_KEYWORDS = {
    "NOME","RAZÃO","RAZAO","CNPJ","CPF","DATA","ENDEREÇO","ENDERECO",
    "INSCRIÇÃO","INSCRICAO","CEP","MUNICÍPIO","MUNICIPIO","BAIRRO",
    "DISTRITO","FONE","FAX","HORA","UF","NATUREZA DA OPERAÇÃO","PROTOCOLO",
    "CHAVE DE ACESSO","SEFAZ","SITE","DANFE"
}

HEADERS = {"User-Agent": "NF-Cover-Extractor/1.0"}

EASY_OCR = None

def carregar_easy_ocr():
    """Carrega EasyOCR"""
    try:
        import easyocr
        reader = easyocr.Reader(['pt', 'en'], gpu=False)
        return reader
    except:
        return None

# =============== UTILS ===============
def somente_digitos(s: str | Any) -> str:
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

def achar_doc_em_linha(s: str) -> str | None:
    m = RE_CNPJ_MASK.search(s) or RE_CPF_MASK.search(s)
    if m: return m.group(0)
    m = RE_CNPJ_PLAIN.search(s)
    if m: return fmt_cnpj(m.group(0))
    m = RE_CPF_PLAIN.search(s)
    if m: return fmt_cpf(m.group(0))
    return None

def moeda_to_float(s: str | None) -> float | None:
    if not s: return None
    try: return float(s.replace(".", "").replace(",", "."))
    except: return None

def is_headerish(s: str) -> bool:
    up = s.upper()
    return any(k in up for k in HEADER_KEYWORDS)

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

# =============== CNPJ ===============
def calcula_dvs_cnpj(base12: str) -> tuple[int,int]:
    nums = [int(x) for x in base12]
    pesos1 = [5,4,3,2,9,8,7,6,5,4,3,2]
    s1 = sum(n*p for n,p in zip(nums, pesos1))
    r1 = s1 % 11
    dv1 = 0 if r1 < 2 else 11 - r1
    pesos2 = [6,5,4,3,2,9,8,7,6,5,4,3,2]
    nums2 = nums + [dv1]
    s2 = sum(n*p for n,p in zip(nums2, pesos2))
    r2 = s2 % 11
    dv2 = 0 if r2 < 2 else 11 - r2
    return dv1, dv2

def cnpj_raiz_0001(cnpj_digits: str) -> str:
    d = somente_digitos(cnpj_digits)
    if len(d) != 14:
        return d
    base8 = d[:8]
    base12 = base8 + "0001"
    dv1, dv2 = calcula_dvs_cnpj(base12)
    return base12 + str(dv1) + str(dv2)

def _try_brasilapi(cnpj14: str) -> dict | None:
    try:
        url = f"https://brasilapi.com.br/api/cnpj/v1/{cnpj14}"
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            data = r.json()
            razao = data.get("razao_social") or data.get("nome_fantasia")
            if razao:
                return {"nome": razao, "fonte": "brasilapi"}
    except:
        pass
    return None

def _try_publica(cnpj14: str) -> dict | None:
    try:
        url = f"https://publica.cnpj.ws/cnpj/{cnpj14}"
        r = requests.get(url, headers=HEADERS, timeout=12)
        if r.status_code == 200:
            data = r.json()
            razao = data.get("razao_social") or (data.get("estabelecimento") or {}).get("razao_social")
            if razao:
                return {"nome": razao, "fonte": "publica"}
    except:
        pass
    return None

def _try_receitaws(cnpj14: str) -> dict | None:
    try:
        url = f"https://www.receitaws.com.br/v1/cnpj/{cnpj14}"
        r = requests.get(url, headers=HEADERS, timeout=12)
        if r.status_code == 200:
            data = r.json()
            if (data.get("status") or "").upper() == "OK":
                nome = data.get("nome") or data.get("fantasia")
                if nome:
                    return {"nome": nome, "fonte": "receitaws"}
    except:
        pass
    return None

def consulta_nome_por_cnpj(cnpj_raw: str, usar_raiz=True) -> str | None:
    if not cnpj_raw:
        return None
    d = somente_digitos(cnpj_raw)
    if len(d) != 14:
        return None

    if usar_raiz:
        d = cnpj_raiz_0001(d)

    if d in CNPJ_CACHE:
        return CNPJ_CACHE[d].get("nome")

    for fn in (_try_brasilapi, _try_publica, _try_receitaws):
        data = fn(d)
        if data and data.get("nome"):
            CNPJ_CACHE[d] = data
            return data.get("nome")
        time.sleep(0.2)

    CNPJ_CACHE[d] = {"nome": None, "fonte": None}
    return None

# =============== PROCESSAMENTO DE IMAGEM ===============
def melhorar_imagem_para_ocr(img: Image.Image) -> Image.Image:
    """Melhora imagem para OCR com CLAHE"""
    try:
        img = img.convert('RGB')
        img = img.resize((img.width * 2, img.height * 2), Image.Resampling.LANCZOS)
        
        img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        
        lab = cv2.cvtColor(img_cv, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        l = clahe.apply(l)
        lab = cv2.merge([l, a, b])
        img_cv = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
        
        img = Image.fromarray(cv2.cvtColor(img_cv, cv2.COLOR_BGR2RGB))
        
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(2)
        
        return img
    except:
        return img

def extrair_texto_ocr(pdf_path: str, progress_callback=None) -> str:
    """Extrai texto com EasyOCR"""
    global EASY_OCR
    
    texto_acumulado = []
    
    try:
        if EASY_OCR is None:
            if progress_callback:
                progress_callback("📥 Carregando EasyOCR...")
            EASY_OCR = carregar_easy_ocr()
        
        if not EASY_OCR:
            return ""
        
        doc = fitz.open(pdf_path)
        
        for page_num in range(doc.page_count):
            try:
                page = doc.load_page(page_num)
                mat = fitz.Matrix(3, 3)
                pix = page.get_pixmap(matrix=mat)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                
                img = melhorar_imagem_para_ocr(img)
                
                resultado = EASY_OCR.readtext(img)
                
                if resultado:
                    for item in resultado:
                        if isinstance(item, (list, tuple)) and len(item) >= 2:
                            texto_str = str(item[1]) if len(item) > 1 else ""
                            confianca_val = float(item[2]) if len(item) > 2 else 0.0
                            
                            if texto_str and len(texto_str.strip()) > 0 and confianca_val > 0.2:
                                texto_acumulado.append(texto_str)
                
            except:
                continue
        
        doc.close()
        return "\n".join(texto_acumulado)
    
    except:
        return ""

# =============== EXTRAÇÃO DE TEXTO ===============
def extrair_capa_de_texto(texto: str) -> dict:
    numero_nf = serie = None
    emitente_nome = emitente_doc = None
    dest_nome = dest_doc = None
    data_emissao = None
    valor_total = None
    candidato_total_produtos = None

    linhas = texto.split("\n")
    sec = None
    dest_header_seen = False

    for i, ln in enumerate(linhas):
        up = ln.upper().strip()

        if not numero_nf:
            m = re.search(r"N[°ºO]\s*[:\-]?\s*(\d{3,6})", ln)
            if m:
                cand = m.group(1)
                try:
                    val = int(cand)
                    if 1 <= val <= 999999:
                        numero_nf = str(val)
                except:
                    pass
            
            if not numero_nf:
                for pattern in [RE_NF_MAIN, RE_NF_ALT, RE_NF_NUMERO]:
                    m = pattern.search(ln)
                    if m:
                        cand = m.group(1).replace(".", "").strip()
                        try:
                            val = int(cand)
                            if 1 <= val <= 999999:
                                numero_nf = str(val)
                                break
                        except:
                            pass

        if not serie:
            for pattern in [RE_SERIE, RE_SERIE_ALT]:
                m = pattern.search(ln)
                if m:
                    s = m.group(1).replace(".", "").strip()
                    try: 
                        serie = str(int(s))
                    except: 
                        serie = s
                    if serie:
                        break

        if not emitente_nome and i < 15:
            t = ln.strip()
            if (t and len(t) > 3 and 
                not achar_doc_em_linha(t) and 
                not re.search(r"^\d+$", t) and
                not is_headerish(t)):
                if not any(w in IGNORAR_NOMES_EMIT for w in t.upper().split()):
                    emitente_nome = t

        if not emitente_doc:
            d = achar_doc_em_linha(ln)
            if d:
                emitente_doc = d

        if ("IDENTIFICAÇÃO DO EMITENTE" in up) or (up == "EMITENTE"):
            sec = "emitente"
            dest_header_seen = False
            continue
        if up.startswith("DESTINAT"):
            sec = "dest"
            dest_header_seen = False
            continue
        if "DADOS DOS PRODUTOS" in up or "CÁLCULO DO IMPOSTO" in up or "CALCULO DO IMPOSTO" in up:
            sec = None
            dest_header_seen = False

        if sec == "emitente" and not emitente_nome:
            t = ln.strip()
            if (t and len(t) > 3 and
                not achar_doc_em_linha(t) and 
                not re.search(r"^\d+$", t) and
                not is_headerish(t)):
                if not any(w in IGNORAR_NOMES_EMIT for w in t.upper().split()):
                    emitente_nome = t

        if sec == "dest":
            if ("NOME" in up and ("CNPJ" in up or "CPF" in up) and "DATA" in up):
                dest_header_seen = True
                continue
            mdoc = achar_doc_em_linha(ln)
            if mdoc:
                if not dest_doc:
                    dest_doc = mdoc
                if not dest_nome:
                    nome = ln.split(mdoc)[0].strip(" -–—\t")
                    if nome and not is_headerish(nome):
                        dest_nome = nome
                continue
            if dest_header_seen and not dest_nome:
                t = ln.strip()
                if t and not achar_doc_em_linha(t) and not is_headerish(t):
                    dest_nome = t

        if not data_emissao:
            md = RE_DATA.search(ln)
            if md:
                dd, mm, yyyy = md.group(0).split("/")
                try:
                    if 2006 <= int(yyyy) <= 2035:
                        data_emissao = md.group(0)
                except:
                    pass

        if "TOTAL DA NOTA" in up and not valor_total:
            v = pick_last_money_on_same_or_next_lines(linhas, i, 6)
            if v: 
                valor_total = v
            continue
        if ("TOTAL DOS PRODUTOS" in up or "VALOR TOTAL" in up) and not valor_total:
            v = pick_last_money_on_same_or_next_lines(linhas, i, 6)
            if v: 
                candidato_total_produtos = v
        if "VALOR LÍQUIDO" in up and not valor_total:
            v = pick_last_money_on_same_or_next_lines(linhas, i, 3)
            if v:
                valor_total = v

    if not valor_total and candidato_total_produtos:
        valor_total = candidato_total_produtos

    if not numero_nf:
        for ln in linhas:
            m = re.search(r"\b(\d{3,6})\b", ln)
            if m and not achar_doc_em_linha(ln):
                cand = m.group(1)
                try:
                    if 1 <= int(cand) <= 999999:
                        numero_nf = cand
                        break
                except:
                    pass

    return {
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

def extrair_capa_de_pdf(arquivo_pdf: str, progress_callback=None) -> dict:
    try:
        with pdfplumber.open(arquivo_pdf) as pdf:
            for page in pdf.pages:
                txt = page.extract_text() or ""
                if txt and len(txt.strip()) > 100:
                    dados = extrair_capa_de_texto(txt)
                    if any([dados["numero_nf"], dados["emitente_doc"], dados["dest_doc"], dados["valor_total"]]):
                        if progress_callback:
                            progress_callback(f"✅ pdfplumber: {Path(arquivo_pdf).name}")
                        return {"arquivo": Path(arquivo_pdf).name, **dados}
    except:
        pass

    try:
        if progress_callback:
            progress_callback(f"🔄 OCR: {Path(arquivo_pdf).name}")
        
        texto_ocr = extrair_texto_ocr(arquivo_pdf, progress_callback)
        
        if texto_ocr and len(texto_ocr.strip()) > 100:
            dados = extrair_capa_de_texto(texto_ocr)
            if any([dados["numero_nf"], dados["emitente_doc"], dados["dest_doc"], dados["valor_total"]]):
                if progress_callback:
                    progress_callback(f"✅ OCR: {Path(arquivo_pdf).name}")
                return {"arquivo": Path(arquivo_pdf).name, **dados}
    except Exception as e:
        if progress_callback:
            progress_callback(f"❌ {e}")
    
    vazio = {k: None for k in [
        "numero_nf","serie","emitente_doc","emitente_nome",
        "dest_doc","dest_nome","data_emissao","valor_total","valor_total_num"
    ]}
    return {"arquivo": Path(arquivo_pdf).name, **vazio}

def enriquecer_com_cnpj(df: pd.DataFrame, progress_callback=None) -> pd.DataFrame:
    for idx in df.index:
        em_doc = df.loc[idx, "emitente_doc"]
        if em_doc:
            cnpj_digits = somente_digitos(em_doc)
            if len(cnpj_digits) == 14:
                nome_cnpj = consulta_nome_por_cnpj(cnpj_digits, usar_raiz=True)
                if nome_cnpj:
                    if df.loc[idx, "emitente_nome"] != nome_cnpj:
                        if progress_callback:
                            progress_callback(f"✓ {nome_cnpj}")
                        df.loc[idx, "emitente_nome"] = nome_cnpj

        de_doc = df.loc[idx, "dest_doc"]
        if de_doc:
            d_digits = somente_digitos(de_doc)
            if len(d_digits) == 14:
                nome_cnpj = consulta_nome_por_cnpj(d_digits, usar_raiz=True)
                if nome_cnpj:
                    if df.loc[idx, "dest_nome"] != nome_cnpj:
                        df.loc[idx, "dest_nome"] = nome_cnpj
    return df

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

    if progress_callback:
        progress_callback("🔍 Enriquecendo...")
    df = enriquecer_com_cnpj(df, progress_callback)
    
    return df

def exportar_para_excel(df: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    df.to_excel(output, index=False, engine='openpyxl')
    output.seek(0)
    return output.getvalue()