import streamlit as st
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Any, Optional
from datetime import datetime
from sklearn.ensemble import IsolationForest
import warnings
warnings.filterwarnings('ignore') # Ignorar avisos do sklearn e pandas

# =============== 1. FUNÇÕES DE INTELIGÊNCIA ARTIFICIAL ===============

# Simulação da Função de Classificação (mantida para evitar dependência externa)
def classify_expense_hf(text: str) -> Dict[str, Any]:
    """Simula a classificação de despesa por um modelo Hugging Face."""
    # Simulação para evitar quebra no código, já que não temos o modelo real
    text_lower = text.lower()
    
    if "cloud" in text_lower or "ec2" in text_lower or "azure" in text_lower:
        categoria = "Infraestrutura de TI"
    elif "licença" in text_lower or "software" in text_lower or "office" in text_lower:
        categoria = "Software e Licenças"
    elif "passagem" in text_lower or "hotel" in text_lower:
        categoria = "Viagens e Deslocamentos"
    else:
        categoria = "Outros Serviços"
        
    return {
        "status": "OK",
        "categoria": categoria,
        "confianca": 0.85, # Confiança simulada
        "alternativas": {"Administrativo": 0.10, "Marketing": 0.05}
    }

# Simulação da Função de Análise de Risco (mantida)
def analyze_supplier_risk(cnpj: Optional[str]) -> Dict[str, Any]:
    """Simula a análise de risco de um fornecedor pelo CNPJ."""
    if cnpj and '0001' in cnpj:
        score = np.random.uniform(0.7, 0.95)
        risco = "Baixo" if score > 0.85 else "Médio"
    else:
        score = np.random.uniform(0.5, 0.7)
        risco = "Médio" if score > 0.6 else "Alto"
        
    return {
        "risco_score": round(score, 2),
        "risco_nivel": risco,
        "detalhes": "Consulta de situação fiscal e saúde financeira (Simulado)."
    }

# Simulação da Função de Previsão (mantida)
def simple_forecast(df: pd.DataFrame) -> pd.DataFrame:
    """Simula uma previsão simples (média móvel) para os próximos 3 meses."""
    if df.empty or 'data_emissao' not in df.columns or 'valor_total_num' not in df.columns:
        return pd.DataFrame()
        
    df = df.copy()
    df['data_emissao'] = pd.to_datetime(df['data_emissao'], format="%d/%m/%Y", errors='coerce')
    df.dropna(subset=['data_emissao', 'valor_total_num'], inplace=True)
    
    # Agrupa por mês e calcula a média
    df_mensal = df.set_index('data_emissao')['valor_total_num'].resample('M').sum()
    
    # Simulação de Média Móvel Simples
    rolling_avg = df_mensal.tail(3).mean() # Média dos últimos 3 meses
    
    ultima_data = df_mensal.index[-1]
    datas_futuras = pd.date_range(start=ultima_data + pd.Timedelta(days=1), periods=3, freq='M')
    
    previsoes = pd.DataFrame({
        'Mês': datas_futuras.strftime('%Y-%m'),
        'Valor Previsto (R$)': rolling_avg * np.random.uniform(0.9, 1.1) # Adiciona um ruído simulado
    })
    
    return previsoes

# ================= 2. NOVA FUNÇÃO: DETECÇÃO DE ANOMALIAS =================

def detect_anomalies_isolation_forest(df: pd.DataFrame) -> pd.DataFrame:
    """
    Detecta anomalias (outliers) na coluna 'valor_total_num' usando Isolation Forest.
    """
    if df.empty or 'valor_total_num' not in df.columns:
        return pd.DataFrame()

    df_anomalia = df.copy()
    df_anomalia.dropna(subset=['valor_total_num'], inplace=True)
    
    # Precisa de mais de um dado para rodar a anomalia
    if len(df_anomalia) < 2:
        st.warning("É necessário mais de uma nota fiscal com valores válidos para rodar o detector de anomalias.")
        return pd.DataFrame()

    # Preparar dados para o modelo (requer reshape para 2D)
    data = df_anomalia['valor_total_num'].values.astype(float).reshape(-1, 1)
    
    # Inicializar e treinar o modelo Isolation Forest
    # O parâmetro 'contamination' é a proporção esperada de outliers (5% é um bom chute inicial)
    model = IsolationForest(
        contamination=0.05, 
        random_state=42, 
        n_estimators=100
    )
    
    # O modelo retorna -1 para anomalias (outliers) e 1 para observações normais
    df_anomalia['anomaly_score'] = model.fit_predict(data)
    
    # Filtrar apenas as anomalias
    anomalies = df_anomalia[df_anomalia['anomaly_score'] == -1].sort_values(
        by='valor_total_num', ascending=False
    ).reset_index(drop=True)
    
    # Calcular o Z-Score para contextualizar a anomalia (quão longe da média está)
    media = df_anomalia['valor_total_num'].mean()
    std = df_anomalia['valor_total_num'].std()
    
    if std > 0:
        anomalies['Z-Score'] = (anomalies['valor_total_num'] - media) / std
    else:
        anomalies['Z-Score'] = 0.0 # Evitar divisão por zero
        
    # Colunas de interesse no resultado
    anomalies_output = anomalies[[
        'data_emissao', 'emitente_nome', 'numero_nf', 'valor_total_num', 'Z-Score'
    ]].rename(columns={
        'valor_total_num': 'Valor Total (R$)'
    })
    
    anomalies_output['Valor Total (R$)'] = anomalies_output['Valor Total (R$)'].map('R$ {:,.2f}'.format)
    anomalies_output['Z-Score'] = anomalies_output['Z-Score'].map('{:.2f}'.format)

    return anomalies_output


