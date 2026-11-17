"""
Simulador Dinâmico de Calços — Pacote Interno de Trefila
Interface profissional (azul-marinho / branco) com ferramentas de análise:
  • Montagem interativa com esquema gráfico em tempo real
  • Análise dimensional (cascata, composição, desvio por estágio)
  • Otimização de alocação e sugestão de correção de espessura
  • Análise de tolerâncias: pior caso, RSS e simulação Monte Carlo (Cp/Cpk)
  • Exportação: relatório PDF, planilha Excel e configuração JSON
"""

import ast
import io
import itertools
import json
import operator
import os
import tempfile
from datetime import datetime

import matplotlib

matplotlib.use("Agg")
import matplotlib.patches as patches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from fpdf import FPDF

# =============================================================================
# IDENTIDADE VISUAL
# =============================================================================
NAVY_950 = "#06142B"
NAVY_900 = "#0B1F3A"
NAVY_800 = "#13315C"
NAVY_700 = "#1F4E89"
NAVY_500 = "#3A75C4"
NAVY_300 = "#7FA7D9"
NAVY_100 = "#DCE6F3"
NAVY_50 = "#F2F5FA"
BORDA = "#D5DDEA"
CINZA_TXT = "#5B6B82"
OK = "#1E8E5A"
ALERTA = "#C98A06"
ERRO = "#C0392B"

CORES_CALCOS = [NAVY_900, NAVY_700, NAVY_500, NAVY_300]
COR_POSTICO = NAVY_100

# =============================================================================
# DADOS DE PROJETO (PADRÃO)
# =============================================================================
ESTAGIOS = ["2º Postiço", "3º Postiço", "4º Postiço", "5º Postiço"]
BASES_PADRAO = {"2º Postiço": 240.0, "3º Postiço": 250.0, "4º Postiço": 395.0, "5º Postiço": 470.0}
BASE_INICIAL_PADRAO = 102.0
COMPRIMENTO_ORIGINAL_PADRAO = 1737.0
ESPESSURAS_PADRAO = ["70.5", "68.5", "70.5", "70.5"]
ESPESSURA_MINIMA = 0.5  # calços com espessura <= este valor são desconsiderados
N_CALCOS = 4
NOMES_CALCOS = [f"{i + 1}º Espaçador" for i in range(N_CALCOS)]

NOME_DROPDOWN = {
    "2º Postiço": "Entre 1º e 2º postiço",
    "3º Postiço": "Entre 2º e 3º postiço",
    "4º Postiço": "Entre 3º e 4º postiço",
    "5º Postiço": "Entre 4º e 5º postiço",
}
NOME_TABELA = {
    "2º Postiço": "1º para 2º estágio",
    "3º Postiço": "2º para 3º estágio",
    "4º Postiço": "3º para 4º estágio",
    "5º Postiço": "4º para 5º estágio",
}

# =============================================================================
# NÚCLEO DE CÁLCULO
# =============================================================================
_OPERADORES = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _avaliar_no(no):
    if isinstance(no, ast.Expression):
        return _avaliar_no(no.body)
    if isinstance(no, ast.Constant) and isinstance(no.value, (int, float)):
        return float(no.value)
    if isinstance(no, ast.BinOp) and type(no.op) in _OPERADORES:
        return _OPERADORES[type(no.op)](_avaliar_no(no.left), _avaliar_no(no.right))
    if isinstance(no, ast.UnaryOp) and type(no.op) in _OPERADORES:
        return _OPERADORES[type(no.op)](_avaliar_no(no.operand))
    raise ValueError("Expressão não suportada")


def calcular_expressao(valor_str):
    """Avalia com segurança expressões aritméticas (ex.: '70,5+5'). Retorna (valor, ok)."""
    try:
        expr = str(valor_str).replace(",", ".").strip()
        if not expr:
            return 0.0, False
        return float(_avaliar_no(ast.parse(expr, mode="eval"))), True
    except Exception:
        return 0.0, False


def calcular_montagem(base_inicial, bases, calcos, alocacao):
    """Retorna as distâncias finais por estágio e o comprimento total."""
    distancias = dict(bases)
    for nome, esp in calcos.items():
        if esp > ESPESSURA_MINIMA:
            distancias[alocacao[nome]] += esp
    total = base_inicial + sum(distancias.values())
    return distancias, total


def classificar(diferenca, tolerancia):
    d = round(diferenca, 1)
    if abs(d) <= tolerancia + 1e-9:
        return "CONFORME", OK
    return ("ACIMA DO ALVO", ERRO) if d > 0 else ("ABAIXO DO ALVO", ALERTA)


def otimizar_alocacao(bases, calcos, alvos_estagio):
    """Enumera todas as alocações possíveis e ordena pelo desvio em relação aos alvos por estágio."""
    nomes = list(calcos.keys())
    resultados = []
    for combinacao in itertools.product(ESTAGIOS, repeat=len(nomes)):
        aloc = dict(zip(nomes, combinacao))
        dist, _ = calcular_montagem(0.0, bases, calcos, aloc)
        desvios = np.array([dist[e] - alvos_estagio[e] for e in ESTAGIOS])
        resultados.append(
            {
                "alocacao": aloc,
                "rms": float(np.sqrt(np.mean(desvios**2))),
                "max_abs": float(np.max(np.abs(desvios))),
                "desvios": desvios,
            }
        )
    resultados.sort(key=lambda r: (round(r["max_abs"], 6), r["rms"]))
    return resultados


def simular_monte_carlo(base_inicial, bases, calcos, alocacao, tol_calco, tol_postico, n, semente=42):
    """Simulação Monte Carlo assumindo tolerância = ±3σ (distribuição normal)."""
    rng = np.random.default_rng(semente)
    sig_c, sig_p = tol_calco / 3.0, tol_postico / 3.0
    estagios_sim = {e: rng.normal(bases[e], sig_p, n) for e in ESTAGIOS}
    base_sim = rng.normal(base_inicial, sig_p, n)
    for nome, esp in calcos.items():
        if esp > ESPESSURA_MINIMA:
            estagios_sim[alocacao[nome]] = estagios_sim[alocacao[nome]] + rng.normal(esp, sig_c, n)
    total = base_sim + sum(estagios_sim.values())
    return total, estagios_sim


# =============================================================================
# RELATÓRIO PDF
# =============================================================================
def _txt(s):
    """Garante compatibilidade com as fontes padrão do PDF (Latin-1)."""
    trocas = {"—": "-", "–": "-", "σ": "sigma", "→": "->", "≥": ">=", "≤": "<=", "✔": "", "⚠": ""}
    s = str(s)
    for a, b in trocas.items():
        s = s.replace(a, b)
    return s.encode("latin-1", "replace").decode("latin-1")


