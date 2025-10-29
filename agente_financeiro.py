import streamlit as st
import os
from typing import Dict, Any
from ia_simples import classify_expense_hf

try:
    import google.generativeai as genai
    # Tentativa de inicializar o cliente diretamente, que é a forma moderna
    from google.genai.client import Client as GeminiClient
except ImportError:
    # Se a importação falhar (biblioteca não instalada ou versão antiga)
    genai = None
    GeminiClient = None

def get_model_provider() -> str:
    """
    Permite escolher o provedor de IA e inserir chave de API.
    HuggingFace é o padrão gratuito.
    """
    st.markdown("### 🧠 Escolha o modelo de IA")

    provider = st.selectbox(
        "Provedor de IA:",
        ["Hugging Face (Grátis)", "OpenAI", "Gemini (Google AI Studio)"]
    )

    token = None
    if provider != "Hugging Face (Grátis)":
        token = st.text_input("🔑 Insira sua API Key:", type="password")
        if token:
            os.environ["USER_AI_TOKEN"] = token
    
    return provider


def analisar_contexto_ia(df, provider: str):
    """
    Interpreta os resultados financeiros e fiscais com IA generativa.
    """
    if df.empty:
        st.warning("Nenhum dado disponível para análise.")
        return

    st.markdown("### 💬 Análise Explicativa de IA")

    if provider == "Hugging Face (Grátis)":
        st.info("Usando HuggingFace — modo local sem custos.")
        resumo = f"""
        O conjunto contém {len(df)} notas fiscais,
        com valor médio de R$ {df['valor_total_num'].mean():,.2f}.
        O modelo gratuito não faz interpretação textual,
        mas você pode usar as abas de classificação e risco.
        """
        st.write(resumo)

    elif provider == "OpenAI":
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("USER_AI_TOKEN", ""))

        if not client.api_key:
            st.warning("Insira sua chave da OpenAI acima.")
            return

        prompt = f"""
        Faça uma análise resumida e inteligente sobre as notas fiscais abaixo.
        Enfatize possíveis riscos, fornecedores críticos e oportunidades de economia.
        Dados: {df.head(10).to_dict(orient='records')}
        """
        with st.spinner("Gerando análise com OpenAI..."):
            response = client.chat.completions.create(
                model="gpt-4-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=400
            )
            st.success("Análise gerada com sucesso!")
            st.write(response.choices[0].message.content)

    elif provider == "Gemini (Google AI Studio)":
            
            # 1. Checagem de Importação
            if not genai or not GeminiClient:
                st.error("❌ A biblioteca 'google-genai' não está instalada ou está desatualizada. Execute:\n\npip install -U google-genai")
                return

            # 2. Busca da Chave
            api_key = st.session_state.get('ia_api_key', '') 
            
            if not api_key:
                st.warning("Insira sua chave da API Gemini na barra lateral para continuar.")
                return

            try:
                st.info("🔄 Gerando análise com o modelo Gemini (1.5-flash)...")
                
                # 3. INICIALIZAÇÃO CORRETA: Cria o objeto cliente autenticado
                client = GeminiClient(api_key=api_key) # Usa o nome 'GeminiClient' para evitar o aviso do Pylance
                
                prompt = f"""
                Faça uma análise financeira detalhada com base nas notas fiscais abaixo:
                {df.head(10).to_dict(orient='records')}
                Identifique:
                - Padrões de gastos;
                - Riscos e inconsistências fiscais;
                - Oportunidades de economia;
                - Possíveis anomalias de CFOP, CST ou tributação.
                """
                
                # 4. CHAMADA DE CONTEÚDO: Chama o modelo através do objeto client
                # Esta é a sintaxe recomendada pelo SDK moderno
                result = client.models.generate_content(
                    model="gemini-1.5-flash",
                    contents=prompt
                )

                st.success("✅ Análise concluída com sucesso!")
                st.markdown(result.text)

            except Exception as e:
                st.error(f"❌ Erro ao executar análise com Gemini: {e}")
                st.error("Dica: Verifique se a chave da API está correta e se o modelo 'gemini-1.5-flash' está habilitado para sua conta.")