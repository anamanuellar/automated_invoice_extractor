import streamlit as st
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Any, Optional, Sequence, Union
import warnings
warnings.filterwarnings('ignore')


# =============== HUGGING FACE  ===============

def classify_expense_hf(description: str, confidence_threshold: float = 0.5) -> Dict[str, Any]:
    """
    Classifica despesa usando Hugging Face (Modelo BERT)
    - Totalmente grátis
    - Funciona offline
    - Primeira execução demora ~2 min (download do modelo)
    
    Exemplo:
        >>> classify_expense_hf("Amazon Web Services - Cloud Hosting")
        {
            'categoria': 'Infraestrutura IT',
            'confianca': 0.87,
            'alternativas': {...}
        }
    """
    try:
        from transformers import pipeline
        
        # Corrigido: Categorias Fiscais e Financeiras Aprimoradas
        categories = [
            "Infraestrutura/Cloud IT",
            "Software, ERP e Licenças",
            "Consultoria e Auditoria",
            "Marketing e Vendas",
            "Recursos Humanos e Benefícios",
            "Aluguel, IPTU e Condomínio",
            "Despesas com Viagem e Hospedagem",
            "Combustível, Fretes e Logística",
            "Manutenção, Reparo e Serviços Gerais",
            "Materiais de Escritório e Suprimentos",
            "Serviços Financeiros (Juros, Taxas)",
            "Impostos e Contribuições (Fed/Est/Mun)",
            "Seguro (Patrimonial, Vida, Saúde)",
            "Educação e Treinamento",
            "Outros Gastos Operacionais"
        ]
        
        @st.cache_resource
        def load_classifier() -> Any:
            """Carregar modelo uma única vez"""
            return pipeline(
                "zero-shot-classification",
                model="facebook/bart-large-mnli",
                device=-1  # CPU
            )
        
        classifier = load_classifier()
        
        # CORREÇÃO: Converter para lista explicitamente
        result = classifier(description, categories)
        
        # Garantir que result é um dicionário
        if isinstance(result, dict):
            labels = result.get('labels', [])
            scores = result.get('scores', [])
        else:
            # Se for outro tipo, tentar acessar como atributos
            labels = list(result['labels']) if hasattr(result, '__getitem__') else []
            scores = list(result['scores']) if hasattr(result, '__getitem__') else []
        
        # Se conseguiu os dados
        if labels and scores:
            alternativas = {}
            for i in range(1, min(4, len(labels))):
                if i < len(labels) and i < len(scores):
                    alternativas[str(labels[i])] = float(scores[i])
            
            return {
                'categoria': str(labels[0]) if labels else 'Desconhecido',
                'confianca': float(scores[0]) if scores else 0.0,
                'alternativas': alternativas,
                'status': 'OK'
            }
        else:
            return {
                'categoria': 'Desconhecido',
                'confianca': 0.0,
                'alternativas': {},
                'status': 'Erro ao processar resultado'
            }
    
    except Exception as e:
        return {
            'categoria': 'Desconhecido',
            'confianca': 0.0,
            'alternativas': {},
            'status': f'Erro: {str(e)}'
        }


# =============== DETECÇÃO DE ANOMALIAS ===============

