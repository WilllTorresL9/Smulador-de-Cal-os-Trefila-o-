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

# --- CLASSE DE PDF PERSONALIZADA PARA PADRÃO INDUSTRIAL ---
class PDFRelatorioIndustrial(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 12)
        self.set_text_color(40, 40, 40)
        self.cell(0, 6, 'RELATORIO TECNICO DE SETUP - PACOTE INTERNO DE TREFILA', 0, 1, 'L')
        self.set_font('Arial', '', 9)
        self.set_text_color(100, 100, 100)
        self.cell(0, 5, 'Modulo de Analise Dimensional e Alocacao de Calcos', 0, 1, 'L')
        
        self.set_draw_color(180, 180, 180)
        self.set_line_width(0.5)
        self.line(10, 20, 200, 20)
        self.ln(6)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f'Pagina {self.page_no()} | Gerado via Simulador Industrial de Calcos', 0, 0, 'C')

# --- FUNÇÃO DE GERAÇÃO DA IMAGEM TÉCNICA PARA O PDF (TEXTOS VERTICAIS PADRONIZADOS) ---
def gerar_imagem_grafico_pdf(valor_base_inicial, bases_fixas, calcos, alocacao, novas_distancias):
    fig_pdf, ax = plt.subplots(figsize=(10, 2.3), dpi=250)
    
    cor_base_hex = "#D3D3D3" # Cinza claro industrial
    cores_calcos_hex = ["#2CA02C", "#17BECF", "#1F77B4", "#9467BD"]
    
    pos_x = 0
    # Desenha Base Inicial (1º Postiço) com texto vertical
    ax.add_patch(patches.Rectangle((pos_x, 0), valor_base_inicial, 1, facecolor=cor_base_hex, edgecolor="black", linewidth=1))
    ax.text(pos_x + valor_base_inicial/2, 0.5, f"1º Postiço\n{valor_base_inicial:.1f}mm", color="black", fontsize=7, ha='center', va='center', weight='bold', rotation=90)
    pos_x += valor_base_inicial
    
    opcoes_posicao = list(bases_fixas.keys())
    titulos_curtos = ["1º para 2º estágio", "2º para 3º estágio", "3º para 4º estágio", "4º para 5º estágio"]
    
    for i, estagio in enumerate(opcoes_posicao):
        x_inicio_estagio = pos_x
        
        # Desenha calços ativos (> 0.5mm) com texto vertical padronizado
        for idx_c, (nome_calco, posicao) in enumerate(alocacao.items()):
            if posicao == estagio:
                esp = calcos[nome_calco]
                if esp > 0.5:
                    ax.add_patch(patches.Rectangle((pos_x, 0), esp, 1, facecolor=cores_calcos_hex[idx_c], edgecolor="black", linewidth=1))
                    ax.text(pos_x + esp/2, 0.5, f"{idx_c+1}º Esp.\n{esp:.1f}mm", color="white", fontsize=7, ha='center', va='center', weight='bold', rotation=90)
                    pos_x += esp
                
        # Desenha o Postiço/Base do estágio com texto vertical padronizado
        tam_base = bases_fixas[estagio]
        ax.add_patch(patches.Rectangle((pos_x, 0), tam_base, 1, facecolor=cor_base_hex, edgecolor="black", linewidth=1))
        ax.text(pos_x + tam_base/2, 0.5, f"{i+2}º Postiço\n{tam_base:.1f}mm", color="black", fontsize=7, ha='center', va='center', weight='bold', rotation=90)
        pos_x += tam_base
        
        # Linha tracejada vermelha e título do estágio
        ax.axvline(x=x_inicio_estagio, color="red", linestyle="--", linewidth=1.2)
        largura_total_estagio = novas_distancias[estagio]
        ax.text(x_inicio_estagio + (largura_total_estagio / 2), 1.12, titulos_curtos[i], color="red", fontsize=8, ha='center', va='bottom', weight='bold')
        
    ax.set_xlim(0, pos_x)
    ax.set_ylim(-0.1, 1.4)
    ax.axis('off')
    
    tmp_path = tempfile.NamedTemporaryFile(delete=False, suffix=".png").name
    plt.savefig(tmp_path, bbox_inches='tight', dpi=300)
    plt.close(fig_pdf)
    return tmp_path

