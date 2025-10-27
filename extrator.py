# extrator.py - Lógica de extração de NFs
import os, io, re, requests, time
from pathlib import Path
from datetime import datetime

import pdfplumber
import pandas as pd
import pytesseract
from PIL import Image
import fitz  # PyMuPDF

# =============== CONFIG ===============
DEBUG = False  # Desabilita debug em produção
CNPJ_CACHE: dict[str, dict] = {}

# =============== REGEX ===============
RE_MOEDA = re.compile(r"R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})")
RE_DATA  = re.compile(r"\b\d{2}/\d{2}/\d{4}\b")

RE_NF_MAIN   = re.compile(r"NOTA\s+FISCAL\s+ELETR[ÔO]NICA\s*N[ºO]?\s*([\d\.]+)", re.I)
RE_NF_ALT    = re.compile(r"\b(?:NF-?E|N[ºO]|NUM(?:ERO)?|NRO)\s*[:\-]?\s*([\d\.]+)", re.I)
RE_NF_NUMERO = re.compile(r"N[ºO\.]?\s*([\d\.]+)", re.I)
RE_NF_DUPLIC = re.compile(r"^(\d{1,6})/\d+\b")

RE_SERIE   = re.compile(r"S[ÉE]RIE\s*[: ]*\s*([0-9\.]{1,5})", re.I)

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

HEADERS = {"User-Agent": "NF-Cover-Extractor/1.0 (+github.com/)"}

# =============== UTILS ===============
def somente_digitos(s: str) -> str:
    return re.sub(r"\D", "", s or "")

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

# =============== CNPJ: raiz (…/0001-**) + DVs ===============
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
    """Recebe 14 dígitos e devolve a raiz com 0001 e DV corretos."""
    d = somente_digitos(cnpj_digits)
    if len(d) != 14:
        return d
    base8 = d[:8]
    base12 = base8 + "0001"
    dv1, dv2 = calcula_dvs_cnpj(base12)
    return base12 + str(dv1) + str(dv2)

# =============== CONSULTA CNPJ (múltiplas fontes) ===============
def _try_brasilapi(cnpj14: str) -> dict | None:
    try:
        url = f"https://brasilapi.com.br/api/cnpj/v1/{cnpj14}"
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            data = r.json()
            razao = data.get("razao_social") or data.get("nome_fantasia")
            if razao:
                return {"nome": razao, "fonte": "brasilapi"}
    except Exception as e:
        if DEBUG: print(f"[BRASILAPI ERRO] {cnpj14}: {e}")
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
    except Exception as e:
        if DEBUG: print(f"[PUBLICA ERRO] {cnpj14}: {e}")
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
    except Exception as e:
        if DEBUG: print(f"[RECEITAWS ERRO] {cnpj14}: {e}")
    return None

def consulta_nome_por_cnpj(cnpj_raw: str, usar_raiz=True) -> str | None:
    """Consulta nome oficial por CNPJ, com opção de forçar raiz 0001."""
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

