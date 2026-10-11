"""TODOS os seletores do OtxIdle (confirmados ao vivo em 11/10/2026). Se o HTML mudar, e' so' aqui.
Muitos botoes sao do Mantine sem classe propria: esses sao achados pelo TEXTO (constantes *_TEXT)."""

# --- identidade / HUD
NAME = ".gs-me .name"
LEVEL = ".gs-me .lvl"
VOCATION = ".gs-right .voc"
CAP = ".gs-goldrow .cap"                 # "CAP. 224" = capacidade LIVRE
GOLD = ".gs-goldrow .gold"
TOOLTIP = ".mantine-Tooltip-tooltip"     # hover no CAP: "Capacidade livre: 36 de 570 oz"
STAMINA_HUNT_BAR = '.ta-bar[aria-label="Stamina de caça restante"]'
STAMINA_TRAIN_BAR = '.ta-bar[aria-label="Stamina de treino restante"]'
PARTY_CHIP = ".gs-chip.gs-party"         # aria-label "Party: 4 de 4 membros"

# --- caçando
HUNT_PANEL = "section.hb-panel"          # "Caçando / <nome> / Tempo de caça ..."
HUNT_NAME = "section.hb-panel .gs-panelhead p"
FINISH_TEXT = "Finalizar Hunt"
LEAVING_TEXT = "Saindo em"               # "Saindo em 4s…" (5s, nao clicar de novo)

# --- treino
TRAIN_PANEL = "section.ta"               # aria "Analisador de Treino"
END_TRAIN_TEXT = "End Training"

# --- cidade
PLAY = "button.gs-cta.gs-cta-play"       # "JOGAR / EXPLORAR"
PILL = ".gs-pill"                        # VENDER / LOJA DE ITENS / PARTY FINDER
SELL_TEXT = "VENDER"

# --- modais (Mantine). Ha varios .mantine-Modal-root vazios sempre no DOM: usar o conteudo.
MODAL = ".gm-modal"
DRAWER = ".gm-panel"                     # gaveta de detalhe da caça
GM_TAB = "button.gm-tab"                 # HUNTS / TRAINING / ...
GM_CARD = "button.gm-card"               # card de caça / treino ("Nome\nLEVEL ...")
HUNT_SEARCH = 'input[placeholder="Buscar caças"]'
START_HUNT = "button.gs-cta"             # dentro da gaveta: "COMEÇAR A CAÇA"
START_HUNT_TEXT = "COMEÇAR A CAÇA"

# venda rapida: VENDER -> SELECIONAR TUDO -> VENDER -> confirmar "VENDER ITENS" -> VENDER
SELL_ALL = ".qs-all"                     # "SELECIONAR TUDO" / "DESMARCAR TUDO"
SELL_ITEM = ".ti-slot"
SELL_CONCLUDE = ".ab-conclude"
CONFIRM = ".ti-confirm"
CANCEL = ".ti-cancel"

# party e amigos (chip Amigos)
FRIENDS_CHIP = 'button.gs-chip[aria-label="Amigos"]'
PARTY_SECTION = ".pt-section"
PARTY_COUNT = ".pt-count"                # "4 / 4"
PARTY_ROW = ".pt-row"                    # ".pt-who": "Nome · Líder (você)\nLevel 12 · Knight"
PARTY_CREATE_TEXT = "Criar party"
FRIEND_ROW = ".fr-row"                   # b = nome, small = "Level 9 · Druid", .fr-place.is-town = "Na cidade"
FRIEND_INVITE = ".fr-accept"             # "CONVIDAR" (o outro .fr-accept e' MENSAGEM; .fr-decline REMOVER: nunca)
INVITE_TITLE = "CONVITE DE PARTY"        # modal no convidado: "<Lider> Level N convidou você..." -> ENTRAR
INVITE_ACCEPT = ".pt-send.ti-confirm"
PARTY_ADD = ".pt-add"                    # input "Nome do personagem" + .pt-send "Convidar" (convida SEM ser amigo)
PARTY_SEND = ".pt-send"                  # "Criar party" / "Convidar"
PARTY_LEAVE = ".pt-section .pt-decline"  # lider "DESFAZER PARTY" / membro "SAIR DA PARTY" (sem confirmacao)

# tasks (chip Quadro de Tasks)
TASKS_CHIP = 'button.gs-chip[aria-label="Quadro de Tasks"]'
TASK_TAB = ".tb-tab"
TASK_DAILY_TEXT = "TASKS DIÁRIAS"
TASK_CARD = ".tb-card"                   # .tb-banner b = criatura, .tb-kills "3/183 abates", .tb-rewards .rw (img alt)
TASK_SELECT = ".tb-select"               # "Selecionar task" / "Em progresso" (disabled) / "COMPLETAR"
TASK_DIFF = ".tb-diffbtn"                # INICIANTE / ADEPTO / EXPERIENTE / MESTRE (is-on; vale no proximo reroll)
TASK_REROLL = ".tb-btn.primary"          # REROLAR (gasta 1 token, sem confirmacao)
TASK_TRACKER_TOOL = '.gs-tool[aria-label="Rastreador de Tasks"]'