class PDFRelatorio(FPDF):
    def header(self):
        self.set_fill_color(11, 31, 58)
        self.rect(0, 0, 210, 26, "F")
        self.set_xy(10, 6)
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(255, 255, 255)
        self.cell(0, 7, _txt("RELATÓRIO TÉCNICO DE SETUP — PACOTE INTERNO DE TREFILA"), 0, 1, "L")
        self.set_x(10)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(200, 214, 235)
        self.cell(0, 5, _txt("Módulo de Análise Dimensional e Alocação de Calços"), 0, 0, "L")
        self.cell(0, 5, _txt(datetime.now().strftime("Emitido em %d/%m/%Y %H:%M")), 0, 1, "R")
        self.ln(10)

    def footer(self):
        self.set_y(-14)
        self.set_draw_color(213, 221, 234)
        self.line(10, self.get_y(), 200, self.get_y())
        self.set_font("Helvetica", "", 8)
        self.set_text_color(91, 107, 130)
        self.cell(0, 9, _txt(f"Página {self.page_no()}  |  Simulador Industrial de Calços"), 0, 0, "C")

    def secao(self, titulo):
        self.ln(2)
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(11, 31, 58)
        self.cell(0, 7, _txt(titulo.upper()), 0, 1, "L")
        self.set_draw_color(31, 78, 137)
        self.set_line_width(0.6)
        self.line(10, self.get_y(), 40, self.get_y())
        self.set_line_width(0.2)
        self.ln(2)

    def tabela(self, cabecalho, linhas, larguras, alinhamentos=None):
        alinhamentos = alinhamentos or ["L"] * len(cabecalho)
        self.set_font("Helvetica", "B", 9)
        self.set_fill_color(19, 49, 92)
        self.set_text_color(255, 255, 255)
        self.set_draw_color(213, 221, 234)
        for c, w in zip(cabecalho, larguras):
            self.cell(w, 7, _txt(c), 1, 0, "C", True)
        self.ln()
        self.set_font("Helvetica", "", 9)
        self.set_text_color(11, 31, 58)
        for i, linha in enumerate(linhas):
            self.set_fill_color(*((242, 245, 250) if i % 2 == 0 else (255, 255, 255)))
            for v, w, a in zip(linha, larguras, alinhamentos):
                self.cell(w, 6.5, _txt(f"  {v}  " if a == "L" else v), 1, 0, a, True)
            self.ln()


def gerar_imagem_esquema(base_inicial, bases, calcos, alocacao, distancias):
    fig, ax = plt.subplots(figsize=(10, 2.4), dpi=200)
    pos_x = 0.0

    def bloco(x, w, cor, texto, cor_txt):
        ax.add_patch(patches.Rectangle((x, 0), w, 1, facecolor=cor, edgecolor=NAVY_900, linewidth=0.8))
        ax.text(x + w / 2, 0.5, texto, color=cor_txt, fontsize=6.5, ha="center", va="center",
                weight="bold", rotation=90)

    bloco(pos_x, base_inicial, COR_POSTICO, f"1º Postiço\n{base_inicial:.1f} mm", NAVY_900)
    pos_x += base_inicial
    for i, estagio in enumerate(ESTAGIOS):
        x_ini = pos_x
        for idx, nome in enumerate(calcos):
            if alocacao[nome] == estagio and calcos[nome] > ESPESSURA_MINIMA:
                esp = calcos[nome]
                bloco(pos_x, esp, CORES_CALCOS[idx], f"{idx + 1}º Esp.\n{esp:.1f} mm",
                      "white" if idx < 3 else NAVY_900)
                pos_x += esp
        bloco(pos_x, bases[estagio], COR_POSTICO, f"{i + 2}º Postiço\n{bases[estagio]:.1f} mm", NAVY_900)
        pos_x += bases[estagio]
        ax.axvline(x=x_ini, color=NAVY_700, linestyle="--", linewidth=1)
        ax.text(x_ini + distancias[estagio] / 2, 1.1, NOME_TABELA[estagio], color=NAVY_800,
                fontsize=7.5, ha="center", va="bottom", weight="bold")
    ax.set_xlim(0, pos_x)
    ax.set_ylim(-0.1, 1.4)
    ax.axis("off")
    caminho = tempfile.NamedTemporaryFile(delete=False, suffix=".png").name
    plt.savefig(caminho, bbox_inches="tight", dpi=250)
    plt.close(fig)
    return caminho


