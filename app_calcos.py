import streamlit as st
import pandas as pd
import plotly.graph_objects as go

# --- FUNÇÃO DE CÁLCULO MATEMÁTICO ---
def calcular_expressao(valor_str):
    try:
        expr = str(valor_str).replace(',', '.').strip()
        resultado = float(eval(expr, {"__builtins__": {}}))
        return resultado
    except:
        return 0.0

# Configuração da página
st.set_page_config(page_title="Simulador de Calços - Forjaria", layout="wide")

st.title("Simulador Dinâmico e Gráfico dos Calços")
st.write("Insira a espessura (aceita operações matemáticas como 70,5+5), selecione a alocação e defina a folga. O gráfico atualizará em tempo real.")

# 1. Distâncias fixas das camisas (Postiços)
bases_fixas = {
    "2º Postiço": 240.0, 
    "3º Postiço": 250.0,
    "4º Postiço": 395.0,
    "5º Postiço": 470.0
}

# --- DICIONÁRIOS DE MAPEAMENTO DE NOMES (NOVOS) ---
# Altera a exibição no menu suspenso de seleção
nome_dropdown = {
    "2º Postiço": "Entre 1º e 2º postiço",
    "3º Postiço": "Entre 2º e 3º postiço",
    "4º Postiço": "Entre 3º e 4º postiço",
    "5º Postiço": "Entre 4º e 5º postiço"
}

# Altera a exibição na tabela de resultados
nome_tabela = {
    "2º Postiço": "1º para 2º estágio",
    "3º Postiço": "2º para 3º estágio",
    "4º Postiço": "3º para 4º estágio",
    "5º Postiço": "4º para 5º estágio"
}

# Base inicial
nome_base_inicial = "1º Postiço"
valor_base_inicial = 102.0 

cores_calcos = {
    "1º Espaçador": "rgba(34, 139, 34, 0.9)",  # Verde
    "2º Espaçador": "rgba(0, 128, 128, 0.9)",  # Teal
    "3º Espaçador": "rgba(0, 0, 128, 0.9)",    # Azul Escuro
    "4º Espaçador": "rgba(128, 0, 128, 0.9)"   # Roxo
}
cor_base = "rgba(169, 169, 169, 0.6)" # Cinza

# 2. Interface de Entrada do Operador
st.subheader("Parâmetros da Montagem")

folga_flange = st.number_input(
    "Folga para aperto do Flange (mm):", 
    value=0.0, 
    step=0.1,
    help="Este valor será somado ao comprimento padrão original (1737.0 mm) para definir o novo comprimento alvo."
)

st.divider()
st.subheader("Configuração dos Calços")

calcos = {}
alocacao = {}
opcoes_posicao = list(bases_fixas.keys())
valores_padrao_espessura_str = ["70.5", "68.5", "70.5", "70.5"]

for i in range(4):
    col1, col2 = st.columns(2)
    nome_calco = f"{i+1}º Espaçador"
    
    with col1:
        entrada_texto = st.text_input(
            f"Espessura do {nome_calco} (mm):", 
            value=valores_padrao_espessura_str[i], 
            key=f"esp_{i}"
        )
        
        # Calcula a expressão em tempo real
        valor_calculado = calcular_expressao(entrada_texto)
        calcos[nome_calco] = valor_calculado
        
        # Destaque visual
        st.info(f"📏 Medida calculada: **{valor_calculado:.1f} mm**")
        
    with col2:
        # ATUALIZAÇÃO: Usa o format_func para exibir o nome customizado no dropdown
        alocacao[nome_calco] = st.selectbox(
            f"Local de alocação:", 
            opcoes_posicao, 
            format_func=lambda x: nome_dropdown[x], 
            index=i, 
            key=f"pos_{i}"
        )

st.divider()

# 3. Processamento de Cálculos e Representação Gráfica
novas_distancias = bases_fixas.copy()
fig = go.Figure()

# Desenha o 1º Postiço (102,0 mm) antes de todos os outros componentes
fig.add_trace(go.Bar(
    y=['Montagem do Eixo'],
    x=[valor_base_inicial],
    name=nome_base_inicial,
    orientation='h',
    marker=dict(color=cor_base, line=dict(color='black', width=1)),
    text=f"{nome_base_inicial}<br>{valor_base_inicial:.1f}mm",
    textposition='inside',
    insidetextanchor='middle'
))

