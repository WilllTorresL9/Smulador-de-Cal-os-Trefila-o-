import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import tempfile
import os
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from fpdf import FPDF

# --- FUNÇÃO DE CÁLCULO MATEMÁTICO SEGURO ---
def calcular_expressao(valor_str):
    try:
        expr = str(valor_str).replace(',', '.').strip()
        resultado = float(eval(expr, {"__builtins__": {}}))
        return resultado
    except:
        return 0.0

# --- FUNÇÃO DE GERAÇÃO DA IMAGEM TÉCNICA PARA O PDF (MATPLOTLIB) ---
def gerar_imagem_grafico_pdf(valor_base_inicial, bases_fixas, calcos, alocacao, novas_distancias):
    fig_pdf, ax = plt.subplots(figsize=(10, 2.5))
    
    # Cores equivalentes às do dashboard
    cor_base_hex = "#A9A9A9"
    cores_calcos_hex = [
        "#228B22",  # Verde
        "#008080",  # Teal
        "#000080",  # Azul Escuro
        "#800080"   # Roxo
    ]
    
    # Desenha Base Inicial (Aba)
    pos_x = 0
    ax.add_patch(patches.Rectangle((pos_x, 0), valor_base_inicial, 1, facecolor=cor_base_hex, edgecolor="black", linewidth=1.5))
    ax.text(pos_x + valor_base_inicial/2, 0.5, f"1º Postiço\n{valor_base_inicial:.1f}mm", color="black", fontsize=8, ha='center', va='center', weight='bold')
    pos_x += valor_base_inicial
    
    opcoes_posicao = list(bases_fixas.keys())
    titulos_curtos = ["1º/2º Est.", "2º/3º Est.", "3º/4º Est.", "4º/5º Est."]
    
    for i, estagio in enumerate(opcoes_posicao):
        # Desenha calços alocados neste estágio
        for idx_c, (nome_calco, posicao) in enumerate(alocacao.items()):
            if posicao == estagio:
                esp = calcos[nome_calco]
                ax.add_patch(patches.Rectangle((pos_x, 0), esp, 1, facecolor=cores_calcos_hex[idx_c], edgecolor="black", linewidth=1.5))
                ax.text(pos_x + esp/2, 0.5, f"{idx_c+1}º\n{esp:.1f}mm", color="white", fontsize=8, ha='center', va='center', weight='bold')
                pos_x += esp
                
        # Desenha o Postiço/Base do estágio
        tam_base = bases_fixas[estagio]
        ax.add_patch(patches.Rectangle((pos_x, 0), tam_base, 1, facecolor=cor_base_hex, edgecolor="black", linewidth=1.5))
        ax.text(pos_x + tam_base/2, 0.5, f"{estagio}\n{tam_base:.1f}mm", color="black", fontsize=8, ha='center', va='center', weight='bold')
        
        # Linha tracejada divisoria de estágio
        ax.axvline(x=pos_x, color="red", linestyle="--", linewidth=1.5)
        ax.text(pos_x + (novas_distancias[estagio]/2), 1.15, titulos_curtos[i], color="red", fontsize=9, ha='center', va='bottom', weight='bold')
        
        pos_x += tam_base
        
    ax.set_xlim(0, pos_x)
    ax.set_ylim(-0.1, 1.4)
    ax.axis('off')
    
    # Salva em arquivo temporário
    tmp_path = tempfile.NamedTemporaryFile(delete=False, suffix=".png").name
    plt.savefig(tmp_path, bbox_inches='tight', dpi=200)
    plt.close(fig_pdf)
    return tmp_path