# --- FUNÇÃO DE GERAÇÃO DE PDF EXECUTIVO ---
def gerar_pdf(calcos, alocacao, novas_distancias, comprimento_alvo, soma_total_nova, diferenca, nome_dropdown, nome_tabela, valor_base_inicial, bases_fixas):
    pdf = PDFRelatorioIndustrial(orientation='P', unit='mm', format='A4')
    pdf.add_page()
    
    # 1. Representação Gráfica
    pdf.set_font("Arial", 'B', 10)
    pdf.set_text_color(50, 50, 50)
    pdf.cell(0, 6, "1. REPRESENTACAO ESQUEMATICA DA MONTAGEM", 0, 1, 'L')
    pdf.ln(1)
    
    img_path = gerar_imagem_grafico_pdf(valor_base_inicial, bases_fixas, calcos, alocacao, novas_distancias)
    pdf.image(img_path, x=10, w=190)
    pdf.ln(4)
    os.remove(img_path)
    
    # 2. Tabela de Configuração dos Espaçadores
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(0, 6, "2. CONFIGURACAO DOS ESPACADORES (CALCOS)", 0, 1, 'L')
    pdf.ln(1)
    
    pdf.set_fill_color(230, 230, 230)
    pdf.set_font("Arial", 'B', 9)
    pdf.cell(45, 6, "Espacador", 1, 0, 'C', True)
    pdf.cell(35, 6, "Espessura (mm)", 1, 0, 'C', True)
    pdf.cell(110, 6, "Posicao de Alocacao no Eixo", 1, 1, 'C', True)
    
    pdf.set_font("Arial", '', 9)
    for calco, espessura in calcos.items():
        local = nome_dropdown[alocacao[calco]]
        local_limpo = local.replace('º', 'o').replace('ç', 'c').replace('á', 'a')
        calco_limpo = calco.replace('º', 'o').replace('ç', 'c')
        
        pdf.cell(45, 6, f"   {calco_limpo}", 1, 0, 'L')
        pdf.cell(35, 6, f"{espessura:.1f} mm", 1, 0, 'C')
        pdf.cell(110, 6, f"   {local_limpo}", 1, 1, 'L')
        
    pdf.ln(4)
    
    # 3. Tabela de Distâncias entre Estágios
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(0, 6, "3. DISTANCIA ENTRE ANEIS DE REDUCAO", 0, 1, 'L')
    pdf.ln(1)
    
    pdf.set_fill_color(230, 230, 230)
    pdf.set_font("Arial", 'B', 9)
    pdf.cell(130, 6, "Estagio / Intervalo", 1, 0, 'C', True)
    pdf.cell(60, 6, "Distancia Final (mm)", 1, 1, 'C', True)
    
    pdf.set_font("Arial", '', 9)
    for estagio, dist in novas_distancias.items():
        estagio_limpo = nome_tabela[estagio].replace('º', 'o').replace('á', 'a').replace('ç', 'c')
        pdf.cell(130, 6, f"   {estagio_limpo}", 1, 0, 'L')
        pdf.cell(60, 6, f"{dist:.1f} mm", 1, 1, 'C')
        
    pdf.ln(4)
    
    # 4. Análise de Conformidade Dimensional
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(0, 6, "4. ANALISE DE CONFORMIDADE DIMENSIONAL", 0, 1, 'L')
    pdf.ln(1)
    
    pdf.set_font("Arial", '', 9)
    pdf.cell(130, 6, "   Comprimento Alvo (Projeto Original + Folga de Flange):", 1, 0, 'L')
    pdf.set_font("Arial", 'B', 9)
    pdf.cell(60, 6, f"{comprimento_alvo:.1f} mm", 1, 1, 'C')
    
    pdf.set_font("Arial", '', 9)
    pdf.cell(130, 6, "   Comprimento Total Consolidado da Montagem:", 1, 0, 'L')
    pdf.set_font("Arial", 'B', 9)
    pdf.cell(60, 6, f"{soma_total_nova:.1f} mm", 1, 1, 'C')
    
    if round(diferenca, 1) > 0:
        status_txt = f"ATENCAO: PASSANDO {abs(diferenca):.1f} mm DO ALVO"
        pdf.set_fill_color(255, 230, 230)
    elif round(diferenca, 1) < 0:
        status_txt = f"ATENCAO: FALTANDO {abs(diferenca):.1f} mm PARA O ALVO"
        pdf.set_fill_color(255, 245, 230)
    else:
        status_txt = "CONFORME: O COMPRIMENTO TOTAL BATE EXATAMENTE COM O ALVO"
        pdf.set_fill_color(230, 255, 230)
        
    pdf.set_font("Arial", 'B', 9)
    pdf.cell(190, 7, f"   STATUS DE VALIDACAO: {status_txt}", 1, 1, 'C', True)
    
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

