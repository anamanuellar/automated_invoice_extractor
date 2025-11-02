"""
Enriquecedor de Dados Fiscais via API
Consulta: IE Status, Regime Tributário, Optante Simples Nacional
"""

import requests
import json
import time
import re
from typing import Optional, Dict, Any
from datetime import datetime
import pandas as pd
import numpy as np

# ===================== CACHE =====================
CACHE_FILE = "cache_fiscal_enriquecimento.json"
try:
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        CACHE_FISCAL = json.load(f)
except:
    CACHE_FISCAL = {}

def salvar_cache():
    """Salva cache em arquivo"""
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(CACHE_FISCAL, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Erro ao salvar cache: {e}")

# ===================== CONSULTAS CNPJ =====================

def consultar_cnpj_receitaws(cnpj: str) -> Optional[Dict[str, Any]]:
    """
    Consulta dados do CNPJ via ReceitaWS
    Retorna: IE status, regime tributário, optante simples, etc
    """
    cnpj_digits = re.sub(r"\D", "", cnpj)
    if len(cnpj_digits) != 14:
        return None
    
    # Verifica cache
    if cnpj_digits in CACHE_FISCAL:
        cache_data = CACHE_FISCAL[cnpj_digits]
        if cache_data.get("tipo") == "cnpj":
            return cache_data
    
    try:
        url = f"https://www.receitaws.com.br/v1/cnpj/{cnpj_digits}"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict) and data.get("status") == "OK":
                resultado = {
                    "tipo": "cnpj",
                    "cnpj": cnpj_digits,
                    "nome": data.get("nome"),
                    "ie_status": data.get("situacao", "Ativa").lower(),
                    "ie_ativa": "ativa" in data.get("situacao", "").lower(),
                    "ie_isenta": "isenta" in data.get("situacao", "").lower(),
                    "optante_simples": "sim" in str(data.get("opcao_pelo_simples", "")).lower(),
                    "regime_tributario": _detectar_regime(data),
                    "data_consulta": datetime.now().isoformat(),
                    "fonte": "ReceitaWS"
                }
                CACHE_FISCAL[cnpj_digits] = resultado
                salvar_cache()
                return resultado
    except Exception as e:
        print(f"⚠️ ReceitaWS erro ({cnpj_digits}): {e}")
    
    return None

def consultar_cnpj_brasilapi(cnpj: str) -> Optional[Dict[str, Any]]:
    """
    Fallback: Consulta via BrasilAPI
    """
    cnpj_digits = re.sub(r"\D", "", cnpj)
    if len(cnpj_digits) != 14:
        return None
    
    try:
        url = f"https://brasilapi.com.br/api/cnpj/v1/{cnpj_digits}"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            resultado = {
                "tipo": "cnpj",
                "cnpj": cnpj_digits,
                "nome": data.get("razao_social") or data.get("nome_fantasia"),
                "ie_status": data.get("inscricao_estadual_ativa"),
                "ie_ativa": data.get("inscricao_estadual_ativa") == True,
                "ie_isenta": False,  # BrasilAPI não fornece esse detalhe
                "optante_simples": False,  # BrasilAPI não fornece esse detalhe
                "regime_tributario": "desconhecido",
                "data_consulta": datetime.now().isoformat(),
                "fonte": "BrasilAPI"
            }
            CACHE_FISCAL[cnpj_digits] = resultado
            salvar_cache()
            return resultado
    except Exception as e:
        print(f"⚠️ BrasilAPI erro ({cnpj_digits}): {e}")
    
    return None

def enriquecer_cnpj(cnpj: str) -> Dict[str, Any]:
    """
    Enriquece dados de CNPJ com informações fiscais
    Tenta ReceitaWS primeiro, depois BrasilAPI
    """
    # Tenta ReceitaWS
    resultado = consultar_cnpj_receitaws(cnpj)
    if resultado:
        return resultado
    
    # Fallback BrasilAPI
    resultado = consultar_cnpj_brasilapi(cnpj)
    if resultado:
        return resultado
    
    # Se falhar, retorna estrutura vazia
    return {
        "tipo": "cnpj",
        "cnpj": re.sub(r"\D", "", cnpj),
        "erro": "Não foi possível consultar",
        "ie_ativa": None,
        "ie_isenta": None,
        "optante_simples": None,
        "regime_tributario": None,
    }

# ===================== CONSULTAS CPF =====================

