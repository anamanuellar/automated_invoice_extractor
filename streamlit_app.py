import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
import tempfile
import os
import gc
from typing import Optional
from extrator import processar_pdfs, exportar_para_excel_com_itens
from extrator_ia_itens_impostos import ExtractorIA

# ✨ PDF é opcional - apenas para exportação
PDF_DISPONIVEL = False
try:
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
    PDF_DISPONIVEL = True
except ImportError:
    pass

# ✨ Análise fiscal é opcional
ANALISE_DISPONIVEL = False
try:
    from analise_fiscal_financeira import gerar_analise_completa as gerar_analise_financeira_completa
    ANALISE_DISPONIVEL = True
except ImportError:
    gerar_analise_financeira_completa = None

# ========================= LIMPEZA DE MEMÓRIA =========================
def limpar_cache():
    gc.collect()
    st.cache_data.clear()

# ========================= GERAÇÃO DE PDF COM MÚLTIPLAS PÁGINAS =========================
def gerar_pdf_completo(df: pd.DataFrame, regime: str, analise: str) -> Optional[bytes]:
    """Gera PDF com múltiplas páginas para análise completa"""
    if not PDF_DISPONIVEL:
        return None
    
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
        from io import BytesIO
        
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
        story = []
        styles = getSampleStyleSheet()
        
        # Criar estilo customizado para análise
        analise_style = ParagraphStyle(
            'Analise',
            parent=styles['Normal'],
            fontSize=10,
            leading=14,
            color='#333333'
        )
        
        # Extrair nome do destinatário
        nome_empresa = "EMPRESA"
        if "dest_nome" in df.columns and len(df) > 0:
            dest_nome = df["dest_nome"].iloc[0]
            if pd.notna(dest_nome) and str(dest_nome).strip():
                nome_empresa = str(dest_nome).upper()
        
        # PÁGINA 1: Cabeçalho
        story.append(Paragraph("📊 ANÁLISE FISCAL E FINANCEIRA COMPLETA", styles['Heading1']))
        story.append(Paragraph(nome_empresa, styles['Heading2']))
        story.append(Spacer(1, 0.3*inch))
        
        story.append(Paragraph(f"<b>Regime Tributário:</b> {regime}", styles['Normal']))
        story.append(Paragraph(f"<b>Data do Relatório:</b> {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", styles['Normal']))
        story.append(Paragraph(f"<b>Total de Notas Fiscais:</b> {len(df)}", styles['Normal']))
        story.append(Spacer(1, 0.3*inch))
        
        # Quebrar análise em linhas e adicionar com quebra de página automática
        linhas_analise = analise.split('\n')
        
        # Adicionar linhas com controle de página
        linhas_por_pagina = 0
        max_linhas_pagina = 50  # Aproximadamente 50 linhas por página
        
        story.append(Paragraph("ANÁLISE DETALHADA", styles['Heading2']))
        story.append(Spacer(1, 0.2*inch))
        
        for i, linha in enumerate(linhas_analise):
            if linha.strip():
                # Adicionar quebra de página a cada ~50 linhas
                if linhas_por_pagina >= max_linhas_pagina:
                    story.append(PageBreak())
                    linhas_por_pagina = 0
                
                # Limpar HTML e escapar caracteres especiais
                texto_limpo = linha.replace('<', '&lt;').replace('>', '&gt;')[:200]
                
                # Determinar se é seção (em branco antes) ou linha normal
                if texto_limpo.startswith('='):
                    story.append(Spacer(1, 0.1*inch))
                    story.append(Paragraph(f"<b>{texto_limpo}</b>", styles['Normal']))
                    story.append(Spacer(1, 0.1*inch))
                elif texto_limpo.startswith('•') or texto_limpo.startswith('☑'):
                    story.append(Paragraph(f"  {texto_limpo}", analise_style))
                elif ':' in texto_limpo and len(texto_limpo) < 80:
                    story.append(Paragraph(f"<b>{texto_limpo}</b>", styles['Normal']))
                else:
                    story.append(Paragraph(texto_limpo, analise_style))
                
                linhas_por_pagina += 1
        
        # Página final: Rodapé
        story.append(Spacer(1, 0.5*inch))
        story.append(Paragraph("---", styles['Normal']))
        story.append(Spacer(1, 0.2*inch))
        story.append(Paragraph(
            f"Relatório gerado automaticamente em {datetime.now().strftime('%d/%m/%Y às %H:%M:%S')}", 
            styles['Normal']
        ))
        story.append(Paragraph("Extrator Inteligente de Notas Fiscais v2.4", styles['Normal']))
        
        # Construir PDF
        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()
        
    except Exception as e:
        st.error(f"Erro ao gerar PDF: {e}")
        return None