# --- FUNÇÃO DE GERAÇÃO DE PDF COMPLETA ---
def gerar_pdf(calcos, alocacao, novas_distancias, comprimento_alvo, soma_total_nova, diferenca, nome_dropdown, nome_tabela, valor_base_inicial, bases_fixas):
    pdf = FPDF()
    pdf.add_page()
    
    # Cabeçalho
    pdf.set_font("Arial", style="B", size=14)
    pdf.cell(200, 8, txt="RELATORIO DE SETUP - SIMULADOR DE CALCOS", ln=True, align='C')
    pdf.ln(2)
    
    # Insere o Gráfico Técnico Gerado
    img_path = gerar_imagem_grafico_pdf(valor_base_inicial, bases_fixas, calcos, alocacao, novas_distancias)
    pdf.image(img_path, x=10, w=190)
    pdf.ln(4)
    os.remove(img_path)
    
    # Seção: Configuração dos Espaçadores
    pdf.set_font("Arial", style="B", size=11)
    pdf.cell(200, 7, txt="1. Configuracao dos Espacadores:", ln=True)
    pdf.set_font("Arial", size=10)
    for calco, espessura in calcos.items():
        local = nome_dropdown[alocacao[calco]]
        local_limpo = local.replace('º', 'o').replace('ç', 'c').replace('á', 'a')
        calco_limpo = calco.replace('º', 'o').replace('ç', 'c')
        pdf.cell(200, 5, txt=f"   - {calco_limpo}: {espessura:.1f} mm  ->  Alocado {local_limpo}", ln=True)
        
    pdf.ln(2)
    
    # Seção: Distâncias entre Anéis
    pdf.set_font("Arial", style="B", size=11)
    pdf.cell(200, 7, txt="2. Distancia entre Aneis de Reducao:", ln=True)
    pdf.set_font("Arial", size=10)
    for estagio, dist in novas_distancias.items():
        estagio_limpo = nome_tabela[estagio].replace('º', 'o').replace('á', 'a').replace('ç', 'c')
        pdf.cell(200, 5, txt=f"   - {estagio_limpo}: {dist:.1f} mm", ln=True)
        
    pdf.ln(2)
    
    # Seção: Validação Dimensional
    pdf.set_font("Arial", style="B", size=11)
    pdf.cell(200, 7, txt="3. Analise do Comprimento Total:", ln=True)
    pdf.set_font("Arial", size=10)
    pdf.cell(200, 5, txt=f"   - Comprimento Alvo (Original + Folga): {comprimento_alvo:.1f} mm", ln=True)
    pdf.cell(200, 5, txt=f"   - Comprimento Total da Montagem: {soma_total_nova:.1f} mm", ln=True)
    
    if round(diferenca, 1) > 0:
        status_txt = f"ATENCAO: Passando {abs(diferenca):.1f} mm do comprimento alvo."
    elif round(diferenca, 1) < 0:
        status_txt = f"ATENCAO: Faltando {abs(diferenca):.1f} mm para atingir o alvo."
    else:
        status_txt = "PERFEITO: O comprimento total bate exatamente com o alvo."
        
    pdf.ln(2)
    pdf.set_font("Arial", style="B", size=10)
    pdf.cell(200, 6, txt=f"   Status: {status_txt}", ln=True)
    
    # Retorna os bytes do PDF
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
        pdf.output(tmp_pdf.name)
        with open(tmp_pdf.name, "rb") as f:
            pdf_bytes = f.read()
            
    os.remove(tmp_pdf.name)
    return pdf_bytes

# --- CONFIGURAÇÃO DA INTERFACE STREAMLIT ---
st.set_page_config(page_title="Simulador de Calços - Forjaria", layout="wide")

st.title("Simulador Dinâmico e Gráfico dos Calços")
st.write("Insira a espessura (aceita operações matemáticas como 70,5+5), selecione a alocação e defina a folga. O gráfico atualizará em tempo real.")

# 1. Parâmetros Fixos e Dicionários
bases_fixas = {
    "2º Postiço": 240.0, 
    "3º Postiço": 250.0,
    "4º Postiço": 395.0,
    "5º Postiço": 470.0
}

nome_dropdown = {
    "2º Postiço": "Entre 1º e 2º postiço",
    "3º Postiço": "Entre 2º e 3º postiço",
    "4º Postiço": "Entre 3º e 4º postiço",
    "5º Postiço": "Entre 4º e 5º postiço"
}

nome_tabela = {
    "2º Postiço": "1º para 2º estágio",
    "3º Postiço": "2º para 3º estágio",
    "4º Postiço": "3º para 4º estágio",
    "5º Postiço": "4º para 5º estágio"
}

nome_base_inicial = "1º Postiço"
valor_base_inicial = 102.0 

cores_calcos = {
    "1º Espaçador": "rgba(34, 139, 34, 0.9)",
    "2º Espaçador": "rgba(0, 128, 128, 0.9)",
    "3º Espaçador": "rgba(0, 0, 128, 0.9)",
    "4º Espaçador": "rgba(128, 0, 128, 0.9)"
}
cor_base = "rgba(169, 169, 169, 0.6)"

# 2. Parâmetros de Entrada do Operador
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
        entrada_texto = st.text_input(f"Espessura do {nome_calco} (mm):", value=valores_padrao_espessura_str[i], key=f"esp_{i}")
        valor_calculado = calcular_expressao(entrada_texto)
        calcos[nome_calco] = valor_calculado
        st.info(f"📏 Medida calculada: **{valor_calculado:.1f} mm**")
        
    with col2:
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

fig.add_trace(go.Bar(
    y=['Montagem do Eixo'], x=[valor_base_inicial], name=nome_base_inicial,
    orientation='h', marker=dict(color=cor_base, line=dict(color='black', width=1)),
    text=f"{nome_base_inicial}<br>{valor_base_inicial:.1f}mm", textposition='inside', insidetextanchor='middle'
))