def gerar_pdf(ctx):
    pdf = PDFRelatorio(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(True, margin=18)
    pdf.add_page()

    # Painel de indicadores
    status, _ = classificar(ctx["diferenca"], ctx["tol_conf"])
    cor_status = {"CONFORME": (30, 142, 90), "ACIMA DO ALVO": (192, 57, 43), "ABAIXO DO ALVO": (201, 138, 6)}[status]
    kpis = [
        ("Comprimento alvo", f"{ctx['alvo']:.1f} mm"),
        ("Comprimento montado", f"{ctx['total']:.1f} mm"),
        ("Diferença", f"{ctx['diferenca']:+.1f} mm"),
        ("Status", status),
    ]
    y0 = pdf.get_y()
    for i, (rot, val) in enumerate(kpis):
        x = 10 + i * 48
        pdf.set_fill_color(242, 245, 250)
        pdf.set_draw_color(213, 221, 234)
        pdf.rect(x, y0, 46, 17, "DF")
        pdf.set_fill_color(*(cor_status if i == 3 else (31, 78, 137)))
        pdf.rect(x, y0, 1.4, 17, "F")
        pdf.set_xy(x + 3, y0 + 2.5)
        pdf.set_font("Helvetica", "", 7.5)
        pdf.set_text_color(91, 107, 130)
        pdf.cell(42, 4, _txt(rot.upper()), 0, 2)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(*(cor_status if i == 3 else (11, 31, 58)))
        pdf.cell(42, 7, _txt(val), 0, 0)
    pdf.set_y(y0 + 21)

    pdf.secao("1. Representação esquemática da montagem")
    img = gerar_imagem_esquema(ctx["base_inicial"], ctx["bases"], ctx["calcos"], ctx["alocacao"], ctx["distancias"])
    pdf.image(img, x=10, w=190)
    os.remove(img)

    pdf.secao("2. Parâmetros de entrada")
    pdf.tabela(
        ["Parâmetro", "Valor"],
        [
            ["Comprimento de projeto original", f"{ctx['original']:.1f} mm"],
            ["Folga para aperto do flange", f"{ctx['folga']:.1f} mm"],
            ["Tolerância de conformidade", f"± {ctx['tol_conf']:.1f} mm"],
        ],
        [130, 60], ["L", "C"],
    )

    pdf.secao("3. Configuração dos espaçadores (calços)")
    pdf.tabela(
        ["Espaçador", "Espessura (mm)", "Posição de alocação no eixo"],
        [[n, f"{e:.1f}", NOME_DROPDOWN[ctx["alocacao"][n]] + ("" if e > ESPESSURA_MINIMA else " (desconsiderado)")]
         for n, e in ctx["calcos"].items()],
        [45, 35, 110], ["L", "C", "L"],
    )

    pdf.secao("4. Distância entre anéis de redução")
    pdf.tabela(
        ["Estágio / intervalo", "Postiço (mm)", "Calços (mm)", "Distância final (mm)"],
        [[NOME_TABELA[e], f"{ctx['bases'][e]:.1f}", f"{ctx['distancias'][e] - ctx['bases'][e]:.1f}",
          f"{ctx['distancias'][e]:.1f}"] for e in ESTAGIOS],
        [70, 40, 40, 40], ["L", "C", "C", "C"],
    )

    pdf.secao("5. Análise de tolerâncias (stack-up)")
    mc = ctx["mc"]
    pdf.tabela(
        ["Método", "Variação no comprimento total"],
        [
            ["Pior caso (aritmético)", f"± {mc['pior_caso']:.2f} mm"],
            ["Estatístico (RSS, 3σ)", f"± {mc['rss']:.2f} mm"],
            [f"Monte Carlo ({mc['n']:,} amostras) — média / desvio-padrão".replace(",", "."),
             f"{mc['media']:.2f} / {mc['sigma']:.3f} mm"],
            ["Probabilidade de conformidade", f"{mc['p_conf'] * 100:.2f} %"],
            ["Índices de capacidade Cp / Cpk", f"{mc['cp']:.2f} / {mc['cpk']:.2f}"],
        ],
        [130, 60], ["L", "C"],
    )

    pdf.secao("6. Parecer de conformidade dimensional")
    d = ctx["diferenca"]
    if status == "CONFORME":
        texto = (f"A montagem atende ao comprimento alvo de {ctx['alvo']:.1f} mm dentro da tolerância de "
                 f"± {ctx['tol_conf']:.1f} mm (diferença de {d:+.1f} mm).")
    elif d > 0:
        texto = f"ATENÇÃO: a montagem está PASSANDO {abs(d):.1f} mm do comprimento alvo ({ctx['alvo']:.1f} mm)."
    else:
        texto = f"ATENÇÃO: a montagem está FALTANDO {abs(d):.1f} mm para o comprimento alvo ({ctx['alvo']:.1f} mm)."
    pdf.set_fill_color(*[int(c + (255 - c) * 0.85) for c in cor_status])
    pdf.set_draw_color(*cor_status)
    pdf.set_text_color(*cor_status)
    pdf.set_font("Helvetica", "B", 9.5)
    pdf.multi_cell(190, 7, _txt(texto), 1, "C", True)

    pdf.ln(14)
    pdf.set_text_color(11, 31, 58)
    pdf.set_draw_color(11, 31, 58)
    pdf.set_font("Helvetica", "", 8.5)
    for i, rotulo in enumerate(["Responsável pelo setup", "Engenharia de processo", "Qualidade"]):
        x = 10 + i * 65
        pdf.line(x, pdf.get_y(), x + 58, pdf.get_y())
        pdf.set_xy(x, pdf.get_y() + 1)
        pdf.cell(58, 5, _txt(rotulo), 0, 0, "C")
        pdf.set_y(pdf.get_y() - 1)

    return bytes(pdf.output())


def gerar_excel(ctx, df_calcos, df_estagios):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame(
            {
                "Indicador": ["Comprimento original", "Folga do flange", "Comprimento alvo",
                              "Comprimento montado", "Diferença", "Tolerância", "Status"],
                "Valor": [ctx["original"], ctx["folga"], ctx["alvo"], ctx["total"], round(ctx["diferenca"], 2),
                          ctx["tol_conf"], classificar(ctx["diferenca"], ctx["tol_conf"])[0]],
            }
        ).to_excel(writer, sheet_name="Resumo", index=False)
        df_calcos.to_excel(writer, sheet_name="Espaçadores", index=False)
        df_estagios.to_excel(writer, sheet_name="Estágios", index=False)
    return buffer.getvalue()


# =============================================================================
# COMPONENTES DE INTERFACE
# =============================================================================
CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"], .stMarkdown, .stTextInput, .stNumberInput, .stSelectbox {{
    font-family: 'Inter', system-ui, sans-serif;
}}
.block-container {{ padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1400px; }}
#MainMenu, footer {{ visibility: hidden; }}

