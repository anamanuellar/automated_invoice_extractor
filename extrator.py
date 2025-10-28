import os, io, re, requests, time
from pathlib import Path
from datetime import datetime
from typing import Any, cast

import pdfplumber
import pandas as pd

# =============== CONFIG ===============
DEBUG = True
CNPJ_CACHE: dict[str, dict] = {}

# =============== REGEX ===============
RE_MOEDA = re.compile(r"R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})")
RE_DATA  = re.compile(r"\b\d{2}/\d{2}/\d{4}\b")

def somente_digitos(s: str | Any) -> str:
    s_str = str(s) if s is not None else ""
    return re.sub(r"\D", "", s_str or "")

def fmt_cnpj(cnpj_digits: str) -> str:
    d = somente_digitos(cnpj_digits)
    if len(d) != 14: return cnpj_digits
    return f"{d[0:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:14]}"

def achar_doc_em_linha(s: str) -> str | None:
    m = re.search(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", s)
    if m: return m.group(0)
    m = re.search(r"\b\d{14}\b", s)
    if m: return fmt_cnpj(m.group(0))
    return None

def moeda_to_float(s: str | None) -> float | None:
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

# =============== ROTAÇÃO ===============
def detectar_rotacao(texto: str) -> bool:
    """Detecta se o PDF tem partes rotacionadas"""
    # Se tem MAIS padrões invertidos que normais, considerar rotacionado
    padroes_invertidos = ["e-FN", ".odal", "adacidni"]
    padroes_normais = ["NF-e", "valor", "indicada"]
    
    inv_count = sum(1 for p in padroes_invertidos if p in texto)
    norm_count = sum(1 for p in padroes_normais if p in texto)
    
    # Se tem mais padrões invertidos OU tem muitos padrões invertidos, considerar rotação
    if inv_count > norm_count or inv_count >= 2:
        return True
    return False

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
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            razao = data.get("razao_social") or data.get("nome_fantasia")
            if razao:
                return {"nome": razao, "fonte": "brasilapi"}
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
    data = _try_brasilapi(d)
    if data and data.get("nome"):
        CNPJ_CACHE[d] = data
        return data.get("nome")
    time.sleep(0.1)
    CNPJ_CACHE[d] = {"nome": None, "fonte": None}
    return None


def extrair_emitente_do_filename(nome_arquivo: str) -> tuple[str | None, str | None]:
    """Extrai nome do emitente do nome do arquivo"""
    # Remove extensão
    nome = nome_arquivo.replace('.pdf', '')
    
    # Padrão: "DANFE <NOME> - Nº <NUM>" ou "DANFE Nº <NUM> - <NOME>"
    # Extrai tudo entre "DANFE" e "- nº" ou "- Nº"
    
    m = re.search(r"DANFE\s+(?:nº|Nº)?\s*(\d+)?\s*-?\s*(.+?)(?:\s*-\s*nº|\s*-\s*Nº|\s*-\s*–)?\s*\d*$", nome, re.I)
    if m and m.lastindex and m.lastindex >= 2:
        emitente = m.group(2).strip()
        if emitente:
            return emitente, None
    
    # Padrão alternativo: "NF <NOME> - Nº <NUM>"
    m = re.search(r"NF\s+(.+?)\s*-\s*Nº\s*\d+", nome, re.I)
    if m:
        emitente = m.group(1).strip()
        if emitente:
            return emitente, None
    
    return None, None


def extrair_capa_de_texto(texto: str) -> dict[str, Any]:
    """Extrai dados usando regex robustos (inspirado em parse_danfe_text)"""
    
    if detectar_rotacao(texto):
        if DEBUG:
            print("  🔄 Rotação detectada, invertendo texto...")
        texto = texto[::-1]
    
    # Normalizar: remover acentos e múltiplos espaços
    texto_norm = re.sub(r"\s+", " ", texto)
    
    numero_nf: str | None = None
    serie: str | None = None
    emitente_nome: str | None = None
    emitente_doc: str | None = None
    dest_nome: str | None = None
    dest_doc: str | None = None
    data_emissao: str | None = None
    valor_total: str | None = None

    # ========== NF e Série ==========
    m = re.search(r"N[oº]?\s*:?\s*(\d+)\s+S[ée]rie\s*:?\s*(\d+)", texto_norm, re.I)
    if m:
        numero_nf = m.group(1)
        serie = m.group(2)
        if DEBUG:
            print(f"    ✓ NF: {numero_nf}, Série: {serie}")
    
    # ========== Data ==========
    m = re.search(r"Emiss[ãa]o[^0-9]*(\d{2}/\d{2}/\d{4})", texto_norm, re.I)
    if m:
        data_emissao = m.group(1)
        if DEBUG:
            print(f"    ✓ Data: {data_emissao}")
    
    # ========== Valor Total ==========
    m = re.search(r"Valor\s+Total(?:\s+da\s+Nota)?\s*[:\-]?\s*R\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})", texto_norm, re.I)
    if m:
        valor_total = m.group(1)
        if DEBUG:
            print(f"    ✓ Valor: {valor_total}")
    
    # ========== Emitente Nome ==========
    m = re.search(r"(?:Emitente|Remetente)\s*[:\-]?\s*([^\n]{5,80}?)(?:\n|$)", texto_norm, re.I)
    if m:
        emitente_nome = m.group(1).strip()
        if DEBUG and emitente_nome:
            print(f"    ✓ Nome Emit: {emitente_nome[:50]}")
    
    # ========== CNPJ/CPF (prioriza emitente depois destinatário) ==========
    docs = re.findall(r"(?:CNPJ|CPF)[^0-9]*([0-9\.\-/]{11,18})", texto_norm, re.I)
    docs_limpos = [somente_digitos(d) for d in docs]
    
    if docs_limpos:
        emitente_doc = docs_limpos[0]
        if len(docs_limpos) > 1:
            dest_doc = docs_limpos[1]
        if DEBUG and emitente_doc:
            print(f"    ✓ CNPJ Emit: {emitente_doc}")
        if DEBUG and dest_doc:
            print(f"    ✓ CNPJ Dest: {dest_doc}")
    
    # ========== Destinatário Nome ==========
    m = re.search(r"(?:Destinat[aá]rio|Consumidor)\s*[:\-]?\s*([^\n]{3,80}?)(?:\n|$)", texto_norm, re.I)
    if m:
        dest_nome = m.group(1).strip()
        if DEBUG and dest_nome:
            print(f"    ✓ Nome Dest: {dest_nome[:50]}")

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


def extrair_capa_de_pdf(arquivo_pdf: str, progress_callback=None) -> dict:
    """Extrai informações da capa do PDF"""
    nome_arquivo = Path(arquivo_pdf).name
    
    try:
        with pdfplumber.open(arquivo_pdf) as pdf:
            for page in pdf.pages:
                txt = page.extract_text() or ""
                if txt and len(txt.strip()) > 100:
                    dados = extrair_capa_de_texto(txt)
                    
                    if any([dados["numero_nf"], dados["emitente_doc"], dados["dest_doc"], dados["valor_total"]]):
                        if progress_callback:
                            progress_callback(f"✅ {nome_arquivo}")
                        return {"arquivo": nome_arquivo, **dados}
    except Exception as e:
        if progress_callback:
            progress_callback(f"❌ {str(e)}")
    
    vazio = cast(dict[str, Any], {k: None for k in [
        "numero_nf","serie","emitente_doc","emitente_nome",
        "dest_doc","dest_nome","data_emissao","valor_total","valor_total_num"
    ]})
    
    return {"arquivo": nome_arquivo, **vazio}


def enriquecer_com_cnpj(df: pd.DataFrame, progress_callback=None) -> pd.DataFrame:
    """Enriquece dados com nomes dos CNPJs"""
    for idx in df.index:
        em_doc = df.loc[idx, "emitente_doc"]
        if em_doc and isinstance(em_doc, str) and not df.loc[idx, "emitente_nome"]:
            nome_cnpj = consulta_nome_por_cnpj(em_doc, usar_raiz=True)
            if nome_cnpj:
                if progress_callback:
                    progress_callback(f"✓ Emit: {nome_cnpj}")
                df.loc[idx, "emitente_nome"] = nome_cnpj

        de_doc = df.loc[idx, "dest_doc"]
        if de_doc and isinstance(de_doc, str) and not df.loc[idx, "dest_nome"]:
            nome_cnpj = consulta_nome_por_cnpj(de_doc, usar_raiz=True)
            if nome_cnpj:
                if progress_callback:
                    progress_callback(f"✓ Dest: {nome_cnpj}")
                df.loc[idx, "dest_nome"] = nome_cnpj
    
    return df


def processar_pdfs(arquivos_pdf: list, progress_callback=None) -> pd.DataFrame:
    """Processa lista de PDFs"""
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


# =============== TESTE =================
if __name__ == "__main__":
    print("🧪 Testando extrator...\n")
    
    pdfs = [
        "/mnt/user-data/uploads/DANFE_DELL_COMPUTADORES_DO_BRASIL_LTDA_-_nº_7686026.pdf",
        "/mnt/user-data/uploads/DANFE_EBAZAR_-_Nº_54013637.pdf",
    ]
    
    def callback(msg):
        print(f"  {msg}")
    
    df = processar_pdfs(pdfs, callback)
    
    print("\n" + "="*100)
    print("RESULTADOS:")
    print("="*100)
    print(df.to_string())
    
    # Salvar em CSV
    df.to_csv("/mnt/user-data/outputs/resultados_finais.csv", index=False)
    print("\n✅ Salvo em: /mnt/user-data/outputs/resultados_finais.csv")