def consultar_cpf_brasilapi(cpf: str) -> Optional[Dict[str, Any]]:
    """
    Consulta dados do CPF via BrasilAPI (nome básico)
    Nota: API limitada por questões de privacidade
    """
    cpf_digits = re.sub(r"\D", "", cpf)
    if len(cpf_digits) != 11:
        return None
    
    # Verifica cache
    if cpf_digits in CACHE_FISCAL:
        cache_data = CACHE_FISCAL[cpf_digits]
        if cache_data.get("tipo") == "cpf":
            return cache_data
    
    try:
        # BrasilAPI tem limite severo de privacidade para CPF
        # Apenas retorna dados públicos muito limitados
        url = f"https://brasilapi.com.br/api/cpf/v1/{cpf_digits}"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            resultado = {
                "tipo": "cpf",
                "cpf": cpf_digits,
                "valido": data.get("is_valid"),
                "data_consulta": datetime.now().isoformat(),
                "fonte": "BrasilAPI"
            }
            CACHE_FISCAL[cpf_digits] = resultado
            salvar_cache()
            return resultado
    except Exception as e:
        print(f"⚠️ BrasilAPI CPF erro ({cpf_digits}): {e}")
    
    return None

def consultar_regime_tributario_cpf_simplesnacional(cpf: str) -> Optional[Dict[str, Any]]:
    """
    Verifica se CPF está registrado como Simples Nacional
    Usa integração com dados do Simples Nacional (limitado)
    """
    cpf_digits = re.sub(r"\D", "", cpf)
    if len(cpf_digits) != 11:
        return None
    
    try:
        # Tenta ReceitaWS para dados básicos
        url = f"https://www.receitaws.com.br/v1/cpf/{cpf_digits}"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict) and data.get("status") == "OK":
                resultado = {
                    "tipo": "cpf",
                    "cpf": cpf_digits,
                    "nome": data.get("nome"),
                    "regime_tributario": _detectar_regime_cpf(data),
                    "data_consulta": datetime.now().isoformat(),
                    "fonte": "ReceitaWS"
                }
                CACHE_FISCAL[cpf_digits] = resultado
                salvar_cache()
                return resultado
    except Exception as e:
        print(f"⚠️ ReceitaWS CPF erro ({cpf_digits}): {e}")
    
    return None

# ===================== DETECÇÃO DE REGIME =====================

def _detectar_regime(data_cnpj: dict) -> str:
    """
    Detecta regime tributário a partir dos dados do CNPJ
    """
    # Verifica Simples Nacional
    opcao_simples = str(data_cnpj.get("opcao_pelo_simples", "")).lower()
    if "sim" in opcao_simples:
        return "Simples Nacional"
    
    # Verifica situação especial
    sit_especial = str(data_cnpj.get("situacao_especial", "")).upper()
    if "SIMPLES" in sit_especial:
        return "Simples Nacional"
    
    # Verifica se é isento
    situacao = str(data_cnpj.get("situacao", "")).lower()
    if "isent" in situacao:
        return "Isento de IE"
    
    # Padrão: Lucro Real ou Presumido (não se sabe sem mais dados)
    return "Lucro Real/Presumido"

def _detectar_regime_cpf(data_cpf: dict) -> str:
    """
    Detecta regime tributário para CPF
    Nota: Dados limitados para CPF
    """
    # CPF tem menos informações fiscais que CNPJ
    # Retorna regime genérico
    return "Pessoa Física (regime desconhecido via API)"

# ===================== ENRIQUECIMENTO EM LOTE =====================

def enriquecer_dataframe_fiscal(df, coluna_cnpj="emitente_doc", coluna_cpf=None):
    """
    Enriquece DataFrame com dados fiscais de CNPJ/CPF
    
    Args:
        df: DataFrame pandas
        coluna_cnpj: Nome da coluna com CNPJ do emitente
        coluna_cpf: Nome da coluna com CPF (opcional)
    
    Returns:
        DataFrame enriquecido com colunas novas:
        - ie_ativa
        - ie_isenta
        - optante_simples
        - regime_tributario_emitente
    """
    import pandas as pd
    
    df_novo = df.copy()
    
    # Enriquecimento CNPJ
    print("\n📊 Enriquecendo dados de CNPJ...")
    df_novo["ie_ativa"] = None
    df_novo["ie_isenta"] = None
    df_novo["optante_simples"] = None
    df_novo["regime_tributario_emitente"] = None
    
    for idx, row in df_novo.iterrows():
        cnpj = row.get(coluna_cnpj)
        if cnpj and str(cnpj).strip():
            print(f"  [{idx+1}/{len(df_novo)}] {cnpj}...", end=" ", flush=True)
            
            dados = enriquecer_cnpj(cnpj)
            df_novo.at[idx, "ie_ativa"] = dados.get("ie_ativa")
            df_novo.at[idx, "ie_isenta"] = dados.get("ie_isenta")
            df_novo.at[idx, "optante_simples"] = dados.get("optante_simples")
            df_novo.at[idx, "regime_tributario_emitente"] = dados.get("regime_tributario")
            
            print(f"✅ {dados.get('regime_tributario')}")
            time.sleep(1)  # Rate limiting
    
    # Enriquecimento CPF (opcional)
    if coluna_cpf and coluna_cpf in df.columns:
        print("\n📊 Enriquecendo dados de CPF...")
        df_novo["regime_tributario_cpf"] = None
        
        for idx, row in df_novo.iterrows():
            cpf = row.get(coluna_cpf)
            if cpf and str(cpf).strip():
                print(f"  [{idx+1}/{len(df_novo)}] {cpf}...", end=" ", flush=True)
                
                dados = consultar_regime_tributario_cpf_simplesnacional(cpf)
                if dados:
                    df_novo.at[idx, "regime_tributario_cpf"] = dados.get("regime_tributario")
                    print(f"✅ {dados.get('regime_tributario')}")
                else:
                    print("⚠️ Sem dados")
                
                time.sleep(1)  # Rate limiting
    
    salvar_cache()
    return df_novo

