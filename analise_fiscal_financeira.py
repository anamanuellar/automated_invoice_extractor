"""
Análise Executiva - Fiscal + Financeira
Com regime tributário do destinatário e análise comparativa
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple
from datetime import datetime

def enriquecer_com_regime_destinatario(df: pd.DataFrame, cnpj_destinatario: str, regime_destinatario: str) -> pd.DataFrame:
    """
    Adiciona regime do destinatário a todas as linhas para comparação fiscal
    
    Args:
        df: DataFrame com dados das NFs
        cnpj_destinatario: CNPJ da empresa destino (ex: HOTEIS DESIGN)
        regime_destinatario: Regime tributário (Simples/Lucro/Isento)
    
    Returns:
        DataFrame enriquecido com colunas de regime destinatário
    """
    df_novo = df.copy()
    df_novo["dest_doc"] = df_novo["dest_doc"].fillna("")
    df_novo["regime_tributario_destinatario"] = regime_destinatario
    df_novo["ie_destinatario_isenta"] = "isenta" in regime_destinatario.lower()
    
    return df_novo

def calcular_metricas_financeiras(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Calcula métricas financeiras gerais
    """
    df_num = df.copy()
    df_num["valor_total_num"] = pd.to_numeric(df_num["valor_total_num"], errors="coerce").fillna(0)
    
    total = df_num["valor_total_num"].sum()
    media = df_num["valor_total_num"].mean()
    maior = df_num["valor_total_num"].max()
    menor = df_num["valor_total_num"].min()
    
    return {
        "total": total,
        "media": media,
        "maior": maior,
        "menor": menor,
        "quantidade_nfs": len(df),
        "concentracao_top3": df_num.nlargest(3, "valor_total_num")["valor_total_num"].sum() / total * 100 if total > 0 else 0,
    }

def analisar_por_fornecedor(df: pd.DataFrame) -> pd.DataFrame:
    """
    Agrupa e analisa dados por fornecedor
    """
    grupo = df.groupby("emitente_nome").agg({
        "valor_total_num": ["sum", "mean", "count"],
        "regime_tributario_emitente": "first",
        "optante_simples": "first",
        "ie_isenta": "first",
    }).reset_index()
    
    grupo.columns = ["Fornecedor", "Total", "Média", "Quantidade", "Regime", "Simples", "IE Isenta"]
    grupo = grupo.sort_values("Total", ascending=False)
    
    return grupo

def analisar_compatibilidade_fiscal(df: pd.DataFrame, regime_dest: str) -> Dict[str, Any]:
    """
    Analisa compatibilidade fiscal entre emitente e destinatário
    
    Retorna:
    - Potencial perda de crédito
    - Operações problemáticas
    - Conformidade tributária
    """
    alertas = {
        "total_alertas": 0,
        "detalhes": []
    }
    
    ie_dest_isenta = "isenta" in regime_dest.lower()
    
    for idx, row in df.iterrows():
        nf = row.get("numero_nf")
        emitente = row.get("emitente_nome")
        valor = row.get("valor_total_num", 0)
        regime_emit = row.get("regime_tributario_emitente", "desconhecido")
        simples = row.get("optante_simples", False)
        ie_isenta_emit = row.get("ie_isenta", False)
        
        # Cenário 1: Destinatário isento recebendo de fornecedor com ICMS
        if ie_dest_isenta and regime_emit in ["Lucro Real/Presumido", "desconhecido"]:
            alertas["detalhes"].append({
                "tipo": "⚠️ ICMS em Operação Isenta",
                "nf": nf,
                "emitente": emitente,
                "valor": valor,
                "severidade": "CRÍTICA",
                "mensagem": f"NF de fornecedor com regime normal para empresa com IE isenta. Verificar CFOP (esperado 5.949)",
                "impacto": f"R$ {valor * 0.205:.2f}" if valor > 0 else "Calculado"
            })
            alertas["total_alertas"] += 1
        
        # Cenário 2: Simples Nacional sem destaque de PIS/COFINS
        if simples and regime_dest not in ["Simples Nacional"]:
            alertas["detalhes"].append({
                "tipo": "ℹ️ Simples Nacional",
                "nf": nf,
                "emitente": emitente,
                "valor": valor,
                "severidade": "INFORMAÇÃO",
                "mensagem": "Fornecedor Simples Nacional - Sem direito a crédito de PIS/COFINS",
                "impacto": "Sem crédito disponível"
            })
            alertas["total_alertas"] += 1
        
        # Cenário 3: Regime desconhecido
        if regime_emit == "desconhecido":
            alertas["detalhes"].append({
                "tipo": "⚠️ Regime Desconhecido",
                "nf": nf,
                "emitente": emitente,
                "valor": valor,
                "severidade": "MÉDIA",
                "mensagem": "Regime tributário do emitente não foi identificado. Validar via API ou manualmente",
                "impacto": "Impossível avaliar conformidade"
            })
            alertas["total_alertas"] += 1
    
    return alertas

