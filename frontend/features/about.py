"""Tela 'Como funciona': transparência sobre a IA, privacidade e limites."""
import streamlit as st


def render() -> None:
    st.markdown("""
#### Como a Zela funciona
1. **Você descreve** o problema da sua rua, com suas palavras.
2. **O assistente de IA** sugere o tipo de problema, a urgência e quem deve cuidar, e avisa se já há relatos parecidos por perto.
3. **Você confere** e corrige se precisar. Nada vai para a prefeitura sem a sua confirmação.
4. **Você recebe um protocolo** e acompanha o andamento em *Meus relatos*.

Se o assistente estiver fora do ar, você ainda pode **registrar o relato sozinho**: ele não se perde.

#### O que a Zela **não** faz
- Não substitui serviços de emergência. **Risco à vida: ligue 193 (Bombeiros), 199 (Defesa Civil) ou 190 (Polícia).**
- Não garante prazo de atendimento: os prazos mostrados são metas de primeira resposta.
- Não toma decisões sozinha: a IA só sugere; cidadão e equipe da prefeitura decidem.

#### Sua privacidade
- Removemos CPF, e-mail e telefone do texto **antes** de enviar à IA.
- O painel da cidade mostra apenas tipo, urgência, bairro e data: nunca o texto do relato.
- Você só vê os relatos dos protocolos que possui. Eles ficam guardados no endereço desta página, no seu navegador.
""")