/* ---------- Cabeçalho ---------- */
.hero {{
    background: linear-gradient(120deg, {NAVY_950} 0%, {NAVY_900} 45%, {NAVY_800} 100%);
    border-radius: 14px; padding: 26px 32px; margin-bottom: 22px; color: #fff;
    box-shadow: 0 10px 30px rgba(11,31,58,.18); position: relative; overflow: hidden;
}}
.hero::after {{
    content: ""; position: absolute; right: -60px; top: -60px; width: 260px; height: 260px;
    border-radius: 50%; border: 36px solid rgba(255,255,255,.05);
}}
.hero .tag {{ font-size: .72rem; letter-spacing: .14em; text-transform: uppercase; color: {NAVY_300}; font-weight: 600; }}
.hero h1 {{ color: #fff; font-size: 1.85rem; font-weight: 800; margin: 4px 0 6px 0; padding: 0; letter-spacing: -.01em; }}
.hero p {{ color: #C8D6EB; margin: 0; font-size: .95rem; max-width: 860px; }}

/* ---------- Cartões de indicadores ---------- */
.kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 14px; margin: 4px 0 18px 0; }}
.kpi {{
    background: #fff; border: 1px solid {BORDA}; border-left: 4px solid {NAVY_700};
    border-radius: 10px; padding: 14px 18px; box-shadow: 0 1px 3px rgba(11,31,58,.05);
}}
.kpi .lbl {{ font-size: .72rem; text-transform: uppercase; letter-spacing: .08em; color: {CINZA_TXT}; font-weight: 600; }}
.kpi .val {{ font-size: 1.55rem; font-weight: 800; color: {NAVY_900}; margin-top: 2px; font-variant-numeric: tabular-nums; }}
.kpi .sub {{ font-size: .78rem; color: {CINZA_TXT}; margin-top: 2px; }}

/* ---------- Faixa de status ---------- */
.status {{ border-radius: 10px; padding: 14px 18px; font-weight: 600; margin: 6px 0 12px 0; border: 1px solid; }}

/* ---------- Títulos de seção ---------- */
.sec {{ display:flex; align-items:center; gap:10px; margin: 8px 0 10px 0; }}
.sec .bar {{ width: 4px; height: 22px; background: {NAVY_700}; border-radius: 2px; }}
.sec h3 {{ margin: 0; padding: 0; font-size: 1.08rem; font-weight: 700; color: {NAVY_900}; }}
.sec .hint {{ color: {CINZA_TXT}; font-size: .82rem; margin-left: 4px; }}

/* ---------- Cartões dos calços ---------- */
.calco-head {{ display:flex; align-items:center; gap:8px; font-weight:700; color:{NAVY_900}; margin-bottom: 4px; }}
.calco-dot {{ width: 12px; height: 12px; border-radius: 3px; display:inline-block; }}
.calco-val {{ font-size: .82rem; color: {CINZA_TXT}; margin-top: -4px; }}
.calco-val b {{ color: {NAVY_900}; }}
[data-testid="stVerticalBlockBorderWrapper"] {{ border-color: {BORDA} !important; border-radius: 12px !important; }}

/* ---------- Abas ---------- */
.stTabs [data-baseweb="tab-list"], .stTabs [role="tablist"] {{ gap: 4px; border-bottom: 2px solid {NAVY_100}; }}
.stTabs [data-baseweb="tab"], .stTabs [role="tab"] {{
    height: 44px; padding: 0 18px; background: {NAVY_50}; border-radius: 8px 8px 0 0;
    color: {NAVY_800}; font-weight: 600;
}}
.stTabs [role="tab"] {{ display:flex; align-items:center; }}
.stTabs [aria-selected="true"] {{ background: {NAVY_900} !important; color: #fff !important; }}
.stTabs [aria-selected="true"] p {{ color: #fff !important; }}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"], .stTabs .react-aria-SelectionIndicator {{ display: none; }}

/* ---------- Barra lateral ---------- */
[data-testid="stSidebar"] {{ background: linear-gradient(180deg, {NAVY_950} 0%, {NAVY_900} 100%); }}
[data-testid="stSidebar"] * {{ color: #E6EDF7; }}
[data-testid="stSidebar"] input, [data-testid="stSidebar"] textarea {{ color: {NAVY_900} !important; }}
[data-testid="stSidebar"] [data-testid="stExpander"] {{ border-color: rgba(255,255,255,.15); background: rgba(255,255,255,.03); }}
[data-testid="stSidebar"] [data-testid="stTooltipIcon"] svg, [data-testid="stSidebar"] [data-testid="stTooltipHoverTarget"] svg {{ stroke: {NAVY_300}; color: {NAVY_300}; }}
[data-testid="stSidebar"] hr {{ border-color: rgba(255,255,255,.12); }}
[data-testid="stSidebar"] button {{ background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.25); }}
[data-testid="stSidebar"] button:hover {{ background: rgba(255,255,255,.16); border-color: #fff; }}
[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] {{ background: rgba(255,255,255,.05); }}
[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button {{ color: #fff; }}
.side-brand {{ font-weight: 800; font-size: 1.05rem; letter-spacing: .02em; }}
.side-brand span {{ color: {NAVY_300}; }}

/* ---------- Botões ---------- */
.stButton > button[kind="primary"], .stDownloadButton > button {{
    background: {NAVY_900}; color: #fff; border: 1px solid {NAVY_900}; border-radius: 8px; font-weight: 600;
}}
.stButton > button[kind="primary"]:hover, .stDownloadButton > button:hover {{ background: {NAVY_700}; border-color: {NAVY_700}; color:#fff; }}
.stButton > button {{ border-radius: 8px; font-weight: 600; }}
</style>
"""


def secao(titulo, dica=""):
    st.markdown(
        f'<div class="sec"><div class="bar"></div><h3>{titulo}</h3>'
        f'<span class="hint">{dica}</span></div>',
        unsafe_allow_html=True,
    )


def kpis(itens):
    """itens: lista de (rótulo, valor, subtítulo, cor_destaque)."""
    html = '<div class="kpi-grid">'
    for rot, val, sub, cor in itens:
        html += (f'<div class="kpi" style="border-left-color:{cor}"><div class="lbl">{rot}</div>'
                 f'<div class="val" style="color:{cor if cor != NAVY_700 else NAVY_900}">{val}</div>'
                 f'<div class="sub">{sub}</div></div>')
    st.markdown(html + "</div>", unsafe_allow_html=True)


def faixa_status(texto, cor):
    st.markdown(
        f'<div class="status" style="background:{cor}12;border-color:{cor}55;color:{cor}">{texto}</div>',
        unsafe_allow_html=True,
    )


def estilizar(fig, altura=380, titulo=None, legenda=True):
    fig.update_layout(
        height=altura,
        title=dict(text=titulo, x=0.01, font=dict(size=15, color=NAVY_900)) if titulo else None,
        font=dict(family="Inter, sans-serif", color=NAVY_900, size=12),
        paper_bgcolor="white",
        plot_bgcolor="white",
        margin=dict(l=20, r=20, t=60 if titulo else 30, b=40),
        showlegend=legenda,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=11)),
        hoverlabel=dict(bgcolor=NAVY_900, font_color="white", bordercolor=NAVY_900),
    )
    fig.update_xaxes(gridcolor="#E9EEF5", linecolor=BORDA, zeroline=False)
    fig.update_yaxes(gridcolor="#E9EEF5", linecolor=BORDA, zeroline=False)
    return fig


GRAFICO_CFG = {"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d"]}

# =============================================================================
# ESTADO DA SESSÃO
# =============================================================================
st.set_page_config(page_title="Simulador de Calços — Trefila", page_icon="⚙️", layout="wide",
                   initial_sidebar_state="expanded")
st.markdown(CSS, unsafe_allow_html=True)


def _inicializar_estado():
    padroes = {
        "folga": 0.0, "tol_conf": 0.5, "original": COMPRIMENTO_ORIGINAL_PADRAO,
        "base_ini": BASE_INICIAL_PADRAO, "tol_calco": 0.10, "tol_postico": 0.20, "n_mc": 20000,
    }
    for i, e in enumerate(ESTAGIOS):
        padroes[f"base_{i}"] = BASES_PADRAO[e]
    for i in range(N_CALCOS):
        padroes[f"esp_{i}"] = ESPESSURAS_PADRAO[i]
        padroes[f"pos_{i}"] = ESTAGIOS[i]
    for k, v in padroes.items():
        st.session_state.setdefault(k, v)


def _aplicar_configuracao(dados):
    for k, v in dados.items():
        if k.startswith(("esp_", "pos_", "base_")) or k in ("folga", "tol_conf", "original", "base_ini"):
            st.session_state[k] = v


def _restaurar_padrao():
    for k in list(st.session_state.keys()):
        if k.startswith(("esp_", "pos_", "base_")) or k in ("folga", "tol_conf", "original", "base_ini"):
            del st.session_state[k]


def _aplicar_alocacao(aloc):
    for i, nome in enumerate(NOMES_CALCOS):
        st.session_state[f"pos_{i}"] = aloc[nome]


_inicializar_estado()

# =============================================================================
# BARRA LATERAL — PARÂMETROS
# =============================================================================
with st.sidebar:
    st.markdown('<div class="side-brand">⚙️ CALÇOS <span>· TREFILA</span></div>', unsafe_allow_html=True)
    st.caption("Simulador industrial de setup")
    st.divider()

    st.markdown("**Parâmetros da montagem**")
    st.number_input("Folga para aperto do flange (mm)", step=0.1, format="%.1f", key="folga",
                    help="Somada ao comprimento de projeto original para definir o comprimento alvo.")
    st.number_input("Tolerância de conformidade (± mm)", min_value=0.0, step=0.1, format="%.1f", key="tol_conf",
                    help="Faixa aceitável em torno do comprimento alvo.")

    with st.expander("Dados de projeto (postiços)"):
        st.number_input("Comprimento de projeto original (mm)", step=0.5, format="%.1f", key="original")
        st.number_input("1º Postiço (mm)", step=0.5, format="%.1f", key="base_ini")
        for i, e in enumerate(ESTAGIOS):
            st.number_input(f"{e} (mm)", step=0.5, format="%.1f", key=f"base_{i}")

    with st.expander("Tolerâncias de fabricação"):
        st.number_input("Tolerância dos calços (± mm)", min_value=0.0, step=0.01, format="%.2f", key="tol_calco")
        st.number_input("Tolerância dos postiços (± mm)", min_value=0.0, step=0.01, format="%.2f", key="tol_postico")
        st.select_slider("Amostras Monte Carlo", options=[5000, 10000, 20000, 50000, 100000], key="n_mc")

    st.divider()
    st.markdown("**Configurações salvas**")
    arquivo = st.file_uploader("Carregar configuração (.json)", type="json", label_visibility="collapsed")
    if arquivo is not None and st.session_state.get("_cfg_carregada") != arquivo.file_id:
        try:
            _aplicar_configuracao(json.load(arquivo))
            st.session_state["_cfg_carregada"] = arquivo.file_id
            st.rerun()
        except Exception:
            st.error("Arquivo de configuração inválido.")
    st.button("↺ Restaurar valores padrão", on_click=_restaurar_padrao, width="stretch")

# =============================================================================
# LEITURA DOS PARÂMETROS
# =============================================================================
ss = st.session_state
bases = {e: float(ss[f"base_{i}"]) for i, e in enumerate(ESTAGIOS)}
base_inicial = float(ss["base_ini"])
folga = float(ss["folga"])
tol_conf = float(ss["tol_conf"])
comprimento_original = float(ss["original"])
comprimento_alvo = comprimento_original + folga

# =============================================================================
# CABEÇALHO
# =============================================================================
st.markdown(
    """
    <div class="hero">
      <div class="tag">Engenharia de processo · Trefila</div>
      <h1>Simulador Dinâmico de Calços</h1>
      <p>Configure espessuras e posições dos espaçadores, acompanhe o esquema da montagem em tempo real e
      valide o comprimento do pacote interno com análises dimensionais, de tolerância e de otimização.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

aba_mont, aba_anal, aba_otim, aba_tol, aba_rel = st.tabs(
    ["🔧 Montagem", "📊 Análise dimensional", "🎯 Otimização", "📐 Tolerâncias", "📄 Relatórios"]
)

# =============================================================================
# ABA 1 — MONTAGEM
# =============================================================================
with aba_mont:
    secao("Configuração dos calços", "Aceita operações matemáticas, ex.: 70,5+5")
    calcos, alocacao, entradas_invalidas = {}, {}, []
    colunas = st.columns(N_CALCOS)
    for i, nome in enumerate(NOMES_CALCOS):
        with colunas[i]:
            with st.container(border=True):
                st.markdown(
                    f'<div class="calco-head"><span class="calco-dot" style="background:{CORES_CALCOS[i]}"></span>'
                    f'{nome}</div>',
                    unsafe_allow_html=True,
                )
                texto = st.text_input("Espessura (mm)", key=f"esp_{i}")
                valor, valido = calcular_expressao(texto)
                if not valido:
                    entradas_invalidas.append(nome)
                calcos[nome] = valor
                alocacao[nome] = st.selectbox("Local de alocação", ESTAGIOS,
                                              format_func=lambda x: NOME_DROPDOWN[x], key=f"pos_{i}")
                if not valido:
                    st.markdown(f'<div class="calco-val" style="color:{ERRO}">Expressão inválida → 0,0 mm</div>',
                                unsafe_allow_html=True)
                elif valor <= ESPESSURA_MINIMA:
                    st.markdown(f'<div class="calco-val">Medida: <b>{valor:.1f} mm</b> · desconsiderado</div>',
                                unsafe_allow_html=True)
                else:
                    st.markdown(f'<div class="calco-val">Medida calculada: <b>{valor:.1f} mm</b></div>',
                                unsafe_allow_html=True)

    if entradas_invalidas:
        st.warning("Verifique a espessura de: " + ", ".join(entradas_invalidas))

    distancias, comprimento_total = calcular_montagem(base_inicial, bases, calcos, alocacao)
    diferenca = comprimento_total - comprimento_alvo
    status, cor_status = classificar(diferenca, tol_conf)

    kpis([
        ("Comprimento alvo", f"{comprimento_alvo:.1f} mm", f"Original {comprimento_original:.1f} + folga {folga:.1f}",
         NAVY_700),
        ("Comprimento montado", f"{comprimento_total:.1f} mm", "Postiços + calços ativos", NAVY_700),
        ("Diferença", f"{diferenca:+.1f} mm", f"Tolerância ± {tol_conf:.1f} mm", cor_status),
        ("Status", status, f"{sum(1 for v in calcos.values() if v > ESPESSURA_MINIMA)} de {N_CALCOS} calços ativos",
         cor_status),
    ])

    secao("Representação visual do pacote interno")
    fig = go.Figure()
    eixo = ["Montagem"]

    def _barra(largura, nome, cor, texto, cor_txt, borda=1):
        fig.add_trace(go.Bar(
            y=eixo, x=[largura], name=nome, orientation="h",
            marker=dict(color=cor, line=dict(color=NAVY_900, width=borda)),
            text=texto, textposition="inside", insidetextanchor="middle",
            textfont=dict(color=cor_txt, size=12), hovertemplate=f"<b>{nome}</b><br>%{{x:.1f}} mm<extra></extra>",
        ))

    _barra(base_inicial, "1º Postiço", COR_POSTICO, f"1º Postiço<br>{base_inicial:.1f}", NAVY_900)
    for i, estagio in enumerate(ESTAGIOS):
        for idx, nome in enumerate(NOMES_CALCOS):
            if alocacao[nome] == estagio and calcos[nome] > ESPESSURA_MINIMA:
                _barra(calcos[nome], nome, CORES_CALCOS[idx], f"{idx + 1}º Esp.<br>{calcos[nome]:.1f}",
                       "white" if idx < 3 else NAVY_900, 1.5)
        _barra(bases[estagio], estagio, COR_POSTICO, f"{i + 2}º Postiço<br>{bases[estagio]:.1f}", NAVY_900)

    x_acum = base_inicial
    for estagio in ESTAGIOS:
        fig.add_vline(x=x_acum, line_width=2, line_dash="dash", line_color=NAVY_700)
        fig.add_annotation(x=x_acum + distancias[estagio] / 2, y=1.04, yref="paper", yanchor="bottom",
                           text=f"<b>{NOME_TABELA[estagio]}</b><br>{distancias[estagio]:.1f} mm",
                           showarrow=False, font=dict(color=NAVY_800, size=12))
        x_acum += distancias[estagio]
    fig.add_vline(x=comprimento_alvo, line_width=2, line_color=cor_status)
    fig.add_annotation(x=comprimento_alvo, y=-0.18, yref="paper", text=f"Alvo {comprimento_alvo:.1f}",
                       showarrow=False, font=dict(color=cor_status, size=11), xanchor="right")
    estilizar(fig, altura=320, legenda=False)
    fig.update_layout(barmode="stack", yaxis_visible=False, xaxis_title="Comprimento acumulado (mm)",
                      margin=dict(l=10, r=10, t=80, b=50), bargap=0.25)
    st.plotly_chart(fig, width="stretch", config=GRAFICO_CFG)

    if status == "CONFORME":
        faixa_status(f"✔ Montagem conforme — diferença de {diferenca:+.1f} mm, dentro da tolerância de "
                     f"± {tol_conf:.1f} mm.", OK)
    elif diferenca > 0:
        faixa_status(f"⚠ A montagem está PASSANDO {abs(diferenca):.1f} mm do comprimento alvo "
                     f"({comprimento_alvo:.1f} mm). Consulte a aba Otimização para sugestões de correção.", ERRO)
    else:
        faixa_status(f"⚠ A montagem está FALTANDO {abs(diferenca):.1f} mm para o comprimento alvo "
                     f"({comprimento_alvo:.1f} mm). Consulte a aba Otimização para sugestões de correção.", ALERTA)

    secao("Distância entre anéis de redução")
    df_estagios = pd.DataFrame({
        "Estágio": [NOME_TABELA[e] for e in ESTAGIOS],
        "Postiço (mm)": [bases[e] for e in ESTAGIOS],
        "Calços (mm)": [distancias[e] - bases[e] for e in ESTAGIOS],
        "Distância final (mm)": [distancias[e] for e in ESTAGIOS],
        "Participação no total (%)": [distancias[e] / comprimento_total * 100 for e in ESTAGIOS],
    })
    st.dataframe(
        df_estagios, hide_index=True, width="stretch",
        column_config={
            "Postiço (mm)": st.column_config.NumberColumn(format="%.1f"),
            "Calços (mm)": st.column_config.NumberColumn(format="%.1f"),
            "Distância final (mm)": st.column_config.NumberColumn(format="%.1f"),
            "Participação no total (%)": st.column_config.ProgressColumn(
                format="%.1f%%", min_value=0, max_value=100),
        },
    )

df_calcos = pd.DataFrame({
    "Espaçador": NOMES_CALCOS,
    "Entrada": [ss[f"esp_{i}"] for i in range(N_CALCOS)],
    "Espessura (mm)": [calcos[n] for n in NOMES_CALCOS],
    "Ativo": [calcos[n] > ESPESSURA_MINIMA for n in NOMES_CALCOS],
    "Posição": [NOME_DROPDOWN[alocacao[n]] for n in NOMES_CALCOS],
})

# =============================================================================
# ABA 2 — ANÁLISE DIMENSIONAL
# =============================================================================
with aba_anal:
    c1, c2 = st.columns([1, 1.6])
    with c1:
        secao("Indicador de desvio")
        faixa = max(3 * tol_conf, abs(diferenca) * 1.3, 2.0)
        gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=round(diferenca, 2),
            number=dict(suffix=" mm", font=dict(size=40, color=cor_status), valueformat="+.1f"),
            gauge=dict(
                axis=dict(range=[-faixa, faixa], tickcolor=NAVY_900),
                bar=dict(color=NAVY_900, thickness=0.28),
                bgcolor="white", borderwidth=1, bordercolor=BORDA,
                steps=[
                    dict(range=[-faixa, -tol_conf], color="#FBEFD5"),
                    dict(range=[-tol_conf, tol_conf], color="#D6F0E3"),
                    dict(range=[tol_conf, faixa], color="#F7DAD6"),
                ],
                threshold=dict(line=dict(color=cor_status, width=4), thickness=0.85, value=diferenca),
            ),
            title=dict(text=f"Diferença em relação ao alvo<br><span style='font-size:12px;color:{CINZA_TXT}'>"
                            f"Zona verde = ± {tol_conf:.1f} mm</span>", font=dict(size=14)),
        ))
        st.plotly_chart(estilizar(gauge, altura=340, legenda=False), width="stretch", config=GRAFICO_CFG)

    with c2:
        secao("Composição do comprimento (cascata)")
        rotulos, valores, cores_txt = ["1º Postiço"], [base_inicial], []
        for i, estagio in enumerate(ESTAGIOS):
            for nome in NOMES_CALCOS:
                if alocacao[nome] == estagio and calcos[nome] > ESPESSURA_MINIMA:
                    rotulos.append(nome.replace("Espaçador", "Esp."))
                    valores.append(calcos[nome])
            rotulos.append(f"{i + 2}º Postiço")
            valores.append(bases[estagio])
        wf = go.Figure(go.Waterfall(
            x=rotulos + ["Total"], y=valores + [0], measure=["relative"] * len(valores) + ["total"],
            text=[f"{v:.1f}" for v in valores] + [f"{comprimento_total:.1f}"], textposition="outside",
            increasing=dict(marker=dict(color=NAVY_500)), totals=dict(marker=dict(color=NAVY_900)),
            connector=dict(line=dict(color=BORDA, width=1)),
            hovertemplate="<b>%{x}</b><br>%{y:.1f} mm<extra></extra>",
        ))
        wf.add_hline(y=comprimento_alvo, line_dash="dot", line_color=cor_status,
                     annotation_text=f"Alvo {comprimento_alvo:.1f} mm", annotation_font_color=cor_status,
                     annotation_position="top left")
        estilizar(wf, altura=340, legenda=False)
        wf.update_yaxes(title="mm", range=[0, max(comprimento_total, comprimento_alvo) * 1.12])
        st.plotly_chart(wf, width="stretch", config=GRAFICO_CFG)

    c3, c4 = st.columns([1.6, 1])
    with c3:
        secao("Distância por estágio — postiço × calços")
        fig_est = go.Figure()
        nomes_est = [NOME_TABELA[e] for e in ESTAGIOS]
        fig_est.add_trace(go.Bar(x=nomes_est, y=[bases[e] for e in ESTAGIOS], name="Postiço",
                                 marker_color=NAVY_100, marker_line=dict(color=NAVY_800, width=1)))
        fig_est.add_trace(go.Bar(x=nomes_est, y=[distancias[e] - bases[e] for e in ESTAGIOS], name="Calços",
                                 marker_color=NAVY_700))
        fig_est.add_trace(go.Scatter(x=nomes_est, y=[distancias[e] for e in ESTAGIOS], mode="text",
                                     text=[f"<b>{distancias[e]:.1f}</b>" for e in ESTAGIOS], textposition="top center",
                                     showlegend=False, textfont=dict(color=NAVY_900)))
        estilizar(fig_est, altura=340)
        fig_est.update_layout(barmode="stack", yaxis_title="mm")
        st.plotly_chart(fig_est, width="stretch", config=GRAFICO_CFG)
    with c4:
        secao("Participação no comprimento")
        soma_calcos = sum(v for v in calcos.values() if v > ESPESSURA_MINIMA)
        donut = go.Figure(go.Pie(
            labels=["Postiços", "Calços"], values=[comprimento_total - soma_calcos, soma_calcos], hole=0.62,
            marker=dict(colors=[NAVY_100, NAVY_900], line=dict(color="white", width=2)),
            textinfo="percent", textfont=dict(size=13), sort=False,
            hovertemplate="<b>%{label}</b><br>%{value:.1f} mm (%{percent})<extra></extra>",
        ))
        donut.add_annotation(text=f"<b>{comprimento_total:.0f}</b><br>mm", showarrow=False,
                             font=dict(size=18, color=NAVY_900))
        st.plotly_chart(estilizar(donut, altura=340), width="stretch", config=GRAFICO_CFG)

    secao("Resumo estatístico dos calços")
    ativos = [v for v in calcos.values() if v > ESPESSURA_MINIMA]
    if ativos:
        kpis([
            ("Soma dos calços", f"{sum(ativos):.1f} mm", f"{len(ativos)} ativos", NAVY_700),
            ("Espessura média", f"{np.mean(ativos):.2f} mm", "Calços ativos", NAVY_700),
            ("Amplitude", f"{max(ativos) - min(ativos):.1f} mm", f"Mín {min(ativos):.1f} · Máx {max(ativos):.1f}",
             NAVY_700),
            ("Desvio-padrão", f"{np.std(ativos, ddof=1) if len(ativos) > 1 else 0:.2f} mm", "Amostral", NAVY_700),
        ])
    else:
        st.info("Nenhum calço ativo na montagem.")

# =============================================================================
# ABA 3 — OTIMIZAÇÃO
# =============================================================================
with aba_otim:
    secao("Correção de espessura sugerida", "Como zerar a diferença em relação ao alvo")
    if abs(round(diferenca, 1)) == 0:
        faixa_status("✔ A montagem já está exatamente no alvo — nenhuma correção necessária.", OK)
    else:
        nomes_ativos = [n for n in NOMES_CALCOS if calcos[n] > ESPESSURA_MINIMA]
        linhas = []
        for n in NOMES_CALCOS:
            nova = calcos[n] - diferenca
            linhas.append({
                "Estratégia": f"Ajustar somente o {n}",
                "Espessura atual (mm)": calcos[n],
                "Espessura necessária (mm)": nova,
                "Ajuste (mm)": -diferenca,
                "Viável": nova > ESPESSURA_MINIMA,
            })
        df_corr = pd.DataFrame(linhas)
        c1, c2 = st.columns([1.6, 1])
        with c1:
            st.dataframe(df_corr, hide_index=True, width="stretch", column_config={
                "Espessura atual (mm)": st.column_config.NumberColumn(format="%.1f"),
                "Espessura necessária (mm)": st.column_config.NumberColumn(format="%.1f"),
                "Ajuste (mm)": st.column_config.NumberColumn(format="%+.1f"),
                "Viável": st.column_config.CheckboxColumn(),
            })
        with c2:
            if nomes_ativos:
                ajuste = -diferenca / len(nomes_ativos)
                st.markdown(f"**Distribuição uniforme** entre os {len(nomes_ativos)} calços ativos:")
                st.dataframe(pd.DataFrame({
                    "Espaçador": nomes_ativos,
                    "Nova espessura (mm)": [calcos[n] + ajuste for n in nomes_ativos],
                }), hide_index=True, width="stretch",
                    column_config={"Nova espessura (mm)": st.column_config.NumberColumn(format="%.2f")})
                st.caption(f"Ajuste de {ajuste:+.2f} mm em cada calço.")

    st.divider()
    secao("Otimização da alocação por estágio", "Busca exaustiva em todas as combinações possíveis")
    st.caption(f"Defina a distância nominal desejada para cada estágio. O algoritmo avalia as "
               f"{len(ESTAGIOS) ** N_CALCOS} combinações de alocação e classifica pelo menor desvio máximo.")
    padrao_dist = calcular_montagem(
        BASE_INICIAL_PADRAO, BASES_PADRAO,
        {n: calcular_expressao(v)[0] for n, v in zip(NOMES_CALCOS, ESPESSURAS_PADRAO)},
        dict(zip(NOMES_CALCOS, ESTAGIOS)))[0]
    cols_alvo = st.columns(len(ESTAGIOS))
    alvos_estagio = {}
    for i, e in enumerate(ESTAGIOS):
        with cols_alvo[i]:
            alvos_estagio[e] = st.number_input(f"Alvo · {NOME_TABELA[e]} (mm)",
                                               value=float(padrao_dist[e] - BASES_PADRAO[e] + bases[e]),
                                               step=0.5, format="%.1f", key=f"alvo_est_{i}")

    resultados = otimizar_alocacao(bases, calcos, alvos_estagio)
    melhor = resultados[0]
    desvios_atuais = np.array([distancias[e] - alvos_estagio[e] for e in ESTAGIOS])
    kpis([
        ("Desvio máximo atual", f"{np.max(np.abs(desvios_atuais)):.1f} mm", "Alocação configurada", NAVY_700),
        ("Desvio máximo otimizado", f"{melhor['max_abs']:.1f} mm", "Melhor alocação encontrada",
         OK if melhor["max_abs"] <= tol_conf else ALERTA),
        ("RMS otimizado", f"{melhor['rms']:.2f} mm", "Raiz do erro quadrático médio", NAVY_700),
        ("Combinações avaliadas", f"{len(resultados)}", "Busca exaustiva", NAVY_700),
    ])

    c1, c2 = st.columns([1.3, 1])
    with c1:
        top = resultados[:10]
        df_top = pd.DataFrame([
            {"#": k + 1, **{n.replace("Espaçador", "Esp."): f"Estágio {ESTAGIOS.index(r['alocacao'][n]) + 1}→{ESTAGIOS.index(r['alocacao'][n]) + 2}" for n in NOMES_CALCOS},
             "Desvio máx. (mm)": r["max_abs"], "RMS (mm)": r["rms"]}
            for k, r in enumerate(top)
        ])
        st.dataframe(df_top, hide_index=True, width="stretch", column_config={
            "Desvio máx. (mm)": st.column_config.NumberColumn(format="%.2f"),
            "RMS (mm)": st.column_config.NumberColumn(format="%.2f"),
        })
        st.button("✓ Aplicar a melhor alocação na montagem", type="primary",
                  on_click=_aplicar_alocacao, args=(melhor["alocacao"],))
    with c2:
        fig_cmp = go.Figure()
        nomes_est = [NOME_TABELA[e] for e in ESTAGIOS]
        fig_cmp.add_trace(go.Bar(x=nomes_est, y=desvios_atuais, name="Atual", marker_color=NAVY_300))
        fig_cmp.add_trace(go.Bar(x=nomes_est, y=melhor["desvios"], name="Otimizada", marker_color=NAVY_900))
        if tol_conf > 0:
            fig_cmp.add_hrect(y0=-tol_conf, y1=tol_conf, fillcolor=OK, opacity=0.08, line_width=0)
        estilizar(fig_cmp, altura=360, titulo="Desvio por estágio (mm)")
        fig_cmp.update_layout(barmode="group")
        st.plotly_chart(fig_cmp, width="stretch", config=GRAFICO_CFG)

# =============================================================================
# ABA 4 — TOLERÂNCIAS
# =============================================================================
tol_calco, tol_postico, n_mc = float(ss["tol_calco"]), float(ss["tol_postico"]), int(ss["n_mc"])
contribuicoes = {"1º Postiço": tol_postico}
contribuicoes.update({e: tol_postico for e in ESTAGIOS})
contribuicoes.update({n: tol_calco for n in NOMES_CALCOS if calcos[n] > ESPESSURA_MINIMA})
pior_caso = sum(contribuicoes.values())
rss = float(np.sqrt(sum(t**2 for t in contribuicoes.values())))
total_sim, estagios_sim = simular_monte_carlo(base_inicial, bases, calcos, alocacao, tol_calco, tol_postico, n_mc)
lie, lse = comprimento_alvo - tol_conf, comprimento_alvo + tol_conf
mu, sigma = float(total_sim.mean()), float(total_sim.std(ddof=1))
p_conf = float(np.mean((total_sim >= lie) & (total_sim <= lse)))
cp = (lse - lie) / (6 * sigma) if sigma > 0 else float("inf")
cpk = min(lse - mu, mu - lie) / (3 * sigma) if sigma > 0 else float("inf")

with aba_tol:
    st.caption("Tolerâncias de fabricação configuradas na barra lateral. Considera-se tolerância = ±3σ "
               "(distribuição normal) para a simulação estatística.")
    kpis([
        ("Pior caso (aritmético)", f"± {pior_caso:.2f} mm", f"{len(contribuicoes)} componentes no empilhamento",
         NAVY_700),
        ("Estatístico (RSS)", f"± {rss:.2f} mm", "Raiz da soma dos quadrados", NAVY_700),
        ("Prob. de conformidade", f"{p_conf * 100:.2f} %", f"LIE {lie:.1f} · LSE {lse:.1f} mm",
         OK if p_conf >= 0.9973 else (ALERTA if p_conf >= 0.95 else ERRO)),
        ("Cp / Cpk", f"{cp:.2f} / {cpk:.2f}", "Capacidade (≥ 1,33 recomendado)",
         OK if cpk >= 1.33 else (ALERTA if cpk >= 1.0 else ERRO)),
    ])

    c1, c2 = st.columns([1.6, 1])
    with c1:
        secao("Distribuição Monte Carlo do comprimento total", f"{n_mc:,} amostras".replace(",", "."))
        hist = go.Figure()
        hist.add_trace(go.Histogram(x=total_sim, nbinsx=70, marker_color=NAVY_700, opacity=0.85,
                                    name="Simulação", hovertemplate="%{x:.2f} mm<br>%{y} amostras<extra></extra>"))
        if sigma > 0:
            xs = np.linspace(total_sim.min(), total_sim.max(), 300)
            larg = (total_sim.max() - total_sim.min()) / 70
            pdf_n = n_mc * larg * np.exp(-0.5 * ((xs - mu) / sigma) ** 2) / (sigma * np.sqrt(2 * np.pi))
            hist.add_trace(go.Scatter(x=xs, y=pdf_n, mode="lines", line=dict(color=NAVY_950, width=2.5),
                                      name="Normal ajustada"))
        for x, rot, cor in [(lie, "LIE", ERRO), (lse, "LSE", ERRO), (comprimento_alvo, "Alvo", OK)]:
            hist.add_vline(x=x, line_dash="dash" if rot != "Alvo" else "solid", line_color=cor, line_width=2,
                           annotation_text=rot, annotation_font_color=cor, annotation_position="top")
        estilizar(hist, altura=380)
        hist.update_layout(xaxis_title="Comprimento total (mm)", yaxis_title="Frequência", bargap=0.02)
        st.plotly_chart(hist, width="stretch", config=GRAFICO_CFG)
    with c2:
        secao("Sensibilidade (contribuição na variância)")
        var_total = sum(t**2 for t in contribuicoes.values())
        df_sens = pd.DataFrame({
            "Componente": list(contribuicoes.keys()),
            "Contribuição (%)": [(t**2 / var_total * 100) if var_total > 0 else 0 for t in contribuicoes.values()],
        }).sort_values("Contribuição (%)")
        tornado = go.Figure(go.Bar(
            x=df_sens["Contribuição (%)"], y=df_sens["Componente"], orientation="h",
            marker_color=[NAVY_900 if "Esp" in c else NAVY_300 for c in df_sens["Componente"]],
            text=[f"{v:.1f}%" for v in df_sens["Contribuição (%)"]], textposition="outside",
            hovertemplate="<b>%{y}</b><br>%{x:.1f}% da variância<extra></extra>",
        ))
        estilizar(tornado, altura=380, legenda=False)
        tornado.update_xaxes(title="% da variância total", range=[0, df_sens["Contribuição (%)"].max() * 1.25 + 1])
        st.plotly_chart(tornado, width="stretch", config=GRAFICO_CFG)

    secao("Variação simulada da distância por estágio")
    box = go.Figure()
    for i, e in enumerate(ESTAGIOS):
        amostra = estagios_sim[e][:5000]
        box.add_trace(go.Box(y=amostra - distancias[e], name=NOME_TABELA[e], marker_color=CORES_CALCOS[i],
                             boxmean="sd", line=dict(width=1.5)))
    estilizar(box, altura=340, legenda=False)
    box.update_yaxes(title="Desvio em relação ao nominal (mm)")
    st.plotly_chart(box, width="stretch", config=GRAFICO_CFG)

# =============================================================================
# ABA 5 — RELATÓRIOS
# =============================================================================
contexto = {
    "base_inicial": base_inicial, "bases": bases, "calcos": calcos, "alocacao": alocacao,
    "distancias": distancias, "folga": folga, "original": comprimento_original, "alvo": comprimento_alvo,
    "total": comprimento_total, "diferenca": diferenca, "tol_conf": tol_conf,
    "mc": {"pior_caso": pior_caso, "rss": rss, "n": n_mc, "media": mu, "sigma": sigma,
           "p_conf": p_conf, "cp": cp, "cpk": cpk},
}

with aba_rel:
    secao("Exportação de documentos")
    c1, c2, c3 = st.columns(3)
    carimbo = datetime.now().strftime("%Y%m%d_%H%M")
    with c1:
        with st.container(border=True):
            st.markdown("**📄 Relatório técnico (PDF)**")
            st.caption("Esquema da montagem, tabelas, análise de tolerâncias, parecer de conformidade e "
                       "campos de assinatura.")
            assinatura = repr(sorted((k, repr(v)) for k, v in contexto.items()))
            if st.button("Gerar relatório PDF", type="primary", width="stretch"):
                with st.spinner("Compilando relatório técnico..."):
                    st.session_state["_pdf"] = (assinatura, gerar_pdf(contexto))
            pdf_salvo = st.session_state.get("_pdf")
            if pdf_salvo and pdf_salvo[0] == assinatura:
                st.download_button("📥 Baixar PDF", pdf_salvo[1],
                                   file_name=f"relatorio_setup_calcos_{carimbo}.pdf", mime="application/pdf",
                                   width="stretch")
    with c2:
        with st.container(border=True):
            st.markdown("**📊 Planilha de dados (Excel)**")
            st.caption("Resumo, configuração dos espaçadores e distâncias por estágio em abas separadas.")
            st.download_button("📥 Baixar Excel", gerar_excel(contexto, df_calcos, df_estagios),
                               file_name=f"setup_calcos_{carimbo}.xlsx", width="stretch",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    with c3:
        with st.container(border=True):
            st.markdown("**💾 Configuração (JSON)**")
            st.caption("Salve este setup e recarregue-o depois pela barra lateral.")
            chaves = (["folga", "tol_conf", "original", "base_ini"] + [f"base_{i}" for i in range(len(ESTAGIOS))]
                      + [f"esp_{i}" for i in range(N_CALCOS)] + [f"pos_{i}" for i in range(N_CALCOS)])
            st.download_button("📥 Baixar configuração",
                               json.dumps({k: ss[k] for k in chaves}, ensure_ascii=False, indent=2),
                               file_name=f"config_calcos_{carimbo}.json", mime="application/json",
                               width="stretch")

    secao("Pré-visualização dos dados")
    st.dataframe(df_calcos, hide_index=True, width="stretch", column_config={
        "Espessura (mm)": st.column_config.NumberColumn(format="%.1f"),
        "Ativo": st.column_config.CheckboxColumn(),
    })

st.markdown(
    f'<div style="text-align:center;color:{CINZA_TXT};font-size:.78rem;margin-top:28px;">'
    f'Simulador Industrial de Calços · Pacote Interno de Trefila</div>',
    unsafe_allow_html=True,
)
