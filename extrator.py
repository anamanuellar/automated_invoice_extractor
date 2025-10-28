from typing import Any, Optional, List, Dict
import os, io, re, requests, time
from pathlib import Path
from datetime import datetime
import numpy as np
import pdfplumber
import pandas as pd
from PIL import Image, ImageEnhance, ImageOps
import fitz # PyMuPDF
from codigos_fiscais import analisar_nf
from codigos_fiscais_destinatario import analisar_nf_como_destinatario, gerar_resumo_analise
import json

# ==================== CACHE HÍBRIDO (DISCO + MEMÓRIA + STREAMLIT) ====================

import hashlib, json, streamlit as st

# Diretório para armazenar resultados já processados
CACHE_DIR = "cache_nf"
os.makedirs(CACHE_DIR, exist_ok=True)

# Cache em memória para CNPJs e resultados de NF
CNPJ_CACHE: dict[str, Optional[str]] = {}
NF_MEM_CACHE: dict[str, dict] = {}

def get_pdf_hash(pdf_path: str) -> str:
    """Gera um hash MD5 único do conteúdo do PDF"""
    with open(pdf_path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()

def carregar_cache_nf(hash_pdf: str) -> Optional[dict]:
    """Tenta carregar o resultado do cache em disco"""
    # 1️⃣ Cache em memória (mais rápido)
    if hash_pdf in NF_MEM_CACHE:
        return NF_MEM_CACHE[hash_pdf]

    # 2️⃣ Cache em disco (persistente)
    path = os.path.join(CACHE_DIR, f"{hash_pdf}.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            NF_MEM_CACHE[hash_pdf] = data
            return data
    return None

def salvar_cache_nf(hash_pdf: str, data: dict):
    """Salva o resultado do processamento da NF no cache em disco e memória"""
    NF_MEM_CACHE[hash_pdf] = data
    path = os.path.join(CACHE_DIR, f"{hash_pdf}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# =============== CONFIG (MANTIDO) ===============
DEBUG = True
CNPJ_CACHE: dict[str, Optional[str]] = {}
EASY_OCR = None # Inicializar a variável global para evitar erros

# =============== REGEX (MANTIDO) ===============
RE_MOEDA = re.compile(r"R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})")
RE_DATA = re.compile(r"\b\d{2}/\d{2}/\d{4}\b")

RE_NF_MAIN  = re.compile(r"NOTA\s+FISCAL\s+ELETR[ÔO]NICA\s*N[ºO]?\s*([\d\.]+)", re.I)
RE_NF_ALT  = re.compile(r"\b(?:NF-?E|N[ºO]|NUM(?:ERO)?|NRO)\s*[:\-]?\s*([\d\.]+)", re.I)
RE_NF_NUMERO = re.compile(r"N[ºO\.]?\s*[:\-]?\s*(\d{1,6})", re.I)

RE_SERIE   = re.compile(r"S[ÉE]RIE\s*[:\-]?\s*([0-9\.]{1,5})", re.I)
RE_SERIE_ALT = re.compile(r"(?:^|\n)S[ÉE]RIE\s*[:\-]?\s*(\d+)", re.I)

RE_CNPJ_MASK  = re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")
RE_CNPJ_PLAIN = re.compile(r"\b\d{14}\b")
RE_CPF_MASK  = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")
RE_CPF_PLAIN  = re.compile(r"\b\d{11}\b")

# =============== UTILS (MANTIDO) ===============
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

# Consulta API para enriquecer nome emitente a partir do CNPJ (Corrigida)

# ==================== CACHE PERSISTENTE DE CNPJ ====================

CACHE_CNPJ_FILE = "cache_cnpj.json"
CNPJ_CACHE: dict[str, Optional[str]] = {}

def carregar_cache_cnpj():
    """Carrega cache persistente de CNPJs se existir."""
    global CNPJ_CACHE
    if os.path.exists(CACHE_CNPJ_FILE):
        try:
            with open(CACHE_CNPJ_FILE, "r", encoding="utf-8") as f:
                CNPJ_CACHE = json.load(f)
            if DEBUG:
                print(f"[DEBUG] Cache CNPJ carregado: {len(CNPJ_CACHE)} registros")
        except Exception as e:
            if DEBUG:
                print(f"[DEBUG] Falha ao carregar cache CNPJ: {e}")
            CNPJ_CACHE = {}

def salvar_cache_cnpj():
    """Salva cache persistente de CNPJs."""
    try:
        with open(CACHE_CNPJ_FILE, "w", encoding="utf-8") as f:
            json.dump(CNPJ_CACHE, f, ensure_ascii=False, indent=2)
    except Exception as e:
        if DEBUG:
            print(f"[DEBUG] Falha ao salvar cache CNPJ: {e}")

# ==================== CONSULTA COM FALLBACK E CACHE ====================

def consulta_cnpj_api(cnpj: str) -> Optional[str]:
    """
    Consulta nome empresarial do CNPJ usando ReceitaWS e BrasilAPI como fallback.
    Implementa cache persistente e limite de tentativas para evitar loop infinito.
    """
    cnpj_digits = somente_digitos(cnpj)
    if len(cnpj_digits) != 14:
        return None

    # ✅ Verifica cache primeiro
    if cnpj_digits in CNPJ_CACHE:
        if DEBUG:
            print(f"[DEBUG] Cache hit para {cnpj_digits}")
        return CNPJ_CACHE[cnpj_digits]

    tentativas = 0
    nome_empresarial = None

    # === 1️⃣ Primeira tentativa: ReceitaWS ===
    while tentativas < 3:
        tentativas += 1
        url = f"https://www.receitaws.com.br/v1/cnpj/{cnpj_digits}"
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, dict) and data.get("status") == "OK":
                    nome_empresarial = data.get("nome")
                    break
                elif data.get("status") == "ERROR":
                    if DEBUG:
                        print(f"[DEBUG] ReceitaWS erro: {data.get('message')}")
                    break
            elif response.status_code == 429:
                if DEBUG:
                    print(f"[DEBUG] Rate Limit (429) ReceitaWS → tentativa {tentativas}/3")
                time.sleep(10)
                continue
            else:
                if DEBUG:
                    print(f"[DEBUG] HTTP {response.status_code} ReceitaWS → tentativa {tentativas}/3")
                break
        except Exception as e:
            if DEBUG:
                print(f"[DEBUG] Erro ReceitaWS tentativa {tentativas}: {e}")
            time.sleep(2)

    # === 2️⃣ Fallback: BrasilAPI (se ReceitaWS falhou) ===
    if not nome_empresarial:
        try:
            url_brasil = f"https://brasilapi.com.br/api/cnpj/v1/{cnpj_digits}"
            resp = requests.get(url_brasil, timeout=10)
            if resp.status_code == 200:
                data_brasil = resp.json()
                nome_empresarial = data_brasil.get("razao_social") or data_brasil.get("nome_fantasia")
                if DEBUG:
                    print(f"[DEBUG] Fallback BrasilAPI OK → {nome_empresarial}")
            else:
                if DEBUG:
                    print(f"[DEBUG] BrasilAPI retornou {resp.status_code}")
        except Exception as e:
            if DEBUG:
                print(f"[DEBUG] Fallback BrasilAPI falhou: {e}")

    # === 3️⃣ Atualiza cache (mesmo que None, para evitar repetir falhas) ===
    CNPJ_CACHE[cnpj_digits] = nome_empresarial
    salvar_cache_cnpj()

    return nome_empresarial



def detectar_regime_tributario(dest_doc: Optional[str], emitente_doc: Optional[str] = None) -> str:
    """
    Detecta automaticamente o regime tributário (simples ou normal) com base no CNPJ do destinatário.
    Fallback: usa o CNPJ do emitente se o destinatário não estiver disponível.
    Retorna:
      - 'simples' → Optante pelo Simples Nacional
      - 'normal'  → Lucro Real ou Presumido
    """
    def consultar(cnpj: str) -> Optional[str]:
        cnpj_digits = somente_digitos(cnpj)
        if not cnpj_digits or len(cnpj_digits) != 14:
            return None

        # ✅ Verifica cache para evitar consultas repetidas
        if cnpj_digits in CNPJ_CACHE and CNPJ_CACHE[cnpj_digits]:
            return CNPJ_CACHE[cnpj_digits]

        url = f"https://www.receitaws.com.br/v1/cnpj/{cnpj_digits}"
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, dict):
                    optante = data.get("opcao_pelo_simples") or data.get("simples")
                    situacao = data.get("situacao_especial", "")

                    # 🔍 Verifica se é Simples Nacional
                    if isinstance(optante, str) and "sim" in optante.lower():
                        CNPJ_CACHE[cnpj_digits] = "simples"
                        return "simples"
                    if "SIMPLES" in str(situacao).upper():
                        CNPJ_CACHE[cnpj_digits] = "simples"
                        return "simples"

                    # Caso não se enquadre → grava e retorna normal
                    CNPJ_CACHE[cnpj_digits] = "normal"
                    return "normal"

            elif response.status_code == 429 and DEBUG:
                print("[DEBUG] Rate limit na ReceitaWS - fallback 'normal'")
                CNPJ_CACHE[cnpj_digits] = "normal"

        except Exception as e:
            if DEBUG:
                print(f"[DEBUG] Erro ao detectar regime tributário para {cnpj}: {e}")

        return None


    # 1️⃣ Tenta primeiro o destinatário
    regime = consultar(dest_doc) if dest_doc else None

    # 2️⃣ Fallback: tenta o emitente
    if not regime and emitente_doc:
        regime = consultar(emitente_doc)

    # 3️⃣ Se nada encontrado → assume normal
    return regime or "normal"

# ==================== NOVA FUNÇÃO: EXTRAÇÃO DE ITENS ====================

def extrair_itens_da_tabela(pdf_page) -> List[Dict[str, Any]]:
    """
    Extrai itens (produtos/serviços) de DANFE.
    Estratégia híbrida:
      1. Tenta extrair tabela formal com pdfplumber.
      2. Se falhar, usa fallback com coordenadas e regex.
    """
    itens_extraidos: List[Dict[str, Any]] = []

    try:
        # === 1. Tentativa: tabela estruturada ===
        tables = pdf_page.extract_tables({
            "vertical_strategy": "lines",
            "horizontal_strategy": "lines",
            "intersection_tolerance": 5,
            "snap_tolerance": 3,
            "join_tolerance": 3,
            "text_x_tolerance": 2,
            "text_y_tolerance": 2,
            "edge_min_length": 20
        })

        for table in tables:
            if not table or len(table) < 2:
                continue

            header = [str(c).upper().strip() for c in table[0] if c]
            if not any("DESCRI" in h or "PRODUTO" in h for h in header):
                continue

            for row in table[1:]:
                if not any(row):
                    continue
                row = (row + [""] * 12)[:12]

                def num(v):
                    s = str(v).replace(".", "").replace(",", ".").strip()
                    try:
                        return float(s)
                    except:
                        return None

                item = {
                    "codigo": str(row[0]).strip(),
                    "descricao": str(row[1]).strip(),
                    "ncm": str(row[2]).strip(),
                    "cfop": str(row[4]).strip(),
                    "unidade": str(row[5]).strip(),
                    "quantidade": num(row[6]),
                    "valor_unit": num(row[7]),
                    "valor_total": num(row[8]),
                }

                if item["descricao"] and item["valor_total"]:
                    itens_extraidos.append(item)

        # === 2. Fallback: texto posicional (caso sem bordas) ===
        if not itens_extraidos:
            words = pdf_page.extract_words()
            linhas = {}
            for w in words:
                y = round(w["top"] / 5) * 5
                linhas.setdefault(y, []).append(w)

            for _, grupo in sorted(linhas.items()):
                linha_txt = " ".join([w["text"] for w in grupo])
                if len(linha_txt) < 10:
                    continue
                if any(k in linha_txt.upper() for k in ["CÓDIGO", "PRODUTO", "DESCRIÇÃO", "TOTAL", "ICMS", "IPI"]):
                    continue

                m_valor = re.search(r"(\d{1,3}(?:[.,]\d{3})*[.,]\d{2,3})", linha_txt)
                if m_valor:
                    valor_total = moeda_to_float(m_valor.group(1))
                    if valor_total and valor_total > 0:
                        partes = linha_txt.split(m_valor.group(1))
                        descricao = partes[0].strip()
                        codigo = None
                        match_cod = re.match(r"^\d{1,5}", descricao)
                        if match_cod:
                            codigo = match_cod.group(0)
                            descricao = descricao[len(codigo):].strip()

                        if len(descricao) > 4:
                            itens_extraidos.append({
                                "codigo": codigo,
                                "descricao": descricao,
                                "valor_total": round(valor_total, 2)
                            })

        if DEBUG:
            print(f"[DEBUG] Página {pdf_page.page_number}: {len(itens_extraidos)} itens encontrados")

        return itens_extraidos

    except Exception as e:
        if DEBUG:
            print(f"[DEBUG] Erro na extração híbrida de itens: {e}")
        return []

def enriquecer_itens(itens, uf_destino="BA", regime="simples"):
    """Usa a biblioteca de códigos fiscais para enriquecer os dados dos itens"""
    itens_enriquecidos = []
    for item in itens:
        cfop = str(item.get("cfop", "")).strip()
        ncm = str(item.get("ncm", "")).strip()
        csosn = str(item.get("csosn", item.get("ocst", ""))).strip()

        if cfop or ncm:
            analise = analisar_nf(cfop, ncm, csosn, uf_destino, regime)
            item.update({
                "cfop_desc": analise.get("cfop_info", {}).get("descricao"),
                "ncm_desc": analise.get("ncm_info", {}).get("descricao"),
                "icms_aplica": analise.get("cfop_info", {}).get("icms_aplica"),
                "ipi_aplica": analise.get("cfop_info", {}).get("ipi_aplica"),
                "aliquota_icms": analise.get("aliquota_icms"),
                "aliquota_ipi": analise.get("aliquota_ipi"),
                "aliquota_pis": analise.get("aliquota_pis"),
                "aliquota_cofins": analise.get("aliquota_cofins"),
            })
        itens_enriquecidos.append(item)
    return itens_enriquecidos

# ==================== FUNÇÕES DE EXTRAÇÃO (ADAPTADAS) ====================

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
    if emitente_doc is None:
        cnpjs = re.findall(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b", texto)
        if cnpjs:
            emitente_doc = cnpjs[0]
            if emitente_doc is not None:
                idx = texto.find(emitente_doc)
                if idx != -1:
                    trecho_antes = texto[max(0, idx-150):idx].strip()
                    linhas_antes = trecho_antes.split("\n")
                    for linha in reversed(linhas_antes):
                        linha_limpa = linha.strip()
                        if linha_limpa and not any(k in linha_limpa.upper() for k in ["CNPJ", "CPF", "ENDEREÇO", "RAZÃO", "NOTA", "EMITENTE"]):
                            alpha_count = sum(c.isalpha() for c in linha_limpa)
                            if alpha_count >= max(3, len(linha_limpa) // 2):
                                emitente_nome = linha_limpa
                                break

    # Sempre atualiza emitente_nome pelo nome oficial da API (se emitente_doc presente)
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
    # ... (Seu código existente para OCR, mantido)
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

# FUNÇÃO PRINCIPAL ADAPTADA para retornar ITENS

def extrair_capa_de_pdf(arquivo_pdf: str, progress_callback=None) -> dict:
    nome_arquivo = Path(arquivo_pdf).name
    itens: List[Dict[str, Any]] = []
    dados = {}

    try:
        with pdfplumber.open(arquivo_pdf) as pdf:
            capa_encontrada = False

            for page in pdf.pages:
                # === 1️⃣ Extrai itens estruturados da página ===
                try:
                    pagina_itens = extrair_itens_da_tabela(page)
                    if pagina_itens:
                        itens.extend(pagina_itens)
                except Exception as e:
                    if DEBUG:
                        print(f"[DEBUG] Falha ao extrair itens da Pág {page.page_number} de {nome_arquivo}: {e}")

                # === 2️⃣ Extrai capa (geralmente na primeira página) ===
                if not capa_encontrada:
                    txt = page.extract_text() or ""
                    if txt and len(txt.strip()) > 100:
                        dados_capa = extrair_capa_de_texto(txt) or {}
                        if isinstance(dados_capa, dict) and dados_capa.get("numero_nf"):
                                dados = dados_capa
                                capa_encontrada = True



            # === 3️⃣ Detecta automaticamente os regimes tributários ===
            regime_dest = detectar_regime_tributario(dest_doc=dados.get("dest_doc"), emitente_doc=None)
            regime_emit = detectar_regime_tributario(dest_doc=dados.get("emitente_doc"), emitente_doc=None)

            # === 4️⃣ Define o regime final conforme combinação ===
            if regime_dest == "normal" and regime_emit == "simples":
                regime_final = "normal"
            elif regime_dest == "simples" and regime_emit == "normal":
                regime_final = "misto"
            else:
                regime_final = regime_dest or regime_emit or "normal"

            dados["regime_emit"] = regime_emit
            dados["regime_dest"] = regime_dest
            dados["regime_final"] = regime_final

            if DEBUG:
                print(f"[DEBUG] Regimes detectados → Emitente: {regime_emit}, Destinatário: {regime_dest}, Final: {regime_final}")

            # === 5️⃣ Enriquecimento fiscal por item ===
            if itens:
                itens = enriquecer_itens(itens, uf_destino="BA", regime=regime_final)

            # === 6️⃣ Análise fiscal detalhada (destinatário) ===
            try:
                if itens:
                    analise = analisar_nf_como_destinatario(
                        cfop=str(itens[0].get("cfop", "")),
                        ncm=str(itens[0].get("ncm", "")),
                        csosn_ou_cst_recebido=str(itens[0].get("csosn", itens[0].get("ocst", ""))),
                        regime_destinatario=regime_dest or "lucro_real",
                        regime_emitente=regime_emit or "normal",
                        uf_origem="BA",
                        valor_total=dados.get("valor_total_num", 0.0),
                        valor_icms=None,
                        valor_pis=None,
                        valor_cofins=None,
                    )
                    dados["analise_destinatario"] = analise
                    dados["resumo_analise"] = gerar_resumo_analise(analise)
            except Exception as e:
                if DEBUG:
                    print(f"[DEBUG] Erro ao analisar NF como destinatário: {e}")

            # === 7️⃣ Retorna resultado consolidado ===
            if capa_encontrada or itens:
                if progress_callback:
                    status = "✅" if capa_encontrada else "⚠️"
                    progress_callback(f"{status} pdfplumber: {nome_arquivo} ({len(itens)} itens encontrados)")
                return {"arquivo": nome_arquivo, **dados, "itens_nf": itens}

    except Exception as e:
        if DEBUG:
            print(f"[DEBUG] Erro catastrófico em pdfplumber para {nome_arquivo}: {e}")

    # === 8️⃣ Fallback OCR ===
    try:
        if progress_callback:
            progress_callback(f"🔄 OCR: {nome_arquivo}")
        texto_ocr = extrair_texto_ocr(arquivo_pdf, progress_callback)
        if texto_ocr and len(texto_ocr.strip()) > 100:
            dados = extrair_capa_de_texto(texto_ocr)
            if any([dados.get("numero_nf"), dados.get("emitente_doc"), dados.get("valor_total")]):
                if progress_callback:
                    progress_callback(f"✅ OCR: {nome_arquivo}")
                return {"arquivo": nome_arquivo, **dados, "itens_nf": []}
    except Exception as e:
        if progress_callback:
            progress_callback(f"❌ Erro OCR/Extração: {e}")

    vazio = {k: None for k in [
        "numero_nf","serie","emitente_doc","emitente_nome",
        "dest_doc","dest_nome","data_emissao","valor_total","valor_total_num"
    ]}
    return {"arquivo": nome_arquivo, **vazio, "itens_nf": []}


# =============== FUNÇÕES DE PROCESSAMENTO (ADAPTADAS) ===============

@st.cache_data(show_spinner=False, ttl=86400)
def processar_pdfs(arquivos_pdf: list, _progress_callback=None) -> pd.DataFrame:
    """
    Processa múltiplos PDFs com cache híbrido:
      - Streamlit cache (24h)
      - Disco cache (permanente)
      - Memória (em execução)
    """
    carregar_cache_cnpj()

    regs = []

    for i, pdf_path in enumerate(arquivos_pdf, 1):
        nome = Path(pdf_path).name
        if _progress_callback:
            _progress_callback(f"[{i}/{len(arquivos_pdf)}] {nome}")

        # === 1️⃣ Gera hash e tenta carregar cache ===
        hash_pdf = get_pdf_hash(pdf_path)
        cached = carregar_cache_nf(hash_pdf)
        if cached:
            if _progress_callback:
                _progress_callback(f"⚡ Loaded from cache: {nome}")
            regs.append(cached)
            continue

        # === 2️⃣ Se não houver cache, processa normalmente ===
        try:
            data = extrair_capa_de_pdf(pdf_path, _progress_callback)
            regs.append(data)
            salvar_cache_nf(hash_pdf, data)
        except Exception as e:
            if DEBUG:
                print(f"[DEBUG] Falha ao processar {nome}: {e}")

    # === 3️⃣ Gera DataFrame consolidado ===
    df = pd.DataFrame(regs).drop_duplicates(subset=["arquivo"], keep="first")

    # === 4️⃣ Limpeza e padronização ===
    for col in ["emitente_nome", "dest_nome"]:
        if col in df.columns:
            df[col] = df[col].fillna('').astype(str)

    if "valor_total_num" in df.columns:
        df["valor_total_num"] = pd.to_numeric(df["valor_total_num"], errors="coerce")

    if "data_emissao" in df.columns:
        df["_ordem"] = pd.to_datetime(df["data_emissao"], format="%d/%m/%Y", errors="coerce")
        df = df.sort_values(by=["_ordem", "numero_nf"], ascending=[True, True])
        df = df.drop(columns=["_ordem"])

    salvar_cache_cnpj()

    return df




def exportar_para_excel(df: pd.DataFrame) -> bytes:
    # Remove a coluna 'itens_nf' para exportação, pois contém listas de dicts
    df_export = df.drop(columns=['itens_nf'], errors='ignore')
    output = io.BytesIO()
    df_export.to_excel(output, index=False, engine='openpyxl')
    output.seek(0)
    return output.getvalue()

def exportar_para_excel_com_itens(df: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        # Aba principal
        df.drop(columns=["itens_nf"], errors="ignore").to_excel(writer, sheet_name="Notas Fiscais", index=False)

        # Aba de itens
        todas_linhas = []
        for _, row in df.iterrows():
            if isinstance(row.get("itens_nf"), list):
                for item in row["itens_nf"]:
                    todas_linhas.append({
                        "arquivo": row["arquivo"],
                        "numero_nf": row.get("numero_nf"),
                        "emitente_nome": row.get("emitente_nome"),
                        "data_emissao": row.get("data_emissao"),
                        "valor_nf": row.get("valor_total_num"),
                        "regime_emit": row.get("regime_emit"),
                        "regime_dest": row.get("regime_dest"),
                        "regime_final": row.get("regime_final"),
                        **item
                    })
        if todas_linhas:
            pd.DataFrame(todas_linhas).to_excel(writer, sheet_name="Itens Detalhados", index=False)

        # Aba de análises fiscais
        analises = []
        for _, row in df.iterrows():
            analise = row.get("analise_destinatario")
            if isinstance(analise, dict):
                analises.append({
                    "arquivo": row["arquivo"],
                    "numero_nf": row.get("numero_nf"),
                    "emitente_nome": row.get("emitente_nome"),
                    "dest_nome": row.get("dest_nome"),
                    "regime_emit": row.get("regime_emit"),
                    "regime_dest": row.get("regime_dest"),
                    "conformidade": analise.get("conformidade"),
                    "credito_icms": analise["credito_icms"]["valor"] if analise.get("credito_icms") else None,
                    "credito_pis": analise["credito_pis"]["valor"] if analise.get("credito_pis") else None,
                    "credito_cofins": analise["credito_cofins"]["valor"] if analise.get("credito_cofins") else None,
                    "resumo_analise": row.get("resumo_analise"),
                })
        if analises:
            pd.DataFrame(analises).to_excel(writer, sheet_name="Análise Fiscal", index=False)

    output.seek(0)
    return output.getvalue()