def detect_anomalies(values: List[float]) -> Dict[str, Any]:
    """
    Detecta valores anômalos em um histórico
    
    Exemplo:
        >>> historico = [5000, 5100, 5050, 50000, 5200, 5150]
        >>> detect_anomalies(historico)
        {
            'anomalias': [{'indice': 3, 'valor': 50000, 'desvio': 842.86}],
            'media': 5250,
            'desvio_padrao': 17521.47
        }
    """
    if len(values) < 5:
        return {
            'status': 'Dados insuficientes',
            'anomalias': [],
            'total_anomalias': 0,
            'valor_medio': 0.0,
            'desvio_padrao': 0.0
        }
    
    try:
        from sklearn.ensemble import IsolationForest
        
        X = np.array(values, dtype=float).reshape(-1, 1)
        model = IsolationForest(contamination=0.1, random_state=42)
        predictions = model.fit_predict(X)
        
        anomalias: List[Dict[str, Any]] = []
        for idx, pred in enumerate(predictions):
            if pred == -1:  # -1 = anomalia
                media = float(np.mean(values))
                if media != 0:
                    desvio_pct = ((values[idx] - media) / media * 100)
                else:
                    desvio_pct = 0.0
                
                anomalias.append({
                    'indice': int(idx),
                    'valor': float(values[idx]),
                    'desvio_percentual': round(desvio_pct, 2)
                })
        
        return {
            'status': 'OK',
            'total_anomalias': len(anomalias),
            'anomalias': anomalias,
            'valor_medio': round(float(np.mean(values)), 2),
            'desvio_padrao': round(float(np.std(values)), 2)
        }
    
    except Exception as e:
        return {
            'status': f'Erro: {str(e)}',
            'anomalias': [],
            'total_anomalias': 0,
            'valor_medio': 0.0,
            'desvio_padrao': 0.0
        }


# =============== ANÁLISE DE RISCO DE FORNECEDOR ===============

def analyze_supplier_risk(supplier_name: str, 
                         nf_history: Sequence[Dict[Any, Any]]) -> Dict[str, Any]:
    """
    Analisa risco de um fornecedor baseado no histórico de NFs
    """
    supplier_nfs: List[Dict[Any, Any]] = [nf for nf in nf_history 
                    if nf.get('fornecedor') == supplier_name]
    
    if not supplier_nfs:
        return {
            'status': 'Dados insuficientes',
            'risco': 'DESCONHECIDO',
            'score': 0.0,
            'total_nfs': 0,
            'taxa_atraso': '0%',
            'motivos': []
        }
    
    try:
        total_nfs = len(supplier_nfs)
        
        # Atrasos
        nfs_atrasadas = sum(1 for nf in supplier_nfs 
                           if nf.get('atrasada', False))
        taxa_atraso = nfs_atrasadas / total_nfs if total_nfs > 0 else 0
        
        # Variação de valor
        valores = [float(nf.get('valor', 0)) for nf in supplier_nfs]
        media_valores = float(np.mean(valores)) if valores else 0
        desvio_valores = float(np.std(valores)) if valores else 0
        coeficiente_variacao = desvio_valores / media_valores if media_valores != 0 else 0
        
        # Score de risco (0-10, onde 10 é máximo risco)
        risk_score: float = 0.0
        motivos: List[str] = []
        
        if taxa_atraso > 0.3:
            risk_score += 3.0
            motivos.append(f"Taxa de atraso alta: {taxa_atraso:.1%}")
        
        if coeficiente_variacao > 0.5:
            risk_score += 2.0
            motivos.append(f"Valores muito variáveis (CV: {coeficiente_variacao:.2f})")
        
        if total_nfs < 3:
            risk_score += 1.0
            motivos.append("Histórico limitado")
        
        # Classificar risco
        if risk_score < 2:
            risco = "BAIXO ✅"
        elif risk_score < 5:
            risco = "MÉDIO ⚠️"
        else:
            risco = "ALTO 🚨"
        
        return {
            'status': 'OK',
            'fornecedor': supplier_name,
            'risco': risco,
            'score': round(risk_score, 1),
            'total_nfs': total_nfs,
            'taxa_atraso': f"{taxa_atraso:.1%}",
            'motivos': motivos
        }
    
    except Exception as e:
        return {
            'status': f'Erro: {str(e)}',
            'risco': 'DESCONHECIDO',
            'score': 0.0,
            'total_nfs': 0,
            'taxa_atraso': '0%',
            'motivos': []
        }


# =============== PREVISÃO SIMPLES ===============

