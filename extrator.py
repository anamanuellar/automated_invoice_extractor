from typing import Any, Optional, List, Dict
import os, io, re, requests, time
from pathlib import Path
from datetime import datetime
import numpy as np
import pdfplumber
import pandas as pd
from PIL import Image, ImageEnhance, ImageOps
import fitz # PyMuPDF

# =============== CONFIG (MANTIDO) ===============
DEBUG = False
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

# ==================== NOVA FUNÇÃO: EXTRAÇÃO DE ITENS ====================

def extrair_itens_da_tabela(pdf_page: Any) -> List[Dict[str, Any]]:
    """
    Tenta extrair a tabela de itens (produtos/serviços) da página.
    """
    
    # Configuração de detecção de tabelas para NFe padrão
    # Muitas NFs têm 6 a 9 colunas para (Código, Descrição, Qtd, Unidade, Valor Unitário, Valor Total, etc.)
    table_settings = {
        "vertical_strategy": "lines",
        "horizontal_strategy": "lines",
        "snap_y_tolerance": 5, # Permite um pequeno desvio vertical
    }

    try:
        # Extrai todas as tabelas da página
        tables = pdf_page.extract_tables(table_settings)
        
        itens_extraidos: List[Dict[str, Any]] = []
        
        for table in tables:
            if not table or len(table) < 2:
                continue

            # Tentativa de identificar o cabeçalho (pode variar muito)
            header_row = [str(c).upper().strip() for c in table[0] if c is not None]
            
            # Condição básica: precisa ter 'DESCRIÇÃO' e algum tipo de 'VALOR'
            has_descricao = any('DESCRICAO' in h or 'PRODUTO' in h or 'SERVICO' in h for h in header_row)
            has_valor = any('VALOR' in h or 'TOTAL' in h for h in header_row)

            if has_descricao and has_valor:
                # Mapear as colunas de interesse
                mapa_colunas = {}
                for i, col_name in enumerate(header_row):
                    if 'DESCRICAO' in col_name or 'PRODUTO' in col_name or 'SERVICO' in col_name:
                        mapa_colunas['descricao'] = i
                    elif 'VALOR' in col_name and not any(k in col_name for k in ['ICMS', 'IPI']):
                        mapa_colunas['valor_total'] = i
                    elif 'QUANT' in col_name or 'QTDE' in col_name:
                        mapa_colunas['quantidade'] = i

                if 'descricao' in mapa_colunas and 'valor_total' in mapa_colunas:
                    for row_idx, row in enumerate(table):
                        if row_idx == 0: continue # Ignorar cabeçalho

                        descricao_raw = row[mapa_colunas['descricao']] if mapa_colunas['descricao'] < len(row) and row[mapa_colunas['descricao']] else None
                        valor_raw = row[mapa_colunas['valor_total']] if mapa_colunas['valor_total'] < len(row) and row[mapa_colunas['valor_total']] else None
                        
                        descricao_str = str(descricao_raw).strip() if descricao_raw else ""
                        valor_str = str(valor_raw).strip() if valor_raw else ""

                        # Validação básica
                        if len(descricao_str) > 5 and moeda_to_float(valor_str) is not None:
                            itens_extraidos.append({
                                'descricao_item': descricao_str,
                                'valor_item': moeda_to_float(valor_str)
                            })

        return itens_extraidos

    except Exception as e:
        if DEBUG:
            print(f"[DEBUG] Erro na extração de itens da tabela: {e}")
        return []

# ==================== FUNÇÕES DE EXTRAÇÃO (ADAPTADAS) ====================

def extrair_capa_de_texto(texto: str) -> dict:
    # ... (Seu código existente para extrair capa: numero_nf, emitente_doc, etc.)
    # Apenas para manter o código enxuto, assumimos que esta função não muda
    
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
    
    # 1. Tentativa com pdfplumber (melhor para tabelas)
    try:
        with pdfplumber.open(arquivo_pdf) as pdf:
            # Assumimos que a capa e itens estão na primeira página
            if pdf.pages:
                page = pdf.pages[0]
                
                # Extrai itens da tabela (Novo!)
                itens = extrair_itens_da_tabela(page)
                
                # Extrai texto da capa
                txt = page.extract_text() or ""
                if txt and len(txt.strip()) > 100:
                    dados = extrair_capa_de_texto(txt)
                
                if any([dados.get("numero_nf"), dados.get("emitente_doc"), dados.get("valor_total")]):
                    if progress_callback:
                        progress_callback(f"✅ pdfplumber: {nome_arquivo}")
                    # Inclui itens no resultado
                    return {"arquivo": nome_arquivo, **dados, "itens_nf": itens}
    except Exception as e:
        if DEBUG:
            print(f"[DEBUG] Erro em pdfplumber para {nome_arquivo}: {e}")
        pass # Tenta OCR se pdfplumber falhar

    # 2. Tentativa com OCR (não extrai tabelas bem, mas extrai a capa)
    try:
        if progress_callback:
            progress_callback(f"🔄 OCR: {nome_arquivo}")
        texto_ocr = extrair_texto_ocr(arquivo_pdf, progress_callback)
        if texto_ocr and len(texto_ocr.strip()) > 100:
            dados = extrair_capa_de_texto(texto_ocr)
            if any([dados.get("numero_nf"), dados.get("emitente_doc"), dados.get("valor_total")]):
                if progress_callback:
                    progress_callback(f"✅ OCR: {nome_arquivo}")
                # OCR não extrai itens estruturados, então retorna lista vazia
                return {"arquivo": nome_arquivo, **dados, "itens_nf": []}
    except Exception as e:
        if progress_callback:
            progress_callback(f"❌ {e}")

    # 3. Retorno vazio
    vazio = {k: None for k in [
        "numero_nf","serie","emitente_doc","emitente_nome",
        "dest_doc","dest_nome","data_emissao","valor_total","valor_total_num"
    ]}
    # Sempre inclui a chave 'itens_nf'
    return {"arquivo": nome_arquivo, **vazio, "itens_nf": []}


# =============== FUNÇÕES DE PROCESSAMENTO (ADAPTADAS) ===============

def processar_pdfs(arquivos_pdf: list, progress_callback=None) -> pd.DataFrame:
    regs = []
    for i, pdf_path in enumerate(arquivos_pdf, 1):
        if progress_callback:
            progress_callback(f"[{i}/{len(arquivos_pdf)}] {Path(pdf_path).name}")
        regs.append(extrair_capa_de_pdf(pdf_path, progress_callback))
    
    # Criamos um DataFrame temporário para os dados da capa, e mantemos a lista de itens
    df_base = pd.DataFrame(regs)
    
    # Normalizamos o DataFrame (drop_duplicates, sorting, etc.)
    df_processado = df_base.drop_duplicates(subset=["arquivo"], keep="first")
    try:
        df_processado["_ordem"] = pd.to_datetime(df_processado["data_emissao"], format="%d/%m/%Y", errors="coerce")
        df_processado = df_processado.sort_values(by=["_ordem","arquivo"], na_position="last").drop(columns=["_ordem"])
    except:
        pass
        
    # Retornamos o DataFrame com a nova coluna 'itens_nf' (uma lista de dicts)
    return df_processado


def exportar_para_excel(df: pd.DataFrame) -> bytes:
    # Remove a coluna 'itens_nf' para exportação, pois contém listas de dicts
    df_export = df.drop(columns=['itens_nf'], errors='ignore')
    output = io.BytesIO()
    df_export.to_excel(output, index=False, engine='openpyxl')
    output.seek(0)
    return output.getvalue()