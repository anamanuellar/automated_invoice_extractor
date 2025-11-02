"""
Análise Executiva - Fiscal + Financeira com DETALHAMENTO DE IMPACTO CFOP
- Regime do destinatário (seleção do usuário)
- Extração automática de regime por CNPJ
- DETALHE: Impacto financeiro se CFOP estiver incorreto
"""

import pandas as pd
from typing import Dict, Any, List
from datetime import datetime

try:
    from enriquecedor_fiscal_api import enriquecer_cnpj
except:
    def enriquecer_cnpj(cnpj):
        return {"regime_tributario": "Desconhecido"}

def obter_regime_do_cnpj(cnpj: str) -> str:
    """Obtém regime tributário do CNPJ"""
    try:
        dados = enriquecer_cnpj(cnpj)
        return dados.get("regime_tributario", "Desconhecido")
    except:
        return "Desconhecido"

def enriquecer_regimes_emitentes(df: pd.DataFrame) -> pd.DataFrame:
    """Enriquece DataFrame com regime dos emitentes"""
    df_novo = df.copy()
    df_novo["regime_emitente"] = df_novo["emitente_doc"].apply(obter_regime_do_cnpj)
    return df_novo

def calcular_metricas_financeiras(df: pd.DataFrame) -> Dict[str, Any]:
    """Calcula métricas financeiras"""
    df_num = df.copy()
    df_num["valor_total_num"] = pd.to_numeric(df_num["valor_total_num"], errors="coerce").fillna(0)
    
    total = df_num["valor_total_num"].sum()
    media = df_num["valor_total_num"].mean()
    maior = df_num["valor_total_num"].max()
    menor = df_num["valor_total_num"].min()
    
    top3_total = df_num.nlargest(3, "valor_total_num")["valor_total_num"].sum()
    concentracao = (top3_total / total * 100) if total > 0 else 0
    
    return {
        "total": total,
        "media": media,
        "maior": maior,
        "menor": menor,
        "quantidade_nfs": len(df),
        "concentracao_top3": concentracao,
    }

def analisar_por_fornecedor(df: pd.DataFrame) -> pd.DataFrame:
    """Agrupa por fornecedor"""
    grupo = df.groupby("emitente_nome").agg({
        "valor_total_num": ["sum", "mean", "count"],
        "emitente_doc": "first",
        "regime_emitente": "first",
    }).reset_index()
    
    grupo.columns = ["Fornecedor", "Total", "Média", "Quantidade", "CNPJ", "Regime"]
    grupo = grupo.sort_values("Total", ascending=False)
    return grupo

def calcular_impacto_cfop_incorreto(df: pd.DataFrame, aliquota_icms: float = 0.18) -> Dict[str, Any]:
    """
    Calcula impacto financeiro se CFOP estiver incorreto
    Para IE isenta: CFOP correto é 5.949 (isento), incorreto seria 5.102 (tributado)
    """
    impacto = {
        "nfs_com_risco": [],
        "total_valor_em_risco": 0.0,
        "icms_indevido_total": 0.0,
        "pis_indevido_total": 0.0,
        "cofins_indevido_total": 0.0,
        "imposto_total_indevido": 0.0,
        "valor_final_com_imposto": 0.0
    }
    
    for idx, row in df.iterrows():
        valor = row.get("valor_total_num", 0)
        nf = row.get("numero_nf")
        emitente = row.get("emitente_nome")
        regime = row.get("regime_emitente", "Desconhecido")
        
        # Só calcula para fornecedores com regime identificado e não Simples Nacional
        if regime in ["Lucro Real/Presumido"]:
            # Cenário: CFOP incorreto = 5.102 (tributado) em vez de 5.949 (isento)
            icms = valor * aliquota_icms
            pis = valor * 0.0165  # 1.65% para Lucro Real
            cofins = valor * 0.0765  # 7.65% para Lucro Real
            
            total_imposto = icms + pis + cofins
            
            impacto["nfs_com_risco"].append({
                "numero_nf": nf,
                "emitente": emitente,
                "valor_nf": valor,
                "icms_indevido": icms,
                "pis_indevido": pis,
                "cofins_indevido": cofins,
                "total_imposto_indevido": total_imposto,
                "valor_final_com_imposto": valor + total_imposto
            })
            
            impacto["total_valor_em_risco"] += valor
            impacto["icms_indevido_total"] += icms
            impacto["pis_indevido_total"] += pis
            impacto["cofins_indevido_total"] += cofins
            impacto["imposto_total_indevido"] += total_imposto
            impacto["valor_final_com_imposto"] += valor + total_imposto
    
    return impacto