def simple_forecast(values: List[float], periods: int = 30) -> Dict[str, Any]:
    """
    Previsão simples de valores usando média móvel e tendência
    """
    if len(values) < 3:
        return {'status': 'Dados insuficientes'}
    
    try:
        # Converter para float
        valores_float = [float(v) for v in values]
        
        # Calcular tendência
        x_values = np.array(list(range(len(valores_float))), dtype=float)
        y_values = np.array(valores_float, dtype=float)
        
        # Usar polyfit ao invés de linregress (mais simples e sem problemas de tipo)
        coeffs = np.polyfit(x_values, y_values, 1)
        slope = float(coeffs[0])
        intercept = float(coeffs[1])
        
        # Calcular R-value manualmente
        y_pred = slope * x_values + intercept
        ss_res = float(np.sum((y_values - y_pred) ** 2))
        ss_tot = float(np.sum((y_values - np.mean(y_values)) ** 2))
        r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0
        r_value = float(np.sqrt(abs(r_squared)))
        
        # Fazer previsão
        forecasts = []
        for i in range(1, periods + 1):
            valor_previsto = slope * (len(valores_float) + i) + intercept
            forecasts.append(round(max(0.0, valor_previsto), 2))  # Não negativo
        
        # Classificar tendência
        media_valores = float(np.mean(valores_float))
        if slope > media_valores * 0.05:
            tendencia = "CRESCENTE 📈"
        elif slope < -media_valores * 0.05:
            tendencia = "DECRESCENTE 📉"
        else:
            tendencia = "ESTÁVEL 📊"
        
        return {
            'status': 'OK',
            'proximos_periodos': forecasts,
            'tendencia': tendencia,
            'valor_medio_previsto': round(float(np.mean(forecasts)), 2),
            'confiabilidade': f"{r_value:.1%}"
        }
    
    except Exception as e:
        return {
            'status': f'Erro: {str(e)}',
            'proximos_periodos': [],
            'tendencia': 'Desconhecido',
            'valor_medio_previsto': 0.0,
            'confiabilidade': '0%'
        }


# =============== INTEGRAÇÃO COM STREAMLIT (ADAPTADA) ===============

