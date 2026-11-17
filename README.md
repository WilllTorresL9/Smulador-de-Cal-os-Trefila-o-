# Simulador Dinâmico de Calços — Trefila

Aplicação Streamlit para setup do pacote interno de trefila: configuração de espaçadores (calços),
visualização da montagem em tempo real e validação do comprimento total.

## Recursos
- **Montagem** — entrada de espessuras (aceita expressões, ex.: `70,5+5`), alocação por estágio, esquema gráfico e distâncias entre anéis.
- **Análise dimensional** — indicador de desvio, gráfico em cascata, distância por estágio e participação postiços × calços.
- **Otimização** — sugestão de correção de espessura e busca exaustiva da melhor alocação frente a alvos por estágio.
- **Tolerâncias** — empilhamento pior caso e RSS, simulação Monte Carlo com probabilidade de conformidade, Cp/Cpk e sensibilidade.
- **Relatórios** — PDF técnico, planilha Excel e configuração JSON (recarregável pela barra lateral).

## Execução
```bash
pip install -r requirements.txt
streamlit run app_calcos.py
```