# ========================= CONFIGURAÇÃO BÁSICA =========================
st.set_page_config(
    page_title="🔖 Extrator Inteligente de Notas Fiscais",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .main { padding: 1.5rem; }
    h1, h2, h3 { color: #1f77b4; }
    .grafico-container {
        background-color: #f8f9fa;
        padding: 1.5rem;
        border-radius: 8px;
        margin: 1rem 0;
        border-left: 4px solid #1f77b4;
    }
</style>
""", unsafe_allow_html=True)

# ========================= CABEÇALHO =========================
st.title("🔖 Extrator Inteligente de Notas Fiscais")
st.caption("Extraia informações de DANFEs em PDF, analise valores e exporte seus resultados.")
st.divider()

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Status", "🟢 Pronto", help="Sistema operacional OK")
with col2:
    st.metric("Versão", "2.4", help="Versão otimizada")
with col3:
    st.metric("IA Integrada", "✅ Ativa", help="Suporte a Gemini, OpenAI e HuggingFace")

st.divider()

# ========================= SIDEBAR =========================
with st.sidebar:
    st.header("⚙️ Configurações")
    
    enriquecer_cnpj = st.toggle("Enriquecer dados via CNPJ", value=True)
    enriquecer_fiscal = st.toggle("Enriquecer com Análise Fiscal", value=True)
    usar_ia = st.toggle("Ativar Análise com IA", value=True)
    api_key_ia = st.text_input("🔐 Chave de API (Gemini ou OpenAI)", type="password")
    
    if st.button("🧹 Limpar Cache/Memória", use_container_width=True):
        limpar_cache()
        st.success("✅ Cache e memória limpos!")
        st.rerun()

    st.markdown("---")
    st.subheader("ℹ️ Sobre")
    st.markdown("""
    **Funcionalidades:**
    - 📄 Extração automática de DANFEs
    - 📊 Análise fiscal + financeira
    - 📈 Gráficos interativos
    - 📥 Exportação Excel/CSV
    - 🤖 IA integrada
    - 📄 PDF com análise
    """)

# ========================= UPLOAD DE ARQUIVOS =========================
st.subheader("📤 Envie seus arquivos PDF de DANFE")
uploaded_files = st.file_uploader("Selecione um ou mais PDFs", type=["pdf"], accept_multiple_files=True)

if uploaded_files:
    temp_dir = tempfile.mkdtemp()
    pdf_paths = []

    for f in uploaded_files:
        path = os.path.join(temp_dir, f.name)
        with open(path, "wb") as out:
            out.write(f.getbuffer())
        pdf_paths.append(path)

    st.info("⏳ Processando arquivos...")
    
    df_result_ia = processar_pdfs(pdf_paths, api_key_gemini=api_key_ia if usar_ia else None)

    if not df_result_ia.empty:
        st.success(f"✅ {len(df_result_ia)} notas fiscais processadas!")
        st.divider()

        # ========================= TABELA =========================
        st.markdown("### 📋 Dados extraídos")
        colunas_visiveis = ["arquivo", "numero_nf", "serie", "data_emissao", "emitente_nome", "dest_nome", "valor_total", "status"]
        df_view = df_result_ia[[c for c in colunas_visiveis if c in df_result_ia.columns]]
        st.dataframe(df_view, use_container_width=True, height=450)

        # ========================= EXPORTAÇÕES =========================
        st.divider()
        st.subheader("📥 Exportar dados (Excel e CSV)")

        col1, col2 = st.columns(2)
        
        with col1:
            st.download_button(
                label="💾 Exportar para Excel",
                data=exportar_para_excel_com_itens(df_result_ia),
                file_name=f"notas_fiscais_{datetime.now():%Y%m%d_%H%M%S}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        
        with col2:
            st.download_button(
                label="📄 Exportar para CSV",
                data=df_result_ia.to_csv(index=False).encode("utf-8"),
                file_name=f"notas_fiscais_{datetime.now():%Y%m%d_%H%M%S}.csv",
                mime="text/csv",
                use_container_width=True,
            )

        # ========================= GRÁFICOS =========================
        st.divider()
        st.markdown("### 📊 Análises Gráficas")

        df_result_ia["valor_total_num"] = pd.to_numeric(df_result_ia.get("valor_total_num", 0), errors="coerce")

        # Gráfico 1
        st.markdown('<div class="grafico-container">', unsafe_allow_html=True)
        st.subheader("📈 Top 5 Emitentes")
        
        if "emitente_nome" in df_result_ia.columns:
            top_emit = df_result_ia.groupby("emitente_nome")["valor_total_num"].sum().nlargest(5).reset_index()
            top_emit.columns = ["Emitente", "Valor"]
            
            fig1 = px.bar(top_emit, x="Emitente", y="Valor", color_discrete_sequence=["#1f77b4"])
            fig1.update_layout(height=400, showlegend=False)
            st.plotly_chart(fig1, use_container_width=True)
        
        st.markdown('</div>', unsafe_allow_html=True)

        # Gráfico 2
        st.markdown('<div class="grafico-container">', unsafe_allow_html=True)
        st.subheader("📅 Tendência Mensal")
        
        if "data_emissao" in df_result_ia.columns:
            df_result_ia["data_emissao"] = pd.to_datetime(df_result_ia["data_emissao"], errors="coerce")
            trend = df_result_ia.groupby(df_result_ia["data_emissao"].dt.to_period("M"))["valor_total_num"].sum().reset_index()
            trend["data_emissao"] = trend["data_emissao"].astype(str)
            trend.columns = ["Período", "Valor"]
            
            fig2 = px.line(trend, x="Período", y="Valor", markers=True, color_discrete_sequence=["#2ca02c"])
            fig2.update_layout(height=400, showlegend=False)
            st.plotly_chart(fig2, use_container_width=True)
        
        st.markdown('</div>', unsafe_allow_html=True)

        # Gráfico 3
        st.markdown('<div class="grafico-container">', unsafe_allow_html=True)
        st.subheader("🥧 Distribuição")
        
        if "emitente_nome" in df_result_ia.columns:
            dist = df_result_ia.groupby("emitente_nome")["valor_total_num"].sum().reset_index()
            dist.columns = ["Fornecedor", "Valor"]
            
            fig3 = px.pie(dist, values="Valor", names="Fornecedor")
            fig3.update_layout(height=450)
            st.plotly_chart(fig3, use_container_width=True)
        
        st.markdown('</div>', unsafe_allow_html=True)

        # Gráfico 4
        st.markdown('<div class="grafico-container">', unsafe_allow_html=True)
        st.subheader("📦 Quantidade de NFs")
        
        if "emitente_nome" in df_result_ia.columns:
            qty = df_result_ia.groupby("emitente_nome").size().reset_index(name="Quantidade").sort_values("Quantidade", ascending=True)
            qty.columns = ["Emitente", "Quantidade"]
            
            fig4 = px.bar(qty, x="Quantidade", y="Emitente", orientation="h", color_discrete_sequence=["#ff7f0e"])
            fig4.update_layout(height=400, showlegend=False)
            st.plotly_chart(fig4, use_container_width=True)
        
        st.markdown('</div>', unsafe_allow_html=True)

        # ========================= ANÁLISE FISCAL =========================
        st.divider()
        st.subheader("📊 Análise Fiscal + Financeira")
        
        # Seleção do regime tributário
        regime = st.selectbox(
            "Regime tributário da empresa:",
            ["Simples Nacional", "Lucro Real", "Lucro Presumido", "IE Ativa", "IE Isenta"],
            help="Selecione o regime tributário da sua empresa (destinatária)"
        )
        
        # Seleção de IE (Isenta ou Ativa)
        st.markdown("**Qual é a situação da sua Inscrição Estadual (IE)?**")
        
        ie_status = st.radio(
            "Selecione:",
            ["IE Isenta", "IE Ativa"],
            horizontal=True,
            help="IE Isenta: Não precisa pagar ICMS. IE Ativa: Pode aproveitar créditos de ICMS"
        )
        
        # Explicação do impacto
        if "isent" in ie_status.lower():
            st.info("""
            🎯 **IE ISENTA - CFOPs Corretos:**
            - **5.949**: Compra com IE isenta (operação isenta) - ✅ CORRETO
            - **5.102**: Compra tributada - ❌ INCORRETO
            
            Se usar CFOP 5.102, você será tributado e não poderá recuperar ICMS.
            """)
        else:
            st.info("""
            🎯 **IE ATIVA - CFOPs Corretos:**
            - **5.102**: Compra tributada (normal) - ✅ CORRETO
            - **5.101**: Compra com ST (Substituição Tributária)
            - **5.949**: Compra isenta
            
            Com IE ativa, você pode aproveitar créditos de ICMS nas operações tributadas.
            """)
        
        if st.button("Gerar Análise Fiscal 📈", use_container_width=True):
            if ANALISE_DISPONIVEL and gerar_analise_financeira_completa is not None:
                with st.spinner("⏳ Gerando análise personalizada..."):
                    # Passar regime e status de IE
                    analise = gerar_analise_financeira_completa(df_result_ia, regime, ie_status)
                    st.markdown("### 📊 Resultado da Análise:")
                    st.text(analise)
                    
                    st.session_state['analise'] = analise
                    st.session_state['regime'] = regime
                    st.session_state['ie_status'] = ie_status
            else:
                st.warning("Módulo de análise não disponível")

        # ========================= ANÁLISE COMPLETA COM IA =========================
        st.divider()
        st.subheader("🤖 Análise Completa com IA")

        st.markdown("""
        Gere insights automáticos sobre as notas fiscais, com foco em:
        - **Padrões de fornecedores** e concentração de compras
        - **Tendências de valores** e sazonalidade
        - **Possíveis anomalias fiscais** e riscos
        - **Recomendações** de otimização
        """)

        if st.button("Executar análise completa com IA 🚀", use_container_width=True):
            st.info("🧠 Analisando dados via IA... (pode levar alguns segundos)")

            try:
                # Importar o ExtractorIA
                from extrator_ia_itens_impostos import ExtractorIA
                
                # Tentar obter API key do session state ou variáveis de ambiente
                api_key_ia = st.session_state.get('api_key_ia', '')
                
                if not api_key_ia:
                    # Tentar ler de variáveis de ambiente
                    api_key_ia = os.getenv('GOOGLE_API_KEY', '')
                
                if api_key_ia:
                    with st.spinner("⏳ Processando com IA..."):
                        model = ExtractorIA(api_key_ia)
                        
                        # Preparar dados para análise
                        dados_resumo = f"""
RESUMO DOS DADOS DE NOTAS FISCAIS:

Total de NFs: {len(df_result_ia)}
Valor Total: R$ {df_result_ia['valor_total_num'].sum():,.2f}
Valor Médio: R$ {df_result_ia['valor_total_num'].mean():,.2f}

PRINCIPAIS FORNECEDORES:
"""
                        top_fornecedores = df_result_ia.groupby("emitente_nome")["valor_total_num"].sum().nlargest(5)
                        for i, (fornecedor, valor) in enumerate(top_fornecedores.items(), 1):
                            dados_resumo += f"{i}. {fornecedor}: R$ {valor:,.2f}\n"
                        
                        dados_resumo += f"""

AMOSTRA DOS DADOS:
{df_result_ia.head(10).to_string(index=False)}

Por favor, forneça uma análise executiva focando em:
1. Padrões e tendências identificados
2. Riscos fiscais potenciais
3. Oportunidades de otimização
4. Recomendações acionáveis
"""
                        
                        # Chamar IA
                        resultado = model.analisar_texto(dados_resumo)
                        
                        st.markdown("### 💡 Resultado da Análise com IA:")
                        st.markdown(resultado)
                        
                        st.session_state['analise_ia'] = resultado
                else:
                    st.warning("""
                    ⚠️ Chave de API não configurada.
                    
                    Para usar a análise com IA, configure sua API key:
                    1. Defina a variável de ambiente `GOOGLE_API_KEY`
                    2. Ou insira na barra lateral em Configurações
                    """)
            except ImportError:
                st.warning("Módulo ExtractorIA não disponível. Verifique a instalação.")
            except Exception as e:
                st.error(f"Erro ao executar análise de IA: {e}")

        # ========================= PDF (NO FINAL) =========================
        st.divider()
        st.subheader("📄 Exportar Relatório em PDF")
        
        if 'analise' in st.session_state and PDF_DISPONIVEL:
            if st.button("🔴 Gerar PDF", use_container_width=True):
                with st.spinner("⏳ Gerando PDF com múltiplas páginas..."):
                    pdf_data = gerar_pdf_completo(df_result_ia, st.session_state['regime'], st.session_state['analise'])
                    if pdf_data:
                        st.download_button(
                            label="📥 Baixar PDF Completo",
                            data=pdf_data,
                            file_name=f"analise_fiscal_{datetime.now():%Y%m%d_%H%M%S}.pdf",
                            mime="application/pdf",
                            use_container_width=True,
                        )
                        st.success("✅ PDF gerado com sucesso!")
        elif 'analise' not in st.session_state:
            st.info("💡 Gere a análise fiscal acima primeiro")
        elif not PDF_DISPONIVEL:
            st.info("ℹ️ Instale reportlab: pip install reportlab")

    else:
        st.warning("Nenhuma nota fiscal processada")
else:
    st.info("👆 Envie PDFs para começar")

# ========================= RODAPÉ =========================
st.markdown("""
---
<div style="text-align:center; color:gray; font-size:13px;">
💼 Extrator de Notas Fiscais v2.4 – Desenvolvido com ❤️<br>
🚀 Com análise fiscal avançada e exportação em Excel/CSV/PDF
</div>
""", unsafe_allow_html=True)