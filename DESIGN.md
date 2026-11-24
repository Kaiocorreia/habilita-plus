# DESIGN.md — Habilita+

Sistema visual do Habilita+. Toda tela segue este arquivo; os valores vivem como variáveis
CSS em `app/static/css/style.css` (`:root`), e o CSS usa os nomes, nunca os valores.

## Direção

**Referência escolhida: Uber.** Preto e branco, um único formato de ação (a pílula), títulos
firmes em peso 700 e quase nenhuma sombra. Para um app de mobilidade usado no celular, no
meio do dia, por gente que às vezes tem baixa visão ou dislexia, isso dá o máximo de
contraste com o mínimo de ruído: o botão preto é sempre "a próxima ação".

Comparadas (fontes gratuitas, sem UXKIN):

| | Uber | Airbnb | Lyft |
|---|---|---|---|
| Fonte | [awesome-design-md/uber](https://github.com/VoltAgent/awesome-design-md/tree/main/design-md/uber) (MIT) | [awesome-design-md/airbnb](https://github.com/VoltAgent/awesome-design-md/tree/main/design-md/airbnb) (MIT) | CSS público do lyft.com (`coreui/base.css`) |
| Cor de ação | Preto `#000` | Rausch `#FF385C` | Magenta `#FF00BF` / `#820076` |
| Paleta | P&B + cinzas | Branco + 1 coral | Muitas cores vivas + pastéis |
| Raio | Pílula 999px; cartões 16px | Botões 8px; cartões 14px | Pílula 48px; cartões 16px |
| Sombra | Quase nenhuma | Uma só | 8 níveis |

- **Por que não Airbnb:** o coral exigiria trocar a identidade azul inteira e é fraco para
  texto (`#FF385C` dá 3,5:1 no branco). Ficaram dois padrões de marketplace que o
  Habilita+ já usa e agora seguem a mesma regra: cartão de reserva fixo (à direita no
  desktop, barra inferior no celular) e dia selecionado do calendário em círculo preto.
- **Por que não Lyft:** muitas cores vivas competem com os selos de estado (agendado,
  confirmado, concluído), que precisam ser lidos pela cor.

**O que muda da Uber:** o Habilita+ mantém o azul da marca como **único acento**, só para
links, foco do teclado e o "+" do logotipo. A Uber não tem acento; aqui ele separa "isto é
um link / estou com o foco aqui" de "isto está selecionado" (preto), o que ajuda quem
navega por teclado.

## Cor

| Token | Valor | Papel | Contraste |
|---|---|---|---|
| `--tinta` | `#000000` | Botão primário, seleção, títulos, texto principal | 21:1 no branco |
| `--sobre-tinta` | `#FFFFFF` | Texto sobre preto | 21:1 |
| `--fundo` / `--superficie` | `#FFFFFF` | Página e cartões | — |
| `--superficie-2` | `#F3F3F3` | Campos, chips, faixas suaves, seleção | — |
| `--superficie-3` | `#EFEFEF` | Botão secundário (pílula cinza), hover | — |
| `--pressionado` | `#E2E2E2` | Estado pressionado de pílulas claras | — |
| `--texto-2` | `#5E5E5E` | Texto de apoio | ≥ 5,0:1 em todas as superfícies claras |
| `--texto-3` | `#6B6B6B` | Metadados, legendas (nunca sobre `#E2E2E2`) | ≥ 4,6:1 até `#EFEFEF` |
| `--borda` | `#E2E2E2` | Divisórias e contorno de cartões (decorativo) | — |
| `--borda-campo` | `#858585` | Contorno de campos, rádios e caixas de seleção | ≥ 3,3:1 (WCAG 1.4.11) |
| `--marca` | `#1D4ED8` | Links, anel de foco, "+" do logotipo | 6,0:1 em `#F3F3F3` |
| `--marca-suave` | `#EEF3FE` | Fundo do aviso informativo | — |
| `--sucesso` / `--alerta` / `--perigo` | `#067647` / `#B54708` / `#B42318` | Selos de estado e mensagens, sempre com texto | ≥ 4,7:1 nos fundos suaves |
| `--estrela` | `#000000` | Estrelas de avaliação (como no Airbnb) | 21:1 |

Regras: um botão preto por bloco visível; o azul nunca preenche botões; cor de estado
nunca é o único sinal (sempre há texto ou ícone).

## Tipografia

Fonte do sistema (`system-ui`, Segoe UI, SF Pro, Roboto). A Uber usa a Uber Move, que é
proprietária; uma webfont exigiria abrir a CSP (`font-src 'self'`) ou hospedar arquivo
novo, e a do sistema carrega instantaneamente e funciona offline no PWA.

| Token | Tamanho / altura | Peso | Uso |
|---|---|---|---|
| `--tipo-display` | `clamp(36px, 7vw, 52px)` / 1.15 | 700 | Título da página de entrada |
| `--tipo-h1` | 28px → 36px (≥ 680px) / 1.2 | 700 | Título de página |
| `--tipo-h2` | 24px / 1.25 | 700 | Seções |
| `--tipo-h3` | 20px / 1.3 | 700 | Títulos de cartão |
| `--tipo-corpo-lg` | 18px / 1.4 | 500 | Texto de abertura |
| `--tipo-corpo` | 16px / 1.5 | 400 | Corpo (mínimo para parágrafos) |
| `--tipo-legenda` | 14px / 1.45 | 400–500 | Metadados, rótulos |
| `--tipo-mini` | 12px / 1.35 | 600 | Selos e rótulos da barra inferior |

Princípios: títulos em caixa normal (sem caixa-alta), sem espaçamento negativo entre
letras, 700 só em títulos, 600 em botões e ênfase. Sobretítulos em caixa-alta são a única
exceção, e são raros.

## Espaçamento

Base de 4px: `--esp-1` 4 · `--esp-2` 8 · `--esp-3` 12 · `--esp-4` 16 · `--esp-5` 20 ·
`--esp-6` 24 · `--esp-8` 32 · `--esp-12` 48 · `--esp-16` 64.
Conteúdo com até 1120px, margens de 16px no celular e 24px a partir de 680px. Cartões com
16–24px de respiro interno; seções separadas por 32px (app) ou 64px (página de entrada).

## Forma e profundidade

| Token | Valor | Uso |
|---|---|---|
| `--raio-sm` | 8px | Campos, horários, miniaturas |
| `--raio` | 12px | Cartões pequenos, opções |
| `--raio-lg` | 16px | Cartões, painéis |
| `--raio-pilula` | 999px | Todo elemento interativo: botões, chips, selos, abas |
| `--sombra-1` | `0 4px 16px rgba(0,0,0,.12)` | Hover de cartões, busca rápida, cartão de agendar |
| `--sombra-2` | `0 2px 8px rgba(0,0,0,.16)` | Elementos flutuantes (segmentado ativo) |

Padrão é **plano**: cartões com borda de 1px e sem sombra. A faixa preta (inversão de
polaridade) é o recurso de destaque, não a sombra.

## Componentes

- **Botão primário:** pílula preta, texto branco, 48px de altura (56px no grande), peso
  600. Hover `#282828`, pressionado escala 0,985.
- **Botão secundário:** pílula cinza `--superficie-3`, texto preto; hover `--pressionado`.
- **Botão claro:** pílula branca, para usar sobre faixas pretas.
- **Fantasma / link:** sem fundo; o fantasma ganha pílula cinza no hover, o link sublinha.
- **Desativado:** opacidade 0,5 e cursor bloqueado.
- **Campos:** fundo `--superficie-2`, borda 1px `--borda-campo`, raio 8px, 48px de altura,
  16px de fonte (evita zoom no iOS). Foco: borda preta + anel azul de 3px.
- **Opções, chips, horários e dias:** seleção = preto (borda de 2px ou fundo preto com
  texto branco). Foco = anel azul. Os dois nunca se confundem.
- **Cartões:** branco, borda `--borda`, raio 16px, sem sombra; com link, ganham
  `--sombra-1` no hover.
- **Navegação:** barra superior branca e opaca; link ativo em pílula cinza. Barra
  inferior (celular) com o ativo em preto e indicador de 3px em cima.
- **Rodapé público:** faixa preta, texto branco e cinza claro (`#AFAFAF`, 9,6:1).
- **Chamada "É instrutor?":** faixa preta com botão claro.
- **Selos de estado:** pílula com fundo suave e texto na cor do estado.

## Imagem e ícones

Um só conjunto de ícones: o sprite SVG de traço em `_icones.html` (traço 2px, 24px).
Fotos de instrutores sempre em círculo; veículos em ilustração SVG sobre `--superficie-2`.
Sem gradientes, sem emoji, sem ilustração genérica.

## Acessibilidade (inegociável)

WCAG 2.2 AA: texto ≥ 4,5:1, componentes e foco ≥ 3:1, alvos ≥ 44×44px, foco nunca escondido
pelas barras fixas (`scroll-padding`), `prefers-reduced-motion` respeitado, sem estilo
inline (a CSP bloqueia `style=""`).
