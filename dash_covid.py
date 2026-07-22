import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from snowflake.snowpark import Session
from datetime import datetime

st.set_page_config(page_title="Covid Dashboard", layout="wide")

st.title("Dashboard COVID - Análise de Dados da Pandemia de 2020 a 2022 📊")

# Credenciais carregadas do .streamlit/secrets.toml (nunca hardcoded no código)
connection_parameters = {
    "user": st.secrets["snowflake"]["user"],
    "password": st.secrets["snowflake"]["password"],
    "account": st.secrets["snowflake"]["account"],
    "warehouse": st.secrets["snowflake"]["warehouse"],
    "database": "TEST_DB",
    "schema": "PUBLIC",
    "role": st.secrets["snowflake"]["role"]
}

url = "https://raw.githubusercontent.com/owid/covid-19-data/master/public/data/owid-covid-data.csv"

st.sidebar.header("Controles")

if st.sidebar.button("🔄 Carregar/Atualizar Dados no Snowflake"):
    try:
        with st.spinner("Baixando dados ..."):
            df = pd.read_csv(url)
            paises = ['Brazil', 'United States','Italy', 'Spain', 'Germany', 'South Africa', 'Japan']
            df = df[df['location'].isin(paises)]
            df = df[df['date'] >= '2020-01-01']
            df = df[df['date'] <= '2022-12-31']
            st.sidebar.success(f"✅ {df.shape[0]} linhas baixadas")

        with st.spinner("Enviando para Snowflake..."):
            session = Session.builder.configs(connection_parameters).create()
            session.sql("CREATE DATABASE IF NOT EXISTS TEST_DB").collect()
            session.sql("USE DATABASE TEST_DB").collect()
            session.sql("USE SCHEMA PUBLIC").collect()
            session.write_pandas(df, "TB_COVID_FILTRADO", auto_create_table=True, overwrite=True)
            session.close()
            st.sidebar.success("✅ Dados atualizados no Snowflake!")
            st.balloons()
    except Exception as e:
        st.sidebar.error(f"❌ Erro: {e}")

if st.sidebar.button("📊 Carregar Dashboard"):
    try:
        with st.spinner("Conectando ao Snowflake..."):
            session = Session.builder.configs(connection_parameters).create()
            session.sql("USE DATABASE TEST_DB").collect()
            session.sql("USE SCHEMA PUBLIC").collect()

            df = session.table("TB_COVID_FILTRADO").to_pandas()
            session.close()

            # Normalizar nomes das colunas (converter para minúsculas)
            df.columns = df.columns.str.lower()

            # Converter colunas de data
            date_cols = [col for col in df.columns if 'timestamp' in col or 'date' in col]
            for col in date_cols:
                df[col] = pd.to_datetime(df[col], errors='coerce')

            st.session_state['df'] = df
            st.sidebar.success(f"✅ {len(df)} pedidos carregados")

    except Exception as e:
        st.sidebar.error(f"❌ Erro ao carregar: {e}")
        st.sidebar.error(f"Detalhes: {str(e)}")
        st.sidebar.info("💡 Se a tabela não existe ainda, clique primeiro em 'Carregar/Atualizar Dados no Snowflake'")