for estagio in opcoes_posicao:
    # Calços deste estágio
    for nome_calco, posicao in alocacao.items():
        if posicao == estagio:
            espessura_atual = calcos[nome_calco]
            novas_distancias[estagio] += espessura_atual
            
            fig.add_trace(go.Bar(
                y=['Montagem do Eixo'],
                x=[espessura_atual],
                name=nome_calco,
                orientation='h',
                marker=dict(color=cores_calcos[nome_calco], line=dict(color='black', width=2)),
                text=f"{nome_calco[:2]}<br>{espessura_atual:.1f}mm",
                textposition='inside',
                insidetextanchor='middle'
            ))
            
    # Base (Postiço) do estágio
    fig.add_trace(go.Bar(
        y=['Montagem do Eixo'],
        x=[bases_fixas[estagio]],
        name=estagio,
        orientation='h',
        marker=dict(color=cor_base, line=dict(color='black', width=1)),
        text=f"{estagio}<br>{bases_fixas[estagio]:.1f}mm",
        textposition='inside',
        insidetextanchor='middle'
    ))

# --- ADIÇÃO DAS LINHAS DINÂMICAS TRACEJADAS ---
titulos_distancias = [
    "1º para 2º estágio", 
    "2º para 3º estágio", 
    "3º para 4º estágio", 
    "4º para 5º estágio"
]
posicao_x_acumulada = valor_base_inicial

for i, estagio in enumerate(opcoes_posicao):
    distancia_estagio = novas_distancias[estagio]
    
    # Adiciona a linha vermelha tracejada no início da zona do estágio
    fig.add_vline(x=posicao_x_acumulada, line_width=2, line_dash="dash", line_color="red")
    
    # Adiciona o texto centralizado na cota de distância daquele estágio
    fig.add_annotation(
        x=posicao_x_acumulada + (distancia_estagio / 2),
        y=1.05, 
        yref="paper",
        yanchor="bottom", 
        text=f"<b>{titulos_distancias[i]}</b>",
        showarrow=False,
        font=dict(color="red", size=14)
    )
    
    posicao_x_acumulada += distancia_estagio

# Ajuste fino de layout 
fig.update_layout(
    barmode='stack', 
    title=dict(
        text="Representação Visual do Pacote Interno",
        y=0.98,
        x=0.01
    ),
    xaxis_title="Comprimento Total (mm)",
    yaxis_visible=False, 
    height=330, 
    showlegend=False,
    plot_bgcolor='white',
    margin=dict(l=20, r=20, t=110, b=50) 
)

# 4. Apresentação dos Resultados
col_grafico, col_tabela = st.columns([2, 1])

with col_grafico:
    st.plotly_chart(fig, use_container_width=True)

with col_tabela:
    # ATUALIZAÇÃO: Título modificado conforme solicitado
    st.write("**Distância entre Anéis de Redução**")
    
    # ATUALIZAÇÃO: Utiliza o dicionário nome_tabela para alterar os nomes das linhas
    df_resultados = pd.DataFrame({
        "Estágio": [nome_tabela[k] for k in novas_distancias.keys()],
        "Distância Final (mm)": novas_distancias.values()
    })
    st.dataframe(df_resultados, hide_index=True, use_container_width=True)

# 5. Métrica de Validação
comprimento_projeto_original = 1737.0 
comprimento_alvo = comprimento_projeto_original + folga_flange

soma_total_nova = sum(novas_distancias.values()) + valor_base_inicial
diferenca = soma_total_nova - comprimento_alvo

st.divider()
st.subheader("Análise do Comprimento")

col_metrica1, col_metrica2 = st.columns(2)

col_metrica1.metric(
    label="Comprimento Alvo (Original + Folga)", 
    value=f"{comprimento_alvo:.1f} mm"
)

col_metrica2.metric(
    label="Comprimento Total da Montagem", 
    value=f"{soma_total_nova:.1f} mm",
    delta=f"{diferenca:+.1f} mm (Diferença)",
    delta_color="off" if round(diferenca, 1) == 0 else "inverse"
)

if round(diferenca, 1) > 0:
    st.error(f"⚠️ **Atenção:** A montagem está **PASSANDO {abs(diferenca):.1f} mm** do comprimento alvo ({comprimento_alvo:.1f} mm).")
elif round(diferenca, 1) < 0:
    st.warning(f"⚠️ **Atenção:** A montagem está **FALTANDO {abs(diferenca):.1f} mm** para atingir o comprimento alvo ({comprimento_alvo:.1f} mm).")
else:
    st.success(f"✅ **Perfeito!** O comprimento total bate exatamente com o alvo de {comprimento_alvo:.1f} mm.")