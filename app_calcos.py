import streamlit as st
import pandas as pd
import plotly.graph_objects as go

# Configuração da página para ocupar mais espaço na tela
st.set_page_config(page_title="Simulador de Calços - Forjaria", layout="wide")

st.title("Simulador Dinâmico e Gráfico dos Calços")
st.write("Insira a espessura de cada calço e selecione em qual estágio ele deve ser alocado. O gráfico abaixo atualizará a montagem em tempo real.")

# 1. Distâncias fixas das camisas (bases extraídas do comprimento original - calço original)
bases_fixas = {
    "1º para 2º Estágio": 238.0, 
    "2º para 3º Estágio": 260.0,
    "3º para 4º Estágio": 395.0,
    "4º para 5º Estágio": 470.1
}

# Cores baseadas na referência visual do projeto para facilitar a identificação pelo operador
cores_calcos = {
    "1º Espaçador": "rgba(34, 139, 34, 0.9)",  # Verde
    "2º Espaçador": "rgba(0, 128, 128, 0.9)",  # Teal (Azul Esverdeado)
    "3º Espaçador": "rgba(0, 0, 128, 0.9)",    # Azul Escuro
    "4º Espaçador": "rgba(128, 0, 128, 0.9)"   # Roxo
}

cor_base = "rgba(169, 169, 169, 0.6)" # Cinza para as partes fixas

# 2. Interface de Entrada do Operador (Espessura e Estágio)
st.subheader("Parâmetros dos Calços")

calcos = {}
alocacao = {}
opcoes_posicao = list(bases_fixas.keys())

# Valores padrão conforme desenho
valores_padrao_espessura = [70.5, 68.5, 70.5, 70.5]

# Cria um grid de inputs para os 4 espaçadores
for i in range(4):
    col1, col2 = st.columns(2)
    nome_calco = f"{i+1}º Espaçador"
    
    with col1:
        calcos[nome_calco] = st.number_input(
            f"Espessura do {nome_calco} (mm):", 
            value=valores_padrao_espessura[i], 
            step=0.1, 
            key=f"esp_{i}"
        )
    with col2:
        alocacao[nome_calco] = st.selectbox(
            f"Estágio de alocação ({nome_calco}):", 
            opcoes_posicao, 
            index=i, 
            key=f"pos_{i}"
        )

st.divider()

# 3. Processamento de Cálculos e Representação Gráfica
novas_distancias = bases_fixas.copy()
fig = go.Figure()

# Construção do empilhamento visual da esquerda para a direita
for estagio in opcoes_posicao:
    # Adiciona a Base Fixa (Camisa) do estágio no gráfico
    fig.add_trace(go.Bar(
        y=['Montagem do Eixo'],
        x=[bases_fixas[estagio]],
        name=f"Base ({estagio})",
        orientation='h',
        marker=dict(color=cor_base, line=dict(color='black', width=1)),
        text=f"Base {estagio[:2]}<br>{bases_fixas[estagio]}mm",
        textposition='inside',
        insidetextanchor='middle'
    ))
    
    # Verifica quais calços foram alocados pelo operador neste estágio específico
    for nome_calco, posicao in alocacao.items():
        if posicao == estagio:
            espessura_atual = calcos[nome_calco]
            novas_distancias[estagio] += espessura_atual
            
            # Adiciona o calço no gráfico adjacente à base
            fig.add_trace(go.Bar(
                y=['Montagem do Eixo'],
                x=[espessura_atual],
                name=nome_calco,
                orientation='h',
                marker=dict(color=cores_calcos[nome_calco], line=dict(color='black', width=2)),
                text=f"{nome_calco[:2]}<br>{espessura_atual}mm",
                textposition='inside',
                insidetextanchor='middle'
            ))

# Configuração de layout do gráfico para parecer uma peça mecânica
fig.update_layout(
    barmode='stack', # Empilha horizontalmente
    title="Representação Visual do Pacote Interno",
    xaxis_title="Comprimento Total (mm)",
    yaxis_visible=False, # Oculta o eixo Y (já que é apenas um tubo/eixo)
    height=300,
    showlegend=True,
    plot_bgcolor='white',
    margin=dict(l=20, r=20, t=50, b=50)
)

# 4. Apresentação dos Resultados
col_grafico, col_tabela = st.columns([2, 1])

with col_grafico:
    # Exibe o gráfico renderizado
    st.plotly_chart(fig, use_container_width=True)

with col_tabela:
    # Tabela resumo das novas distâncias
    st.subheader("Novas Distâncias Totais")
    df_resultados = pd.DataFrame({
        "Estágio": novas_distancias.keys(),
        "Distância Final (mm)": novas_distancias.values()
    })
    st.dataframe(df_resultados, hide_index=True, use_container_width=True)

# 5. Métrica de Validação
soma_total_nova = sum(novas_distancias.values())

st.metric(
    label="Comprimento Total da Montagem (mm)", 
    value=f"{soma_total_nova:.1f} mm"
)

# Alerta caso o operador configure espessuras que saiam do comprimento padrão original (~1643.1 mm das zonas móveis)
if round(soma_total_nova, 1) != 1643.1:
    st.warning("⚠️ Atenção: A espessura dos calços foi alterada resultando num comprimento total diferente do projeto original (1643.1 mm).")
else:
    st.success("✅ Comprimento total de montagem validado.")