def processar_e_exibir_classificacao_por_item(df: pd.DataFrame):
    """
    Novo bloco para selecionar NF, processar itens e exibir a classificação.
    """
    
    # 1. Preparar lista de NFs que têm itens extraídos
    df_com_itens = df[df['itens_nf'].apply(lambda x: isinstance(x, list) and len(x) > 0)]
    
    if df_com_itens.empty:
        st.info("Nenhuma Nota Fiscal com dados de itens extraídos para classificação.")
        return
        
    # Criar um identificador para seleção
    df_com_itens['nf_id'] = df_com_itens.apply(
        lambda row: f"NF {row['numero_nf']} - {row['emitente_nome']} (R$ {row['valor_total_num']:.2f})"
        if row['valor_total_num'] is not None else f"NF {row['numero_nf']} - {row['emitente_nome']}", 
        axis=1
    )
    
    nf_selecionada_id = st.selectbox(
        "Selecione uma Nota Fiscal com itens extraídos:",
        df_com_itens['nf_id'].tolist()
    )
    
    if not nf_selecionada_id:
        return

    # 2. Obter os dados da NF selecionada
    nf_row = df_com_itens[df_com_itens['nf_id'] == nf_selecionada_id].iloc[0]
    itens_nf: List[Dict[str, Any]] = nf_row['itens_nf']
    
    st.subheader(f"Análise de Itens da NF {nf_row.get('numero_nf', '')}")
    
    resultados_classificacao = []
    total_classificado = 0.0

    with st.spinner("Classificando cada item da Nota Fiscal..."):
        for i, item in enumerate(itens_nf):
            descricao = item.get('descricao_item', 'Descrição Vazia')
            valor = item.get('valor_item', 0.0)
            
            # Chama a função de classificação para a descrição do ITEM
            resultado_ia = classify_expense_hf(descricao)
            
            if resultado_ia['status'] == 'OK':
                total_classificado += valor
                resultados_classificacao.append({
                    'Item': descricao,
                    'Valor (R$)': f"{valor:.2f}",
                    'Categoria Principal': resultado_ia['categoria'],
                    'Confiança': f"{resultado_ia['confianca']:.1%}",
                    'Alternativas': ', '.join([f"{k} ({v:.1%})" for k, v in resultado_ia['alternativas'].items()])
                })
            else:
                # Se falhar, registra como 'Não Classificado'
                 resultados_classificacao.append({
                    'Item': descricao,
                    'Valor (R$)': f"{valor:.2f}",
                    'Categoria Principal': 'Não Classificado',
                    'Confiança': '0%',
                    'Alternativas': resultado_ia['status']
                })
    
    # 3. Exibir resultados detalhados
    if resultados_classificacao:
        df_resultados = pd.DataFrame(resultados_classificacao)
        st.dataframe(df_resultados, use_container_width=True)
        
        # 4. Sumarizar Rateio (Agrupamento por Categoria)
        st.markdown("---")
        st.markdown("### Resumo do Rateio por Categoria")
        
        # Converter a coluna Valor (R$) para float para o agrupamento
        df_resultados['_ValorFloat'] = df_resultados['Valor (R$)'].apply(lambda x: float(x.replace(',', '') if isinstance(x, str) else x))
        
        rateio_sumario = df_resultados.groupby('Categoria Principal').agg(
            Valor_Total=('Valor (R$)', lambda x: x.astype(str).str.replace(',', '').astype(float).sum()),
            Num_Itens=('Item', 'count')
        ).reset_index()
        
        rateio_sumario['% da NF'] = (rateio_sumario['Valor_Total'] / nf_row['valor_total_num']) * 100
        
        rateio_sumario = rateio_sumario.sort_values(by='Valor_Total', ascending=False)
        rateio_sumario['Valor_Total'] = rateio_sumario['Valor_Total'].map('R$ {:,.2f}'.format)
        rateio_sumario['% da NF'] = rateio_sumario['% da NF'].map('{:.1f}%'.format)
        
        st.dataframe(rateio_sumario, use_container_width=True)
        
        st.success(f"**Total da NF (Capa):** R$ {nf_row.get('valor_total_num', 0):.2f}")
        st.info(f"**Total de Itens Classificados:** R$ {total_classificado:.2f}")