def gerar_analise_financeira_completa(df: pd.DataFrame, regime_destinatario: str) -> str:
    """
    Gera análise financeira completa com insights
    """
    df = enriquecer_com_regime_destinatario(df, "", regime_destinatario)
    
    # Métricas gerais
    metricas = calcular_metricas_financeiras(df)
    
    # Por fornecedor
    por_fornecedor = analisar_por_fornecedor(df)
    
    # Compatibilidade fiscal
    compat = analisar_compatibilidade_fiscal(df, regime_destinatario)
    
    # Construir relatório
    relatorio = f"""
╔════════════════════════════════════════════════════════════════════════════════╗
║              📊 ANÁLISE EXECUTIVA - FISCAL + FINANCEIRA                        ║
║                    HOTEIS DESIGN S.A. - Notas de Entrada                      ║
╚════════════════════════════════════════════════════════════════════════════════╝

📌 REGIME TRIBUTÁRIO DESTINATÁRIO: {regime_destinatario}
{'⚠️  EMPRESA COM IE ISENTA - Atenção com operações tributadas' if 'isent' in regime_destinatario.lower() else '✅ Empresa com regime normal'}

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
  • Média por NF: R$ {metricas['media']:,.2f}
  • As 3 maiores compras representam {metricas['concentracao_top3']:.1f}% do total
    {'(⚠️ Concentrada)' if metricas['concentracao_top3'] > 70 else '(✅ Distribuída)'}

════════════════════════════════════════════════════════════════════════════════

🏢 ANÁLISE POR FORNECEDOR

"""
    
    for count, (idx, row) in enumerate(por_fornecedor.iterrows(), 1):
        regime_str = row["Regime"] if row["Regime"] != "desconhecido" else "❌ DESCONHECIDO"
        simples_str = "✅ Sim" if row["Simples"] else "❌ Não"
        
        relatorio += f"""
{count}. {row["Fornecedor"]}
   • Total: R$ {row["Total"]:>12,.2f}
   • NFs: {row["Quantidade"]:.0f} | Média: R$ {row["Média"]:,.2f}
   • Regime: {regime_str}
   • Simples Nacional: {simples_str}
"""
    
    relatorio += f"""

════════════════════════════════════════════════════════════════════════════════

⚠️  ALERTAS FISCAIS ({compat['total_alertas']} identificados)

"""
    
    if compat['total_alertas'] == 0:
        relatorio += "✅ Nenhum alerta identificado - Operações em conformidade"
    else:
        for alerta in compat["detalhes"]:
            relatorio += f"""
{alerta['tipo']}
  NF: {alerta['nf']} | Fornecedor: {alerta['emitente']} | Valor: R$ {alerta['valor']:,.2f}
  Severidade: {alerta['severidade']}
  Mensagem: {alerta['mensagem']}
  Impacto: {alerta['impacto']}

"""
    
    relatorio += f"""
════════════════════════════════════════════════════════════════════════════════

📋 RECOMENDAÇÕES

1. CONFORMIDADE FISCAL
"""
    
    if "isent" in regime_destinatario.lower():
        relatorio += """
   ⚠️  CRÍTICO - Empresa com IE Isenta:
   • Verificar se todos os CFOPs estão corretos (5.949 para operações isentas)
   • Confirmação: Nenhuma operação deve ter ICMS destacado
   • Ação: Contactar fornecedores para corrigir emissão
"""
    else:
        relatorio += """
   ✅ Empresa com regime normal - Créditos de ICMS deverão ser aproveitados
"""
    
    relatorio += f"""

2. GESTÃO DE FORNECEDORES
   • {len(por_fornecedor)} fornecedores identificados
   • {por_fornecedor[por_fornecedor['Simples']].shape[0]} fornecedores Simples Nacional
   • {por_fornecedor[por_fornecedor['Regime']=='desconhecido'].shape[0]} fornecedores com regime desconhecido ⚠️

3. ITENS COM MAIOR VALOR
"""
    
    top3 = df.nlargest(3, "valor_total_num")
    for idx, row in top3.iterrows():
        relatorio += f"""
   • NF {row['numero_nf']}: R$ {row['valor_total_num']:,.2f} - {row['emitente_nome']}
"""
    
    relatorio += f"""

════════════════════════════════════════════════════════════════════════════════

📅 Data do Relatório: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
✅ Status: Análise Completa
"""
    
    return relatorio

if __name__ == "__main__":
    # Teste
    print("Aguarde...")
    # Será usado pelo streamlit