# extrator_final.py - Extrator robusto para NFes (texto + imagem + OCR melhorado)
import os, io, re, requests, time
from pathlib import Path
from datetime import datetime
from typing import Any, cast

import pdfplumber
import pandas as pd
from PIL import Image, ImageEnhance, ImageOps
import fitz  # PyMuPDF

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
    """Melhora imagem para OCR usando apenas PIL"""
    try:
        img = img.convert('RGB')
        
        # Aumentar resolução
        img = img.resize((img.width * 2, img.height * 2), Image.Resampling.LANCZOS)
        
        # Aumentar contraste
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(2)
        
        # Aumentar brilho se necessário
        enhancer_brightness = ImageEnhance.Brightness(img)
        img = enhancer_brightness.enhance(1.1)
        
        # Aumentar nitidez
        enhancer_sharp = ImageEnhance.Sharpness(img)
        img = enhancer_sharp.enhance(2)
        
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
    """Extrai dados de DANFE com suporte a múltiplos layouts"""
    numero_nf: str | None = None
    serie: str | None = None
    emitente_nome: str | None = None
    emitente_doc: str | None = None
    dest_nome: str | None = None
    dest_doc: str | None = None
    data_emissao: str | None = None
    valor_total: str | None = None

    linhas = texto.split("\n")

    # ========== ESTRATÉGIA 1: Buscar "Nº.: XXX.XXX.###" (layout mais comum) ==========
    for ln in linhas:
        if not numero_nf:
            # Padrão: "Nº.: 000.094.615" ou "Nº.: 000.000.671"
            m = re.search(r"N[°ºO]\.\s*[:\-]?\s*(\d{3}\.\d{3}\.\d{3,6})", ln)
            if m:
                cand = m.group(1).replace(".", "")
                try:
                    val = int(cand)
                    # Pegar últimos 6 dígitos que importam
                    numero_nf = str(val % 1000000)
                except:
                    pass
        
        # Série aparece logo após: "Série: 5" ou "SÉRIE:1"
        if not serie:
            m = re.search(r"S[ÉE]RIE\s*[:\-]?\s*(\d+)", ln, re.I)
            if m:
                try:
                    val = int(m.group(1))
                    if 0 <= val <= 999:
                        serie = str(val)
                except:
                    pass

    # ========== ESTRATÉGIA 2: Buscar EMITENTE ==========
    # Padrão: "IDENTIFICAÇÃO DO EMITENTE" seguido do nome
    for i, ln in enumerate(linhas):
        up = ln.upper()
        
        if "IDENTIFICAÇÃO DO EMITENTE" in up:
            # Próximas linhas têm o nome
            for j in range(i + 1, min(i + 5, len(linhas))):
                t = linhas[j].strip()
                if t and len(t) > 3 and not achar_doc_em_linha(t):
                    if not any(w in t.upper() for w in ["DANFE", "DOCUMENTO", "AUXILIAR", "BARRA", "CEP", "SALVADOR"]):
                        emitente_nome = t
                        break
        
        # CNPJ do emitente vem em linha com 14 dígitos ou formato XX.XXX.XXX/XXXX-XX
        if not emitente_doc and "IDENTIFICAÇÃO DO EMITENTE" in up:
            for j in range(i, min(i + 8, len(linhas))):
                d = achar_doc_em_linha(linhas[j])
                if d and len(somente_digitos(d)) == 14:
                    emitente_doc = d
                    break

    # ========== ESTRATÉGIA 3: Buscar DESTINATÁRIO ==========
    for i, ln in enumerate(linhas):
        up = ln.upper()
        
        if "DESTINATÁRIO" in up or "REMETENTE" in up:
            # Próximas linhas têm razão social e CNPJ
            for j in range(i + 1, min(i + 6, len(linhas))):
                linha_dest = linhas[j]
                
                # Procurar CNPJ
                doc_dest = achar_doc_em_linha(linha_dest)
                if doc_dest and len(somente_digitos(doc_dest)) == 14:
                    dest_doc = doc_dest
                    # Tentar extrair nome da mesma linha antes do CNPJ
                    partes = linha_dest.split(doc_dest)
                    if partes[0].strip():
                        dest_nome = partes[0].strip()

    # ========== ESTRATÉGIA 4: Buscar DATA DE EMISSÃO ==========
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

    # ========== ESTRATÉGIA 5: Buscar VALOR TOTAL ==========
    for i, ln in enumerate(linhas):
        up = ln.upper()
        
        # "VALOR TOTAL DA NOTA" é o padrão mais confiável
        if "VALOR TOTAL DA NOTA" in up:
            v = pick_last_money_on_same_or_next_lines(linhas, i, 3)
            if v:
                valor_total = v
                break
        
        # Alternativa: "V. TOTAL PRODUTOS"
        if not valor_total and "V. TOTAL" in up and "PRODUTOS" in up:
            v = pick_last_money_on_same_or_next_lines(linhas, i, 2)
            if v:
                valor_total = v

    resultado = cast(dict[str, Any], {
        "numero_nf": numero_nf,
        "serie": serie,
        "emitente_doc": emitente_doc,
        "emitente_nome": emitente_nome,
        "dest_doc": dest_doc,
        "dest_nome": dest_nome,
        "data_emissao": data_emissao,
        "valor_total": valor_total,
        "valor_total_num": moeda_to_float(valor_total),
    })
    return resultado

