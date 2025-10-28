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
def consulta_cnpj_api(cnpj: str) -> Optional[str]:
    cnpj_digits = somente_digitos(cnpj)
    if cnpj_digits in CNPJ_CACHE:
        return CNPJ_CACHE[cnpj_digits]
    
    time.sleep(0.5) 

    url = f"https://www.receitaws.com.br/v1/cnpj/{cnpj_digits}"
    try:
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict) and data.get("status") == "OK":
                nome_empresarial = data.get("nome")
                CNPJ_CACHE[cnpj_digits] = nome_empresarial
                return nome_empresarial
            elif isinstance(data, dict) and data.get("status") == "ERROR":
                if DEBUG:
                    print(f"[DEBUG] Erro da API na consulta do CNPJ {cnpj}: {data.get('message')}")
                return None
        elif response.status_code == 429: # Rate limit
            if DEBUG:
                print(f"[DEBUG] Rate Limit (429) para o CNPJ {cnpj}. Tentando novamente em 5 segundos.")
            time.sleep(5)
            return consulta_cnpj_api(cnpj)
        
        if DEBUG:
            print(f"[DEBUG] Erro HTTP {response.status_code} na consulta do CNPJ {cnpj}")
        
    except requests.exceptions.Timeout:
        if DEBUG:
            print(f"[DEBUG] Timeout na consulta do CNPJ {cnpj}")
    except requests.exceptions.RequestException as e:
        if DEBUG:
            print(f"[DEBUG] Erro de requisição na consulta do CNPJ {cnpj}: {e}")
    except Exception as e:
        if DEBUG:
            print(f"[DEBUG] Erro inesperado na consulta do CNPJ {cnpj}: {e}")
            
    CNPJ_CACHE[cnpj_digits] = None
    return None

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
                        dados_capa = extrair_capa_de_texto(txt)
                        if dados_capa.get("numero_nf"):
                            dados = dados_capa
                            capa_encontrada = True

            # === Detecta regime tributário automaticamente ===
            regime_tributario = detectar_regime_tributario(
                dest_doc=dados.get("dest_doc"),
                emitente_doc=dados.get("emitente_doc")
            )


            # === 3️⃣ Enriquecimento fiscal automático (usa codigos_fiscais.py) ===
            if itens:
                itens = enriquecer_itens(itens, uf_destino="BA", regime=regime_tributario)
                dados["regime_tributario"] = regime_tributario


            # === 4️⃣ Retorna resultado consolidado ===
            if capa_encontrada or itens:
                if progress_callback:
                    status = "✅" if capa_encontrada else "⚠️"
                    progress_callback(f"{status} pdfplumber: {nome_arquivo} ({len(itens)} itens encontrados)")
                return {"arquivo": nome_arquivo, **dados, "itens_nf": itens}

    except Exception as e:
        if DEBUG:
            print(f"[DEBUG] Erro catastrófico em pdfplumber para {nome_arquivo}: {e}")
        pass  # Fallback para OCR

    # === 5️⃣ Fallback: OCR para PDFs escaneados (sem itens) ===
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

    # === 6️⃣ Retorno vazio padrão ===
    vazio = {k: None for k in [
        "numero_nf", "serie", "emitente_doc", "emitente_nome",
        "dest_doc", "dest_nome", "data_emissao", "valor_total", "valor_total_num"
    ]}
    return {"arquivo": nome_arquivo, **vazio, "itens_nf": []}


# =============== FUNÇÕES DE PROCESSAMENTO (ADAPTADAS) ===============

def processar_pdfs(arquivos_pdf: list, progress_callback=None) -> pd.DataFrame:
    regs = []
    for i, pdf_path in enumerate(arquivos_pdf, 1):
        if progress_callback:
            progress_callback(f"[{i}/{len(arquivos_pdf)}] {Path(pdf_path).name}")
        regs.append(extrair_capa_de_pdf(pdf_path, progress_callback))
    
    df = pd.DataFrame(regs).drop_duplicates(subset=["arquivo"], keep="first")
    
    # =================================================================
    # CORREÇÃO CRÍTICA: Limpeza e Conversão de Tipos
    # Garante que as colunas essenciais para o Pandas e IA estão corretas
    # =================================================================
    
    # 1. Colunas de nome/texto: força string para evitar o erro .str
    for col in ["emitente_nome", "dest_nome"]:
        if col in df.columns:
            # Preenche NaNs com string vazia e depois converte tudo para string
            df[col] = df[col].fillna('').astype(str)
            
    # 2. Colunas numéricas: força float
    if "valor_total_num" in df.columns:
        df["valor_total_num"] = pd.to_numeric(df["valor_total_num"], errors="coerce")
        
    # 3. Colunas de data
    if "data_emissao" in df.columns:
        # Tenta a conversão de data (necessário para ordenar)
        df["_ordem"] = pd.to_datetime(df["data_emissao"], format="%d/%m/%Y", errors="coerce")
        df = df.sort_values(by=["_ordem", "numero_nf"], ascending=[True, True])
        df = df.drop(columns=["_ordem"])
        
    # =================================================================
    
    return df




def exportar_para_excel(df: pd.DataFrame) -> bytes:
    # Remove a coluna 'itens_nf' para exportação, pois contém listas de dicts
    df_export = df.drop(columns=['itens_nf'], errors='ignore')
    output = io.BytesIO()
    df_export.to_excel(output, index=False, engine='openpyxl')
    output.seek(0)
    return output.getvalue()

def exportar_para_excel_com_itens(df: pd.DataFrame) -> bytes:
    """
    Exporta as notas e os itens detalhados em abas separadas.
    """
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        # Aba principal
        df.drop(columns=["itens_nf"], errors="ignore").to_excel(writer, sheet_name="Notas Fiscais", index=False)

        # Aba de itens detalhados
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
                        **item
                    })
        if todas_linhas:
            pd.DataFrame(todas_linhas).to_excel(writer, sheet_name="Itens Detalhados", index=False)

    output.seek(0)
    return output.getvalue()