# ===================== RELATÓRIO =====================

def gerar_relatorio_fiscal(df):
    """
    Gera relatório com análise de regimes tributários
    """
    print("\n" + "="*80)
    print("RELATÓRIO FISCAL - ENRIQUECIMENTO VIA API")
    print("="*80)
    
    if "regime_tributario_emitente" in df.columns:
        print("\n📊 REGIMES TRIBUTÁRIOS IDENTIFICADOS:")
        regimes = df["regime_tributario_emitente"].value_counts()
        for regime, count in regimes.items():
            print(f"  • {regime}: {count}")
    
    if "optante_simples" in df.columns:
        simples_count = df["optante_simples"].sum() if df["optante_simples"].dtype == bool else 0
        print(f"\n📊 SIMPLES NACIONAL:")
        print(f"  • Optantes: {simples_count}")
        print(f"  • Não optantes: {len(df) - simples_count}")
    
    if "ie_isenta" in df.columns:
        isenta_count = df["ie_isenta"].sum() if df["ie_isenta"].dtype == bool else 0
        print(f"\n📊 INSCRIÇÃO ESTADUAL ISENTA:")
        print(f"  • Inscritas como isentas: {isenta_count}")
        print(f"  • Com IE ativa: {df['ie_ativa'].sum() if 'ie_ativa' in df.columns else '?'}")
    
    print("\n" + "="*80)

# ===================== VALIDAÇÕES =====================

def validar_nfs_com_ia_enriquecida(df: 'pd.DataFrame') -> Dict[str, Any]:
    """
    Usa dados enriquecidos para validações e alertas fiscais
    
    Retorna dict com alertas por categoria:
    - ie_inativa: NFs com IE do emitente inativa
    - ie_isenta_mas_icms: NFs com IE isenta mas ICMS pode ter sido cobrado
    - simples_nacional_com_problemas: NFs com Simples Nacional para verificação
    """
    alertas = {
        "ie_inativa": [],
        "ie_isenta_mas_icms": [],
        "simples_nacional_com_problemas": []
    }
    
    for idx, row in df.iterrows():
        nf = row.get("numero_nf")
        emitente = row.get("emitente_nome")
        
        # Alerta 1: IE não ativa
        if row.get("ie_ativa") == False:
            alertas["ie_inativa"].append({
                "nf": nf,
                "emitente": emitente,
                "motivo": "Fornecedor com IE inativa"
            })
        
        # Alerta 2: IE isenta mas com valor (possível ICMS cobrado)
        if row.get("ie_isenta") == True and row.get("valor_total_num", 0) > 0:
            alertas["ie_isenta_mas_icms"].append({
                "nf": nf,
                "emitente": emitente,
                "motivo": "Verificar se CFOP está correto para IE isenta (5.949)"
            })
        
        # Alerta 3: Simples Nacional
        if row.get("optante_simples") == True:
            alertas["simples_nacional_com_problemas"].append({
                "nf": nf,
                "emitente": emitente,
                "motivo": "Validar se PIS/COFINS estão zerados (esperado para Simples)"
            })
    
    return alertas

if __name__ == "__main__":
    # Teste
    print("🔍 Teste de Enriquecimento Fiscal")
    print("="*80)
    
    # Teste CNPJ
    cnpj_teste = "06.990.590/0001-23"  # Exemplo
    print(f"\n📝 Consultando CNPJ: {cnpj_teste}")
    resultado = enriquecer_cnpj(cnpj_teste)
    print(json.dumps(resultado, indent=2, ensure_ascii=False))
    
    print("\n✅ Cache salvo em:", CACHE_FILE)