# =============== EXTRAÇÃO ===============
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

        if not emitente_nome and i < 12:
            t = ln.strip()
            if t and not achar_doc_em_linha(t) and not re.search(r"\d", t) and not is_headerish(t):
                if not any(w in IGNORAR_NOMES_EMIT for w in t.upper().split()):
                    emitente_nome = t

        if not emitente_doc:
            d = achar_doc_em_linha(ln)
            if d:
                emitente_doc = d

        if ("IDENTIFICAÇÃO DO EMITENTE" in up) or (up == "EMITENTE"):
            sec = "emitente"; dest_header_seen = False; continue
        if up.startswith("DESTINAT"):
            sec = "dest"; dest_header_seen = False; continue
        if "DADOS DOS PRODUTOS" in up or "CÁLCULO DO IMPOSTO" in up or "CALCULO DO IMPOSTO" in up:
            sec = None; dest_header_seen = False

        if not numero_nf:
            m = re.search(r"(?:NF-?E|N[ºO]|NUM(?:ERO)?|NRO)\s*[:\-]?\s*(\d{1,6})", ln, re.I)
            if not m: m = RE_NF_MAIN.search(ln) or RE_NF_ALT.search(ln) or RE_NF_NUMERO.search(ln)
            if not m: m = RE_NF_DUPLIC.search(ln)
            if m:
                cand = m.group(1).replace(".", "").strip()
                try:
                    val = int(cand)
                    if 1 <= val <= 999999:
                        numero_nf = str(val)
                except: pass

        if not serie:
            ms = RE_SERIE.search(ln)
            if ms:
                s = ms.group(1).replace(".", "").strip()
                try: serie = str(int(s))
                except: serie = s

        if sec == "emitente" and not emitente_nome:
            t = ln.strip()
            if t and not achar_doc_em_linha(t) and not re.search(r"\d", t) and not is_headerish(t):
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
                if 2006 <= int(yyyy) <= 2035:
                    data_emissao = md.group(0)

        if "TOTAL DA NOTA" in up and not valor_total:
            v = pick_last_money_on_same_or_next_lines(linhas, i, 6)
            if v: valor_total = v
            continue
        if ("TOTAL DOS PRODUTOS" in up or "VALOR TOTAL" in up) and not valor_total:
            v = pick_last_money_on_same_or_next_lines(linhas, i, 6)
            if v: candidato_total_produtos = v

    if not valor_total and candidato_total_produtos:
        valor_total = candidato_total_produtos

    if not numero_nf:
        for ln in linhas:
            m = re.search(r"\b\d{3,6}\b", ln)
            if m and not achar_doc_em_linha(ln):
                numero_nf = m.group(0)
                break

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
                if txt:
                    dados = extrair_capa_de_texto(txt)
                    if any([dados["numero_nf"], dados["emitente_doc"], dados["dest_doc"], dados["valor_total"]]):
                        return {"arquivo": Path(arquivo_pdf).name, **dados}
    except Exception as e:
        if progress_callback:
            progress_callback(f"⚠️ Erro ao ler PDF: {e}")

    # Fallback OCR
    try:
        if progress_callback:
            progress_callback(f"🔄 Usando OCR em: {Path(arquivo_pdf).name}")
        doc = fitz.open(arquivo_pdf)
        acum_txt = []
        for p in range(doc.page_count):
            pix = doc.load_page(p).get_pixmap()
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            acum_txt.append(pytesseract.image_to_string(img, lang="por"))
        dados = extrair_capa_de_texto("\n".join(acum_txt))
        return {"arquivo": Path(arquivo_pdf).name, **dados}
    except Exception as e:
        if progress_callback:
            progress_callback(f"❌ Falha OCR: {e}")
        vazio = {k: None for k in [
            "numero_nf","serie","emitente_doc","emitente_nome",
            "dest_doc","dest_nome","data_emissao","valor_total","valor_total_num"
        ]}
        return {"arquivo": Path(arquivo_pdf).name, **vazio}

# =============== ENRIQUECIMENTO POR CNPJ ===============
def enriquecer_com_cnpj(df: pd.DataFrame, progress_callback=None) -> pd.DataFrame:
    for idx, row in df.iterrows():
        em_doc = row.get("emitente_doc")
        if em_doc:
            cnpj_digits = somente_digitos(em_doc)
            if len(cnpj_digits) == 14:
                nome_cnpj = consulta_nome_por_cnpj(cnpj_digits, usar_raiz=True)
                if nome_cnpj:
                    if row.get("emitente_nome") != nome_cnpj:
                        if progress_callback:
                            progress_callback(f"✓ Enriquecido: {nome_cnpj}")
                        df.at[idx, "emitente_nome"] = nome_cnpj

        de_doc = row.get("dest_doc")
        if de_doc:
            d_digits = somente_digitos(de_doc)
            if len(d_digits) == 14:
                nome_cnpj = consulta_nome_por_cnpj(d_digits, usar_raiz=True)
                if nome_cnpj:
                    if row.get("dest_nome") != nome_cnpj:
                        df.at[idx, "dest_nome"] = nome_cnpj
    return df

# =============== PROCESSAMENTO DE ARQUIVOS ===============
def processar_pdfs(arquivos_pdf: list, progress_callback=None) -> pd.DataFrame:
    """
    Processa uma lista de caminhos de PDFs
    progress_callback: função para atualizar progresso no Streamlit
    """
    regs = []
    for i, pdf_path in enumerate(arquivos_pdf, 1):
        if progress_callback:
            progress_callback(f"[{i}/{len(arquivos_pdf)}] Processando: {Path(pdf_path).name}")
        regs.append(extrair_capa_de_pdf(pdf_path, progress_callback))

    df = pd.DataFrame(regs).drop_duplicates(subset=["arquivo"], keep="first")

    # Ordenar por data
    try:
        df["_ordem"] = pd.to_datetime(df["data_emissao"], format="%d/%m/%Y", errors="coerce")
        df = df.sort_values(by=["_ordem","arquivo"], na_position="last").drop(columns=["_ordem"])
    except Exception:
        pass

    # Enriquecer com CNPJ
    if progress_callback:
        progress_callback("🔍 Enriquecendo dados com informações de CNPJ...")
    df = enriquecer_com_cnpj(df, progress_callback)
    
    return df

def exportar_para_excel(df: pd.DataFrame) -> bytes:
    """Exporta DataFrame para bytes Excel"""
    output = io.BytesIO()
    df.to_excel(output, index=False, engine='openpyxl')
    output.seek(0)
    return output.getvalue()