def gerar_relatorio_impacto_cfop(impacto: Dict[str, Any]) -> str:
    """Gera relatório detalhado de impacto CFOP incorreto"""
    
    relatorio = """
════════════════════════════════════════════════════════════════════════════════

⚠️  CENÁRIO: CFOP INCORRETO (5.102 Tributado vs 5.949 Isento)

IMPACTO FINANCEIRO ESTIMADO:

"""
    
    if len(impacto["nfs_com_risco"]) == 0:
        relatorio += "✅ Nenhuma NF com risco identificada"
        return relatorio
    
    relatorio += f"""
RESUMO DO RISCO:
  • Quantidade de NFs em risco: {len(impacto['nfs_com_risco'])}
  • Valor total em risco: R$ {impacto['total_valor_em_risco']:,.2f}
  
  • ICMS indevido total: R$ {impacto['icms_indevido_total']:,.2f}
  • PIS indevido total: R$ {impacto['pis_indevido_total']:,.2f}
  • COFINS indevido total: R$ {impacto['cofins_indevido_total']:,.2f}
  ════════════════════════════════
  • IMPOSTO TOTAL INDEVIDO: R$ {impacto['imposto_total_indevido']:,.2f}
  
  VALOR FINAL (se CFOP incorreto): R$ {impacto['valor_final_com_imposto']:,.2f}

ANÁLISE DETALHADA POR NF:

"""
    
    for nf_info in impacto["nfs_com_risco"]:
        relatorio += f"""
NF {nf_info['numero_nf']} - {nf_info['emitente']}
  Valor Original: R$ {nf_info['valor_nf']:,.2f}
  
  Impostos Indevidos:
    • ICMS (18%): R$ {nf_info['icms_indevido']:,.2f}
    • PIS (1,65%): R$ {nf_info['pis_indevido']:,.2f}
    • COFINS (7,65%): R$ {nf_info['cofins_indevido']:,.2f}
    ─────────────────────────────
    • Total de Impostos: R$ {nf_info['total_imposto_indevido']:,.2f}
  
  Valor Final (com impostos): R$ {nf_info['valor_final_com_imposto']:,.2f}
  % de aumento: {(nf_info['total_imposto_indevido']/nf_info['valor_nf']*100):.2f}%

"""
    
    return relatorio