def add_ia_to_streamlit(df: pd.DataFrame) -> None:
    # ... (Seu código existente)
    
    st.divider()
    st.subheader("🤖 Análise com Inteligência Artificial")
    
    # Adaptar as abas
    tab1, tab2, tab3, tab4 = st.tabs([
        "Classificação (por Item)", # Renomeado
        "Anomalias", 
        "Fornecedores",
        "Previsão"
    ])
    
    # TAB 1: Classificação (Classificação manual removida, agora focada em itens)
    with tab1:
        st.markdown("### Classificação Detalhada de Despesas por Item")
        
        if 'itens_nf' in df.columns:
            # Chama a nova função que processa a classificação por item
            processar_e_exibir_classificacao_por_item(df)
        else:
            st.error("A coluna 'itens_nf' não foi encontrada no DataFrame. Por favor, certifique-se de que a função 'extrair_capa_de_pdf' do seu extrator foi atualizada para extrair os itens.")
    # TAB 2: Anomalias
    with tab2:
        st.markdown("### Detecção de Anomalias")
        
        if not df.empty and 'valor_total_num' in df.columns:
            # Converter para lista de floats
            valores_raw = df['valor_total_num'].dropna().tolist()
            valores = [float(v) for v in valores_raw if v is not None]
            
            if len(valores) > 5:
                resultado = detect_anomalies(valores)
                
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.metric("Total de NFs", len(valores))
                with col2:
                    st.metric("Anomalias", resultado.get('total_anomalias', 0))
                with col3:
                    st.metric("Valor Médio", f"R$ {resultado.get('valor_medio', 0):.2f}")
                
                anomalias = resultado.get('anomalias', [])
                if anomalias:
                    st.warning("🚨 Anomalias Detectadas:")
                    for anom in anomalias:
                        st.error(
                            f"Índice #{anom.get('indice', 'N/A')}: "
                            f"R$ {anom.get('valor', 0):.2f} "
                            f"({anom.get('desvio_percentual', 0):+.1f}% do padrão)"
                        )
                else:
                    st.success("✅ Nenhuma anomalia detectada")
            else:
                st.info("Envie mais NFs para detectar anomalias")
    
    # TAB 3: Análise de Fornecedores
    with tab3:
        st.markdown("### Análise de Risco de Fornecedores")
        
        if not df.empty and 'emitente_nome' in df.columns:
            fornecedores_lista = df['emitente_nome'].unique()
            fornecedores = [str(f) for f in fornecedores_lista if f is not None]
            
            if fornecedores:
                fornecedor_selecionado = st.selectbox(
                    "Selecione fornecedor:",
                    fornecedores
                )
                
                # Preparar dados de histórico
                df_fornecedor = df[df['emitente_nome'] == fornecedor_selecionado]
                nfs_fornecedor = df_fornecedor.to_dict('records')
                
                # Adicionar campos de exemplo
                for nf in nfs_fornecedor:
                    nf['fornecedor'] = str(nf.get('emitente_nome', ''))
                    nf['valor'] = float(nf.get('valor_total_num', 0)) if nf.get('valor_total_num') is not None else 0.0
                    nf['atrasada'] = False  # Você pode adicionar lógica real
                
                resultado = analyze_supplier_risk(fornecedor_selecionado, nfs_fornecedor)
                
                if resultado['status'] == 'OK':
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.metric("Risco", resultado.get('risco', 'Desconhecido'))
                    
                    with col2:
                        st.metric("Score", f"{resultado.get('score', 0)}/10")
                    
                    with col3:
                        st.metric("Total de NFs", resultado.get('total_nfs', 0))
                    
                    motivos = resultado.get('motivos', [])
                    if motivos:
                        st.markdown("**Motivos do Risco:**")
                        for motivo in motivos:
                            st.caption(f"• {motivo}")
    
    # TAB 4: Previsão
    with tab4:
        st.markdown("### Previsão de Valores")
        
        if not df.empty and 'valor_total_num' in df.columns:
            valores_raw = df['valor_total_num'].dropna().tolist()
            valores = [float(v) for v in valores_raw if v is not None]
            
            if len(valores) > 3:
                periodos = st.slider("Próximos períodos:", 7, 60, 30)
                
                resultado = simple_forecast(valores, periods=periodos)
                
                if resultado['status'] == 'OK':
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.info(f"**Tendência:** {resultado.get('tendencia', 'Desconhecido')}")
                        st.metric(
                            "Valor Médio Previsto",
                            f"R$ {resultado.get('valor_medio_previsto', 0):.2f}"
                        )
                    
                    with col2:
                        st.info(
                            f"**Confiabilidade:** {resultado.get('confiabilidade', '0%')}"
                        )
                    
                    # Gráfico de previsão
                    try:
                        import plotly.graph_objects as go
                        
                        proximos = resultado.get('proximos_periodos', [])
                        
                        fig = go.Figure()
                        
                        # Histórico (últimos 30)
                        historico = valores[-30:] if len(valores) > 30 else valores
                        fig.add_trace(go.Scatter(
                            y=historico,
                            name="Histórico",
                            mode='lines',
                            line=dict(color='blue')
                        ))
                        
                        # Previsão
                        if proximos:
                            fig.add_trace(go.Scatter(
                                y=proximos,
                                name="Previsão",
                                mode='lines+markers',
                                line=dict(color='red', dash='dash')
                            ))
                        
                        fig.update_layout(
                            title="Previsão de Valores",
                            xaxis_title="Período",
                            yaxis_title="Valor (R$)",
                            height=400
                        )
                        
                        st.plotly_chart(fig, use_container_width=True)
                    
                    except Exception as e:
                        st.error(f"Erro ao gerar gráfico: {str(e)}")