for estagio in opcoes_posicao:
    for nome_calco, posicao in alocacao.items():
        if posicao == estagio:
            espessura_atual = calcos[nome_calco]
            novas_distancias[estagio] += espessura_atual
            
            fig.add_trace(go.Bar(
                y=['Montagem do Eixo'], x=[espessura_atual], name=nome_calco,
                orientation='h', marker=dict(color=cores_calcos[nome_calco], line=dict(color='black', width=2)),
                text=f"{nome_calco[:2]}<br>{espessura_atual:.1f}mm", textposition='inside', insidetextanchor='middle'
            ))
            
    fig.add_trace(go.Bar(
        y=['Montagem do Eixo'], x=[bases_fixas[estagio]], name=estagio,
        orientation='h', marker=dict(color=cor_base, line=dict(color='black', width=1)),
        text=f"{estagio}<br>{bases_fixas[estagio]:.1f}mm", textposition='inside', insidetextanchor='middle'
    ))

titulos_distancias = ["1º para 2º estágio", "2º para 3º estágio", "3º para 4º estágio", "4º para 5º estágio"]
posicao_x_acumulada = valor_base_inicial

for i, estagio in enumerate(opcoes_posicao):
    distancia_estagio = novas_distancias[estagio]
    fig.add_vline(x=posicao_x_acumulada, line_width=2, line_dash="dash", line_color="red")
    fig.add_annotation(
        x=posicao_x_acumulada + (distancia_estagio / 2), y=1.05, yref="paper", yanchor="bottom", 
        text=f"<b>{titulos_distancias[i]}</b>", showarrow=False, font=dict(color="red", size=14)
    )
    posicao_x_acumulada += distancia_estagio

fig.update_layout(
    barmode='stack', title=dict(text="Representação Visual do Pacote Interno", y=0.98, x=0.01),
    xaxis_title="Comprimento Total (mm)", yaxis_visible=False, height=330, showlegend=False,
    plot_bgcolor='white', margin=dict(l=20, r=20, t=110, b=50) 
)

# 4. Apresentação Visual no Dashboard
col_grafico, col_tabela = st.columns([2, 1])

with col_grafico:
    st.plotly_chart(fig, use_container_width=True)

with col_tabela:
    st.write("**Distância entre Anéis de Redução**")
    df_resultados = pd.DataFrame({
        "Estágio": [nome_tabela[k] for k in novas_distancias.keys()],
        "Distância Final (mm)": novas_distancias.values()
    })
    st.dataframe(df_resultados, hide_index=True, use_container_width=True)

# 5. Métrica de Validação Dimensional
comprimento_projeto_original = 1737.0 
comprimento_alvo = comprimento_projeto_original + folga_flange
soma_total_nova = sum(novas_distancias.values()) + valor_base_inicial
diferenca = soma_total_nova - comprimento_alvo

st.divider()
st.subheader("Análise do Comprimento")

col_metrica1, col_metrica2 = st.columns(2)
col_metrica1.metric(label="Comprimento Alvo (Original + Folga)", value=f"{comprimento_alvo:.1f} mm")
col_metrica2.metric(
    label="Comprimento Total da Montagem", value=f"{soma_total_nova:.1f} mm",
    delta=f"{diferenca:+.1f} mm (Diferença)", delta_color="off" if round(diferenca, 1) == 0 else "inverse"
)

if round(diferenca, 1) > 0:
    st.error(f"⚠️ **Atenção:** A montagem está **PASSANDO {abs(diferenca):.1f} mm** do comprimento alvo ({comprimento_alvo:.1f} mm).")
elif round(diferenca, 1) < 0:
    st.warning(f"⚠️ **Atenção:** A montagem está **FALTANDO {abs(diferenca):.1f} mm** para atingir o comprimento alvo ({comprimento_alvo:.1f} mm).")
else:
    st.success(f"✅ **Perfeito!** O comprimento total bate exatamente com o alvo de {comprimento_alvo:.1f} mm.")

# 6. Botão de Exportação para PDF com Gráfico
st.divider()
st.subheader("Exportar Relatório")
st.write("Gere um documento PDF contendo a representação gráfica do eixo, parâmetros, distâncias calculadas e a análise de conformidade.")

if st.button("📄 Gerar Relatório em PDF com Gráfico"):
    with st.spinner("Construindo documento PDF com representação gráfica..."):
        pdf_bytes = gerar_pdf(
            calcos, alocacao, novas_distancias, 
            comprimento_alvo, soma_total_nova, diferenca, 
            nome_dropdown, nome_tabela, valor_base_inicial, bases_fixas
        )
        
    st.success("Relatório gerado com sucesso!")
    st.download_button(
        label="📥 Baixar Arquivo PDF",
        data=pdf_bytes,
        file_name="relatorio_setup_calcos.pdf",
        mime="application/pdf"
    )