def gerar_analise_completa(df: pd.DataFrame, regime_destinatario: str) -> str:
    """Gera análise fiscal + financeira com detalhamento de impacto CFOP"""
    
    df = enriquecer_regimes_emitentes(df)
    destinatario_ie_isenta = "isent" in regime_destinatario.lower()
    
    metricas = calcular_metricas_financeiras(df)
    por_fornecedor = analisar_por_fornecedor(df)
    
    relatorio = f"""
╔════════════════════════════════════════════════════════════════════════════════╗
║              📊 ANÁLISE EXECUTIVA - FISCAL + FINANCEIRA                        ║
║                    HOTEIS DESIGN S.A. - Notas de Entrada                      ║
╚════════════════════════════════════════════════════════════════════════════════╝

📌 DESTINATÁRIO: HOTEIS DESIGN S.A.
Regime: {regime_destinatario}
{'✅ IE ISENTA - Operações devem ser isentas (CFOP 5.949)' if destinatario_ie_isenta else '✅ IE ATIVA - Pode aproveitar créditos de ICMS'}

════════════════════════════════════════════════════════════════════════════════

💰 ANÁLISE FINANCEIRA

Total Agregado:           R$ {metricas['total']:>12,.2f}
Quantidade de NFs:        {metricas['quantidade_nfs']:>12.0f}
Valor Médio por NF:       R$ {metricas['media']:>12,.2f}
Maior Compra:             R$ {metricas['maior']:>12,.2f}
Menor Compra:             R$ {metricas['menor']:>12,.2f}
Concentração Top 3:       {metricas['concentracao_top3']:>12.1f}%

Interpretação:
  • Total de compras: R$ {metricas['total']:,.2f}
  • As 3 maiores compras representam {metricas['concentracao_top3']:.1f}% do total
    {'(⚠️ Concentrada em poucos fornecedores)' if metricas['concentracao_top3'] > 70 else '(✅ Distribuída)'}

════════════════════════════════════════════════════════════════════════════════

🏢 ANÁLISE POR FORNECEDOR

"""
    
    for count, (idx, row) in enumerate(por_fornecedor.iterrows(), 1):
        regime_str = row["Regime"] if row["Regime"] != "Desconhecido" else "❌ DESCONHECIDO"
        relatorio += f"""
{count}. {row["Fornecedor"]}
   CNPJ: {row["CNPJ"]}
   • Total: R$ {row["Total"]:>12,.2f}
   • NFs: {row["Quantidade"]:.0f} | Média: R$ {row["Média"]:,.2f}
   • Regime: {regime_str}
"""
    
    relatorio += f"""

════════════════════════════════════════════════════════════════════════════════

🎯 ANÁLISE FISCAL

"""
    
    if destinatario_ie_isenta:
        simples_count = (df["regime_emitente"] == "Simples Nacional").sum()
        lucro_count = (df["regime_emitente"] == "Lucro Real/Presumido").sum()
        desconhecido_count = (df["regime_emitente"] == "Desconhecido").sum()
        
        lucro_df = df[df["regime_emitente"] == "Lucro Real/Presumido"]
        lucro_valor_total = lucro_df["valor_total_num"].sum()
        
        relatorio += f"""
Sua empresa possui IE ISENTA

CFOP Correto: 5.949 (Operação isenta)
CFOP Incorreto: 5.102 (Operação tributada)

Fornecedores por Regime:
  • Simples Nacional: {simples_count} NF(s) - ✅ Sem ICMS destacado
  • Lucro Real/Presumido: {lucro_count} NF(s) - ⚠️ ALTO RISCO SE CFOP INCORRETO
  • Desconhecido: {desconhecido_count} NF(s) - ⚠️ Validar manualmente

IMPACTO SE CFOP ESTIVER INCORRETO:
  • NFs com Lucro Real: {lucro_count}
  • Valor total em risco: R$ {lucro_valor_total:,.2f}
"""
        
        # Calcular impacto
        impacto = calcular_impacto_cfop_incorreto(df)
        relatorio += gerar_relatorio_impacto_cfop(impacto)
        
        relatorio += f"""

════════════════════════════════════════════════════════════════════════════════

🚨 CONSEQUÊNCIAS FINANCEIRAS E TRIBUTÁRIAS

SE CFOP ESTIVER INCORRETO (5.102 em vez de 5.949):

1. IMPACTO FINANCEIRO DIRETO:
   ❌ Custo adicional: R$ {impacto['imposto_total_indevido']:,.2f}
   ❌ Seu custo final seria: R$ {impacto['valor_final_com_imposto']:,.2f}
   
2. IMPACTO TRIBUTÁRIO:
   ❌ ICMS: R$ {impacto['icms_indevido_total']:,.2f} (não recuperável para IE isenta)
   ❌ PIS: R$ {impacto['pis_indevido_total']:,.2f} (não recuperável)
   ❌ COFINS: R$ {impacto['cofins_indevido_total']:,.2f} (não recuperável)
   
3. IMPACTO FISCAL/LEGAL:
   ❌ Risco de auditoria fiscal (empresa isenta com ICMS)
   ❌ Possível multa de 75% sobre ICMS indevido
   ❌ Juros de mora
   ❌ Possibilidade de bloqueio de créditos futuros

4. IMPACTO CONTÁBIL:
   ❌ Aumento de custos operacionais
   ❌ Redução de lucratividade
   ❌ Má interpretação de índices de gestão

════════════════════════════════════════════════════════════════════════════════

✅ AÇÕES RECOMENDADAS

1. VALIDAÇÃO URGENTE:
   ☐ Revisar todas as {lucro_count} NF(s) de Lucro Real/Presumido
   ☐ Verificar CFOP em cada nota (deve ser 5.949)
   ☐ Verificar se ICMS foi destacado (NÃO deve aparecer)
   
2. SE CFOP ESTIVER INCORRETO:
   ☐ Contactar IMEDIATAMENTE o fornecedor
   ☐ Solicitar emissão de Nota Fiscal Complementar (NFC-e) corrigida
   ☐ Documentar toda a comunicação com o fornecedor
   ☐ Guardar comprovante de recebimento
   
3. REGULARIZAÇÃO FISCAL:
   ☐ Abrir chamado com contador para análise
   ☐ Verificar se há ECF/DANFE com divergências
   ☐ Se necessário, fazer ajuste no livro fiscal
   
4. PREVENÇÃO FUTURA:
   ☐ Implementar validação de CFOP no recebimento
   ☐ Treinar equipe sobre CFOPs corretos para IE isenta
   ☐ Criar rotina mensal de auditoria fiscal

════════════════════════════════════════════════════════════════════════════════

📊 TOP 3 MAIORES COMPRAS (Maior Risco)

"""
    
    else:
        simples_count = (df["regime_emitente"] == "Simples Nacional").sum()
        lucro_count = (df["regime_emitente"] == "Lucro Real/Presumido").sum()
        
        relatorio += f"""
Sua empresa tem IE ATIVA - Créditos disponíveis:

Fornecedores por Regime:
  • Simples Nacional: {simples_count} NF(s) - ❌ Sem crédito de ICMS
  • Lucro Real/Presumido: {lucro_count} NF(s) - ✅ Com crédito de ICMS

ANÁLISE DE CRÉDITO:
  • NFs com crédito: {lucro_count}
  • Valor base para crédito: R$ {df[df['regime_emitente']=='Lucro Real/Presumido']['valor_total_num'].sum():,.2f}
  • ICMS a recuperar (est. 18%): R$ {df[df['regime_emitente']=='Lucro Real/Presumido']['valor_total_num'].sum() * 0.18:,.2f}

════════════════════════════════════════════════════════════════════════════════

📊 TOP 3 MAIORES COMPRAS

"""
    
    top3 = df.nlargest(3, "valor_total_num")
    for count, (idx, row) in enumerate(top3.iterrows(), 1):
        relatorio += f"""
{count}. NF {row['numero_nf']}: R$ {row['valor_total_num']:,.2f}
   Fornecedor: {row['emitente_nome']}
   Regime: {row.get('regime_emitente', 'Desconhecido')}
"""
    
    relatorio += f"""

════════════════════════════════════════════════════════════════════════════════

📅 Relatório gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
✅ Análise Completa com Detalhamento de Impacto CFOP
"""
    
    return relatorio