def extrair_numero_do_filename(filename: str) -> str | None:
    """Extrai número da NF do nome do arquivo - padrão: 'DANFE nº 672' ou 'Nº 672'"""
    # Procurar padrões comuns em nomes de arquivo
    patterns = [
        r"DANFE\s*n[°ºo]\s*(\d{3,6})",  # DANFE nº 672
        r"Nº\s*(\d{3,6})",               # Nº 672
        r"N°\s*(\d{3,6})",               # N° 672
        r"NF[- ]?(\d{3,6})",             # NF-672 ou NF 672
        r"nota[- ]?(\d{3,6})",           # nota-672
    ]
    
    for pattern in patterns:
        m = re.search(pattern, filename, re.I)
        if m:
            return m.group(1)
    
    return None

def extrair_capa_de_pdf(arquivo_pdf: str, progress_callback=None) -> dict:
    nome_arquivo = Path(arquivo_pdf).name
    
    # Tentar extrair número do filename como fallback
    numero_nf_do_filename = extrair_numero_do_filename(nome_arquivo)
    
    try:
        with pdfplumber.open(arquivo_pdf) as pdf:
            for page in pdf.pages:
                txt = page.extract_text() or ""
                if txt and len(txt.strip()) > 100:
                    dados = extrair_capa_de_texto(txt)
                    # Se não pegou número mas tem no filename, usar
                    if not dados["numero_nf"] and numero_nf_do_filename:
                        dados["numero_nf"] = numero_nf_do_filename
                    
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
            # Se não pegou número mas tem no filename, usar
            if not dados["numero_nf"] and numero_nf_do_filename:
                dados["numero_nf"] = numero_nf_do_filename
            
            if any([dados["numero_nf"], dados["emitente_doc"], dados["dest_doc"], dados["valor_total"]]):
                if progress_callback:
                    progress_callback(f"✅ OCR: {nome_arquivo}")
                return {"arquivo": nome_arquivo, **dados}
    except Exception as e:
        if progress_callback:
            progress_callback(f"❌ {e}")
    
    vazio = cast(dict[str, Any], {k: None for k in [
        "numero_nf","serie","emitente_doc","emitente_nome",
        "dest_doc","dest_nome","data_emissao","valor_total","valor_total_num"
    ]})
    
    # Mesmo que falhe, tentar pegar número do filename
    if numero_nf_do_filename:
        vazio["numero_nf"] = numero_nf_do_filename
    
    return {"arquivo": nome_arquivo, **vazio}

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