# =============== 3. INTEGRAÇÃO COM STREAMLIT ===============

# Função auxiliar para classificação por item (adaptada, focada em fallback)
def processar_e_exibir_classificacao_por_item(df: pd.DataFrame):
    """
    Processa a classificação focando na descrição geral ou no primeiro item como fallback.
    """
    
    st.markdown("A classificação detalhada por item falhou (dados de item não encontrados).")
    st.markdown("Usando a **Descrição Principal/Emitente** como **Fallback**.")
    st.markdown("---")
    
    # Criar uma coluna de descrição para fallback (prioriza o emitente)
    df_class = df.copy()
    df_class.dropna(subset=['emitente_nome'], inplace=True)
    
    if df_class.empty:
        st.warning("Não há notas com nome do emitente válido para classificação fallback.")
        return

    # Limita o processamento a 100 notas por questão de performance
    df_sample = df_class.head(100)
    
    resultados_classificacao = []
    
    with st.spinner(f"Classificando {len(df_sample)} Notas Fiscais por nome do Emitente (Fallback)..."):
        for index, row in df_sample.iterrows():
            descricao = row['emitente_nome'] # Usa o nome do fornecedor
            valor = row.get('valor_total_num', 0.0)
            
            resultado_ia = classify_expense_hf(descricao)
            
            if resultado_ia['status'] == 'OK':
                resultados_classificacao.append({
                    'Emitente': descricao,
                    'NF Número': row['numero_nf'],
                    'Valor (R$)': f"{valor:.2f}",
                    'Categoria Principal': resultado_ia['categoria'],
                    'Confiança': f"{resultado_ia['confianca']:.1%}"
                })
            else:
                 resultados_classificacao.append({
                    'Emitente': descricao,
                    'NF Número': row['numero_nf'],
                    'Valor (R$)': f"{valor:.2f}",
                    'Categoria Principal': 'Não Classificado',
                    'Confiança': '0%'
                })
    
    if resultados_classificacao:
        df_resultados = pd.DataFrame(resultados_classificacao)
        st.dataframe(df_resultados, use_container_width=True)


def add_ia_to_streamlit(df: pd.DataFrame) -> None:
    
    # Aplicar coerção de tipo fora do fluxo principal
    df['valor_total_num'] = pd.to_numeric(df['valor_total_num'], errors='coerce')
    
    st.divider()
    st.subheader("🤖 Análise com Inteligência Artificial")
    
    tab1, tab2, tab3, tab4 = st.tabs([
        "Classificação (Fallback)",
        "Anomalias de Valor", 
        "Risco de Fornecedores",
        "Previsão de Gastos"
    ])
    
    # TAB 1: Classificação (Fallback)
    with tab1:
        st.markdown("### Classificação Agregada (Fallback)")
        processar_e_exibir_classificacao_por_item(df)

    # TAB 2: Detecção de Anomalias (NOVO)
    with tab2:
        st.markdown("### 🚨 Detecção de Anomalias de Valor (Outliers)")
        st.info("Utiliza o modelo Isolation Forest para identificar Notas Fiscais com valores muito acima ou abaixo do padrão histórico, que podem indicar erros ou fraudes.")
        
        anomalies_df = detect_anomalies_isolation_forest(df)
        
        if anomalies_df.empty:
            st.success("Nenhuma anomalia significativa detectada nos valores totais das Notas Fiscais.")
        else:
            st.warning(f"Foram detectadas **{len(anomalies_df)}** Notas Fiscais com valores anômalos (outliers):")
            st.dataframe(anomalies_df, use_container_width=True)

    # TAB 3: Análise de Risco de Fornecedores
    with tab3:
        st.markdown("### 🛡️ Análise de Risco de Fornecedores")
        st.info("O risco é simulado. Para um resultado real, seria necessário integrar uma API externa (Receita Federal, Serasa, etc.) com base no CNPJ.")
        
        # Simula a análise de risco para cada fornecedor único
        fornecedores_unicos = df['emitente_doc'].dropna().unique()
        if len(fornecedores_unicos) > 0:
            risco_data = []
            for cnpj in fornecedores_unicos[:20]: # Limita para visualização
                nome = df[df['emitente_doc'] == cnpj]['emitente_nome'].iloc[0] if len(df[df['emitente_doc'] == cnpj]['emitente_nome']) > 0 else "Nome Desconhecido"
                risco = analyze_supplier_risk(cnpj)
                
                risco_data.append({
                    'Fornecedor': nome,
                    'CNPJ': cnpj,
                    'Nível de Risco': risco['risco_nivel'],
                    'Score de Risco': risco['risco_score']
                })
            
            df_risco = pd.DataFrame(risco_data)
            st.dataframe(df_risco, use_container_width=True)
        else:
            st.warning("Nenhum CNPJ de fornecedor encontrado para análise de risco.")

    # TAB 4: Previsão de Gastos
    with tab4:
        st.markdown("### 🔮 Previsão de Gastos Futuros")
        st.info("Previsão simples baseada na média móvel dos últimos meses.")
        
        df_forecast = simple_forecast(df)
        
        if df_forecast.empty:
            st.error("Dados insuficientes (menos de 3 meses) ou inválidos para realizar a previsão.")
        else:
            st.markdown("#### Projeção para os Próximos 3 Meses")
            st.dataframe(df_forecast, use_container_width=True)
            
            # Adiciona um gráfico simples (opcional)
            st.bar_chart(df_forecast.set_index('Mês')['Valor Previsto (R$)'].str.replace('R$ ', '').str.replace(',', '').astype(float))