if 'df' in st.session_state:
    df = st.session_state['df']

    # DEBUG: Mostrar colunas disponíveis (pode comentar depois)
    with st.expander("🔍 Ver Colunas Disponíveis"):
        st.write(list(df.columns))

    # MÉTRICAS PRINCIPAIS
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if 'total_cases' in df.columns:
            total_de_casos = df.sort_values('date').groupby('location')['total_cases'].tail(1).sum()
            st.metric("Total de Casos", f"{total_de_casos:,.0f}")
        else:
            st.metric("Total de Casos", "N/A")
            
    with col2:
        if 'location' in df.columns:
            st.metric("Países Analisados", f"{df['location'].nunique():,}")
        else:
            st.metric("Países Analisados", "N/A")

    with col3:
        if 'total_deaths' in df.columns:
            mortes = df.sort_values('date').groupby('location')['total_deaths'].tail(1).sum()
            st.metric("Total de Mortos", f"{mortes:,.0f}")
        else:
            st.metric("Total de Mortos", "N/A")

    with col4:
        st.metric("Período", "2 anos")

    st.divider()

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📈 Casos/Temporal", "📊 Mortes/País", "🔍 Vacinados/País", "📋 Casos/População", 'Dados Brutos', '🧮 Query SQL'])

    with tab1:
        st.subheader("Evolução de casos ao longo do tempo, por país:")

        if 'new_cases_smoothed' in df.columns:
            df_temp = df.copy()

            paises_selecionados = st.multiselect(
                "Filtrar por País",
                options=df_temp['location'].unique(),
                default=df_temp['location'].unique()
            )
            df_temp = df_temp[df_temp['location'].isin(paises_selecionados)]

            fig1 = px.line(df_temp, x='date', y='new_cases_smoothed', color='location',
                          title='Novos Casos por Dia, por País (média móvel de 7 dias)',
                          labels={'date': 'Data', 'new_cases_smoothed': 'Novos Casos (média 7d)', 'location': 'País'})
            st.plotly_chart(fig1, use_container_width=True)
        else:
            st.warning("Coluna de data não encontrada para análise temporal")

    with tab2:
        st.subheader("Mortes por país")

        if 'total_deaths' in df.columns:
            df_obitos = df.sort_values('date').groupby('location').tail(1)
            df_obitos = df_obitos.sort_values('total_deaths', ascending=False)

            fig4 = px.bar(df_obitos, x='location', y='total_deaths',
                         title='Total de Óbitos por País',
                         labels={'location': 'País', 'total_deaths': 'Total de Óbitos'})
            st.plotly_chart(fig4, use_container_width=True)
        else:
            st.warning("Coluna de status não encontrada")

    with tab3:
        st.subheader("Proporção de Vacinados (ao menos 1 dose)")

        if 'people_vaccinated_per_hundred' in df.columns:
            df_vacinados = df.dropna(subset=['people_vaccinated_per_hundred']).sort_values('date').groupby('location').tail(1)
            df_vacinados = df_vacinados.sort_values('people_vaccinated_per_hundred', ascending=False)
            df_vacinados['faixa'] = df_vacinados['people_vaccinated_per_hundred'].apply(
                lambda x: 'Abaixo de 70%' if x < 70 else '70% ou mais'
            )

            fig5 = px.bar(df_vacinados, x='location', y='people_vaccinated_per_hundred', color='faixa',
                         color_discrete_map={'menor que 70%': '#d62728', '70% ou mais': '#2ca02c'},
                         title='Proporção de Vacinados por País (%)',
                         labels={'location': 'País', 'people_vaccinated_per_hundred': '% Vacinados', 'faixa': 'Faixa'})
            st.plotly_chart(fig5, use_container_width=True)
        else:
            st.warning("Colunas de data de entrega não encontradas")

    with tab4:
        st.subheader("População x Total de Casos")

        if all(col in df.columns for col in ['population', 'total_cases']):
            df_pop = df.dropna(subset=['population', 'total_cases']).sort_values('date').groupby('location').tail(1)

            fig6 = px.scatter(df_pop, x='population', y='total_cases', color='location', text='location',
                             title='População x Total de Casos, por País',
                             labels={'population': 'População', 'total_cases': 'Total de Casos'})
            fig6.update_traces(textposition='top center')
            st.plotly_chart(fig6, use_container_width=True)
        else:
            st.warning("Colunas de população/casos não encontradas")

    with tab5:
            st.subheader("Dados Brutos")
    
            st.dataframe(df.head(200), use_container_width=True)
    
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download CSV",
                data=csv,
                file_name=f'olist_data_{datetime.now().strftime("%Y%m%d")}.csv',
                mime='text/csv',
            )

    with tab6:
        st.subheader("Query SQL")

        query = st.text_area(
            "Digite sua consulta SQL",
            value="SELECT * FROM TB_COVID_FILTRADO LIMIT 10;",
            height=150
        )

        if st.button("▶️ Executar Query"):
            query_limpa = query.strip().rstrip(';').strip()
            primeira_palavra = query_limpa.split(None, 1)[0].upper() if query_limpa else ''

            if ';' in query_limpa:
                st.error("❌ Apenas uma consulta por vez (não use ';' no meio do texto)")
            elif primeira_palavra not in ('SELECT', 'WITH'):
                st.error("❌ Somente consultas SELECT são permitidas")
            else:
                try:
                    with st.spinner("Executando consulta..."):
                        session = Session.builder.configs(connection_parameters).create()
                        session.sql("USE DATABASE TEST_DB").collect()
                        session.sql("USE SCHEMA PUBLIC").collect()

                        resultado = session.sql(query_limpa).to_pandas()
                        session.close()

                    st.success(f"✅ {len(resultado)} linhas retornadas")
                    st.dataframe(resultado, use_container_width=True)
                except Exception as e:
                    st.error(f"❌ Erro ao executar query: {e}")
else:
    st.info("👈 Clique em 'Carregar/Atualizar Dados no Snowflake' primeiro (só na primeira vez), depois em 'Carregar Dashboard'")