novas_distancias = bases_fixas.copy()
fig = go.Figure()

# Desenho no Plotly web com texto vertical também
fig.add_trace(go.Bar(
    y=['Montagem do Eixo'], x=[valor_base_inicial], name=nome_base_inicial,
    orientation='h', marker=dict(color=cor_base, line=dict(color='black', width=1)),
    text=f"1º Postiço<br>{valor_base_inicial:.1f}mm", textposition='inside', insidetextanchor='middle'
))

for i, estagio in enumerate(opcoes_posicao):
    for nome_calco, posicao in alocacao.items():
        if posicao == estagio:
            espessura_atual = calcos[nome_calco]
            if espessura_atual > 0.5:
                novas_distancias[estagio] += espessura_atual
                
                # Exibe o número do calço e a espessura de forma limpa
                id_calco_num = nome_calco.split("º")[0]
                texto_barra = f"{id_calco_num}º Esp.<br>{espessura_atual:.1f}mm"
                
                fig.add_trace(go.Bar(
                    y=['Montagem do Eixo'], x=[espessura_atual], name=nome_calco,
                    orientation='h', marker=dict(color=cores_calcos[nome_calco], line=dict(color='black', width=2)),
                    text=texto_barra, textposition='inside', insidetextanchor='middle'
                ))
            
    fig.add_trace(go.Bar(
        y=['Montagem do Eixo'], x=[bases_fixas[estagio]], name=estagio,
        orientation='h', marker=dict(color=cor_base, line=dict(color='black', width=1)),
        text=f"{i+2}º Postiço<br>{bases_fixas[estagio]:.1f}mm", textposition='inside', insidetextanchor='middle'
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

st.divider()
st.subheader("Exportar Relatório")
st.write("Gere um documento PDF em formato executivo/industrial contendo o desenho esquemático, tabelas estruturadas e análise de conformidade para aprovação da engenharia e produção.")

if st.button("📄 Gerar Relatório Executivo em PDF"):
    with st.spinner("Compilando relatório técnico de engenharia..."):
        pdf_bytes = gerar_pdf(
            calcos, alocacao, novas_distancias, 
            comprimento_alvo, soma_total_nova, diferenca, 
            nome_dropdown, nome_tabela, valor_base_inicial, bases_fixas
        )
        
    st.success("Relatório gerado com sucesso!")
    st.download_button(
        label="📥 Baixar Relatório Técnico PDF",
        data=pdf_bytes,
        file_name="relatorio_tecnico_setup_calcos.pdf",
        mime="application/pdf"
    )