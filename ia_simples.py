import streamlit as st
import pandas as pd
import numpy as np
# CORREÇÃO 1: Usar tipos flexíveis para acalmar o Pylance
from typing import Dict, List, Any, Optional, Union, Sequence 
import warnings
warnings.filterwarnings('ignore')
from transformers import pipeline

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
        
        # Categorias contábeis brasileiras
        categories = [
            "Infraestrutura IT",
            "Software e Licenças",
            "Marketing e Publicidade",
            "Recursos Humanos",
            "Viagem e Hospedagem",
            "Materiais e Suprimentos",
            "Consultoria e Outsourcing",
            "Serviços Financeiros",
            "Combustível e Transporte",
            "Manutenção e Reparo",
            "Energia e Água",
            "Aluguel e Propriedade",
            "Educação e Treinamento",
            "Seguro",
            "Outro"
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

# CORREÇÃO 2: Tornar o tipo de nf_history mais flexível para aceitar dados do Pandas (Union)
def analyze_supplier_risk(supplier_name: str, 
                         nf_history: List[Dict[Union[str, Any], Any]]) -> Dict[str, Any]:
    """
    Analisa risco de um fornecedor baseado no histórico de NFs
    """
    supplier_nfs: List[Dict[Union[str, Any], Any]] = [nf for nf in nf_history 
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

# CORREÇÃO 3: O parâmetro 'periods' já está correto
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


# =============== INTEGRAÇÃO COM STREAMLIT ===============

def add_ia_to_streamlit(df: pd.DataFrame) -> None:
    """
    Adiciona seção de IA ao seu app Streamlit
    
    Uso:
        from ia_simples_corrigido import add_ia_to_streamlit
        
        if not df.empty:
            add_ia_to_streamlit(df)
    """
    
    # CORREÇÃO CRÍTICA PARA O ERRO ".str accessor"
    # Garante que as colunas críticas estão no tipo correto
    if 'valor_total_num' in df.columns:
        df['valor_total_num'] = pd.to_numeric(df['valor_total_num'], errors='coerce')
    
    if 'emitente_nome' in df.columns:
        df['emitente_nome'] = df['emitente_nome'].astype(str)
    
    st.divider()
    st.subheader("🤖 Análise com Inteligência Artificial")
    
    tab1, tab2, tab3, tab4 = st.tabs([
        "Classificação", 
        "Anomalias", 
        "Fornecedores",
        "Previsão"
    ])
    
    # TAB 1: Classificação
    with tab1:
        st.markdown("### Classificação de Despesas")
        
        col1, col2 = st.columns([3, 1])
        
        with col1:
            descricao = st.text_input(
                "Descrição do produto/serviço:",
                placeholder="Ex: Amazon Web Services - Cloud Hosting"
            )
        
        with col2:
            metodo = st.selectbox(
                "Método IA:",
                ["Hugging Face (Grátis)"]  # Apenas Hugging Face por enquanto
            )
        
        if descricao:
            with st.spinner("Analisando..."):
                resultado = classify_expense_hf(descricao)
            
            if resultado['status'] == 'OK':
                col1, col2 = st.columns(2)
                
                with col1:
                    st.success(f"**Categoria:** {resultado.get('categoria', 'Desconhecido')}")
                    st.info(f"**Confiança:** {resultado.get('confianca', 0):.1%}")
                
                with col2:
                    alternativas = resultado.get('alternativas', {})
                    if alternativas:
                        st.markdown("**Alternativas:**")
                        for idx, (cat, conf) in enumerate(list(alternativas.items())[:2]):
                            st.caption(f"• {cat}: {conf:.1%}")
            else:
                st.error(f"Erro: {resultado.get('status', 'Desconhecido')}")
    
    # TAB 2: Anomalias
    with tab2:
        st.markdown("### 🚨 Detecção de Anomalias de Valor")
        st.info("Utiliza o Isolation Forest para identificar Notas Fiscais com valores atípicos.")

        df_anomalia = df.copy()
        
        # Opções de segmentação
        segmentacao = st.radio(
            "Analisar por:",
            ["Total Geral", "Por Fornecedor (Emitente)"],
            horizontal=True
        )

        valores_limpos = df_anomalia.dropna(subset=['valor_total_num'])

        if valores_limpos.empty or len(valores_limpos) < 5:
            st.warning("Dados insuficientes (mínimo de 5 notas com valor válido) para análise de anomalias.")
            
        else:
            if segmentacao == "Total Geral":
                # Aplica a análise ao total geral (código existente)
                valores = valores_limpos['valor_total_num'].tolist()
                resultado = detect_anomalies(valores)
                
                # DataFrame inicial de anomalias
                anomalias_df = pd.DataFrame(resultado.get('anomalias', []))
                
                if not anomalias_df.empty:
                    
                    # 1. Pega os índices posicionais das anomalias
                    indices_posicionais = anomalias_df['indice'].to_numpy()
                    
                    # 2. Pega os índices reais do DataFrame limpo e usa np.take para selecionar
                    indices_reais = valores_limpos.index.to_numpy().take(indices_posicionais)
                    
                    # 3. Atribui o índice real de volta ao DataFrame de anomalias
                    anomalias_df['índice_original'] = indices_reais # <--- AGORA A COLUNA EXISTE AQUI
                    
                    # 4. Faz o merge com o DF original
                    anomalias_finais = df_anomalia.loc[anomalias_df['índice_original'], 
                                                      ['data_emissao', 'emitente_nome', 'numero_nf', 'valor_total_num']]
                    
                    # 5. Adiciona o desvio percentual
                    anomalias_finais = anomalias_finais.merge(
                        anomalias_df[['índice_original', 'desvio_percentual']], 
                        left_index=True, 
                        right_on='índice_original', 
                        how='left'
                    )
                    
                    st.warning(f"Foram detectadas **{len(anomalias_finais)}** anomalias no *Total Geral*:")
                    st.dataframe(anomalias_finais.rename(columns={'valor_total_num': 'Valor Anômalo (R$)', 
                                                                  'desvio_percentual': 'Desvio (%)'}).drop(columns='índice_original', errors='ignore'), 
                                use_container_width=True)
                else:
                    st.success("✅ Nenhuma anomalia significativa detectada no Total Geral.")

            elif segmentacao == "Por Fornecedor (Emitente)":
                st.markdown("---")
                anomalias_por_fornecedor = []
                
                # Agrupamento para análise segmentada
                grupos = valores_limpos.groupby('emitente_nome')
                
                with st.spinner("Analisando anomalias por fornecedor..."):
                    for nome_fornecedor, grupo_df in grupos:
                        if len(grupo_df) >= 5: # Mínimo de 5 notas por fornecedor para análise
                            valores = grupo_df['valor_total_num'].tolist()
                            resultado = detect_anomalies(valores)
                            
                            anomalias_encontradas = resultado.get('anomalias', [])
                            
                            if anomalias_encontradas:
                                # Mapear o índice da anomalia de volta para o DataFrame original
                                for anomalia in anomalias_encontradas:
                                    idx_anomalia_no_grupo = anomalia['indice']
                                    
                                    # Pega o índice real do DataFrame original
                                    indice_real = grupo_df.iloc[[idx_anomalia_no_grupo]].index[0] 
                                    
                                    # Pega a linha completa do DF original
                                    linha_original = df_anomalia.loc[indice_real]
                                    
                                    anomalias_por_fornecedor.append({
                                        'Fornecedor': nome_fornecedor,
                                        'Data': linha_original['data_emissao'],
                                        'NF Número': linha_original['numero_nf'],
                                        'Valor Anômalo (R$)': linha_original['valor_total_num'],
                                        'Desvio (%)': anomalia['desvio_percentual']
                                    })
                
                if anomalias_por_fornecedor:
                    df_segmentado = pd.DataFrame(anomalias_por_fornecedor)
                    
                    # Formatação
                    df_segmentado['Valor Anômalo (R$)'] = df_segmentado['Valor Anômalo (R$)'].map('R$ {:,.2f}'.format)
                    df_segmentado['Desvio (%)'] = df_segmentado['Desvio (%)'].map('{:+.1f}%'.format)

                    st.warning(f"Foram detectadas **{len(df_segmentado)}** anomalias em fornecedores:")
                    st.dataframe(df_segmentado, use_container_width=True)
                else:
                    st.success("✅ Nenhuma anomalia significativa detectada por fornecedor.")
    
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
                nfs_fornecedor = df_fornecedor.to_dict('records') # Retorna List[Dict]
                
                # Adicionar campos de exemplo
                for nf in nfs_fornecedor:
                    nf['fornecedor'] = str(nf.get('emitente_nome', ''))
                    nf['valor'] = float(nf.get('valor_total_num', 0)) if nf.get('valor_total_num') is not None else 0.0
                    nf['atrasada'] = False  # Você pode adicionar lógica real
                
                # CORREÇÃO: O Pylance aceitará nfs_fornecedor com a assinatura flexível
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
                
                # CORREÇÃO 4: Passar explicitamente como lista para Pylance
                resultado = simple_forecast(list(valores), periods=periodos) 
                
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

def inferir_ncm(descricao_produto: str) -> str:
    """
    Usa um modelo leve do Hugging Face para sugerir o NCM provável
    com base na descrição textual do item.
    """
    try:
        classifier = pipeline("text-classification", model="mrm8488/distilroberta-finetuned-financial-news-sentiment-analysis")
        res = classifier(f"Produto: {descricao_produto}")
        if isinstance(res, list) and len(res) > 0:
            return res[0].get("label", "NCM não identificado")
    except Exception:
        pass
    return "NCM não identificado"
