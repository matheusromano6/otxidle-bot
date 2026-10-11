# CLAUDE.md - otxidle_bot

Bot do **OtxIdle** (otxidle.com.br/play/, MMORPG idle estilo Tibia) que roda **dentro do IdleDeck**, igual ao bot do
Huntera. Projeto NOVO e SEPARADO: nao misturar com `matheusromano6/huntera-bot` (versoes, releases, config).

## Ponto de partida
- Use o bot do Huntera como MODELO de arquitetura (C:\Users\Pichau\huntera-bot, leia o CLAUDE.md de la):
  idledeck.py/launcher.py (conexao CDP porta 9224 e abrir o IdleDeck com a porta), runner.py (thread), updater.py
  (botao Atualizar via GitHub releases), gui.py (CustomTkinter + bandeja), paths.py, config.py, memory.py,
  build com PyInstaller e o processo de release.
- O que MUDA: seletores, leitura de estado e as acoes do jogo. Mapear AO VIVO antes de codar (so leitura primeiro).
- Regra de ouro: so agir em paginas `otxidle.com.br`; NUNCA tocar nas paginas do Huntera (o bot do Huntera roda no mesmo
  IdleDeck/porta) nem de outros jogos. NUNCA matar processos do IdleDeck a forca.

## Primeira olhada (11/10/2026, so leitura)
- 4 paginas `https://otxidle.com.br/play/` no IdleDeck (abas: kina, pally, sorc, druid). Personagens: MR Kina (Premium 29d),
  The Bala Pally, MestreEscuro (sorc), InvocadorDruid.
- Mapa/criaturas em canvas (2 canvas), mas o HUD e' HTML: `.gs-chip`, `.gs-premium`, `.gs-store` (Store), `.gs-coins`,
  `.gs-mini`, `.cp-stambuy` ('+2h' stamina), `.ti-slot` (`.is-empty`), `.gs-planbtn`. Nomes das criaturas e magias aparecem
  no texto da pagina.

## Ambiente deste PC
- Python 3.12 em %LOCALAPPDATA%\Programs\Python\Python312 (nao esta no PATH: chamar pelo caminho completo), com playwright,
  customtkinter, pillow, pystray, pyinstaller. Git em C:\Program Files\Git\cmd, gh em C:\Program Files\GitHub CLI (logado
  como matheusromano6). Identidade git nao configurada: commits com -c user.name="Matheus Romano"
  -c user.email="matheus.romano@manyminds.com.br".
- Usuario fala portugues; prefere mapear o jogo primeiro e implementar depois, com objetividade.

## Estrutura (v1.0.0, `otxidle_bot/`)
- `selectors.py` (TODOS os seletores), `account.py` (read() -> State em 1 evaluate; acoes: finish_hunt, sell_all,
  start_hunt, start_training, end_training, open_friends/invite/accept_invite), `engine.py` (grupos party/solo, gatilhos,
  ciclos), `config.py`, `memory.py` (ultima caça/modo por grupo + contas vistas), `idledeck.py`/`launcher.py`/`updater.py`/
  `paths.py` (copiados do Huntera), `runner.py`, `gui.py` (abas Contas/Regras/Party/Treino/Log + bandeja), `__main__.py` (--status).
- Testes: `python -m unittest discover -s tests` (contas falsas simulam o jogo). Nomes reais NAO entram nos testes.
- Capacidade: o max vem do tooltip (hover no CAP, relido a cada 10 min/level). Depois de vender o bot guarda o "piso"
  (% que sobra: equipamento/pouch; ~30-47% nesses personagens) e so' sai de novo com limite E piso+10 (evita loop).
- Teste ao vivo 11/10: party de 4 (Kina lider) em Folda Icefields, ciclo de capacidade completo (sair -> 4 vendas -> voltar).

## v2.0.0 - tasks diarias + grupos dinamicos (11/10/2026)
- Decisoes do usuario: 2 tasks Adepto por dia por conta; quem termina AJUDA quem falta (party, se o level deixar; senao solo
  na melhor caça do level); quando TODAS terminam -> party configurada na `party.hunt`; plano mudou -> reagrupa NA HORA.
  Dia vira em `tasks.reset_hour` (0h, palpite do usuario). Abates de task contam pra todos da party (usuario).
- `tasks.py` (puro): parse_board/parse_tracker, hunt_for (maior rec_level <= level; senao a mais facil com min <= level),
  choose_card (caça possivel + min_xp_per_kill; prefere caça de outra conta, depois XP/abate), plan (grupos por caça de
  task respeitando 2/3 e 4 por party; ajudantes; fase de party), levels_ok.
- Engine: _task_upkeep por conta (abre o quadro so' quando: 1a vez no dia, rastreador cheio, task trocada na mao, ou na
  cidade sem task) -> _board (COMPLETAR, reroll na dificuldade, escolhe, ate max_rerolls; sem carta/token = 'stuck').
  Grupos vem do plano; _mismatch (caça/tamanho da party diferente, 2 leituras seguidas) -> _leave + _town + _fix_party.
  Treino agora e' POR CONTA (memory 'training'), fora do plano ate recuperar.
- VALIDADO ao vivo: membro "Finalizar Hunt" -> so' ele volta e SAI da party (party de 2 se desfaz; lider segue caçando).
  Convite pelo NOME (`.pt-add` input + `.pt-send` Convidar, com party criada por "Criar party") funciona SEM amizade.
  v2 rodando: leu os 4 quadros, plano = Kina+Pally+Sorc (Orc Camp) e Druid solo (Spider Nest), ciclo de capacidade ok.
- Ainda NAO visto ao vivo com o bot: entrega automatica + reroll + reagrupar; fase de party; virada do dia; "COLETAR DIÁRIO".
- memory.json: `tasks` {day, accounts{nome: done, creature, hunt, stuck, checked, tracker_tried}}, `training` [nomes].

## Mapa do HUD (11/10/2026, ao vivo, so leitura, as 4 contas CAÇANDO solo)
- Identidade: `.gs-topbar` innerText = "OtxIdle\n<level>\n<Nome>\n[29d]\nStore\n<coins> +" (3a linha = nome).
- Caçando: `section.hb-panel[aria-label="Caça atual"]`: `.ti-section-label` "Caçando" + `p` com o nome da caça (ex: "Bone Crypt",
  "Spider Nest") + "Tempo de caça: hh:mm:ss". Botoes (Mantine, sem classe propria -> achar por texto/aria): `[aria-label="Ajustes da caça"]`,
  "Despachar" (disabled = em intervalo/nada), "Finalizar Hunt".
- Stamina: `.gs-vitalbars` -> `.ta-bar[aria-label="Stamina de caça restante"]` (scaleX do `<i>` = fracao) e o texto "hh:mm" logo antes;
  `[aria-label="Stamina de treino restante"]` separado ("TREINO 12:00", parece cheio = 12h). `.cp-stambuy` "+2h" compra 2h por ouro
  (aria-label traz o preco; dobra a cada garrafa no dia) - NAO clicar sem decisao do usuario.
- Capacidade: `.gs-goldrow .cap` "CAP. 224" (provavel = o que ainda cabe; classe `is-warn` quando baixa). Ouro: `.gs-goldrow .gold`.
  Max ainda nao achado (ver tooltip).
- Inventario: `.ti-slot` (`.is-empty`), "PROTEGIDO DE VENDA" (marcacao de itens protegidos), POUCH `.gs-pouchtoggle`.
- Analisador de caça `.ha-panel` (so Premium: `.ha-locked` nas free). Mapa/monstros em canvas; log em `.gs-chat`.
- Nenhum elemento de party/grupo, venda, cidade ou treino existe no DOM enquanto caça: precisa mapear com uma conta na cidade.

## Cidade, venda, caçada, treino (11/10/2026, ao vivo com MestreEscuro)
- Sair: "Finalizar Hunt" (sem confirmacao) -> o botao vira "Saindo em Ns…" (disabled, 5s) -> cidade. Nao clicar de novo.
- Cidade: sem `.hb-panel`; mapa com `.ms-hotspot` (Armário do depot, Correio, Imbuing Shrine, Daily Reward) e NPCs `.ms-poke`.
  Botoes: `button.gs-cta.gs-cta-play` "JOGAR / EXPLORAR"; `.gs-pill` "VENDER", "LOJA DE ITENS", "PARTY FINDER"
  (`aria-disabled="true"` na conta free; party ainda NAO mapeada - testar na Kina, que e Premium).
- Venda: "VENDER" -> modal Mantine "VENDA RÁPIDA" ("Selecionados: 0 / N"): `.qs-all` "SELECIONAR TUDO", itens `.ti-slot`
  ("X: adicionar à venda"), `.ti-cancel` CANCELAR, `button.gs-cta.ab-conclude` "VENDER" (disabled ate selecionar). Venda real ainda nao testada.
- Modais fecham com Escape. Janelas: `.mantine-Modal-root` (varias vazias sempre no DOM: filtrar as que tem texto).
- JOGAR / EXPLORAR -> "MODOS DE JOGO", abas `button.gm-tab` (HUNTS, BOSSES, ARENA, TRAINING, OUTFITS, MONTARIAS, QUESTS).
  A JANELA LEMBRA A ULTIMA ABA: sempre clicar a aba antes. HUNTS: `button.gm-card` ("Nome\nLEVEL x · MIN. y", 158 caças,
  15 por pagina, `‹ 1 / 11 ›` + campo "Buscar caças" + `.gm-favtool` Favoritas). Card -> `.gm-card.is-selected` + gaveta
  `.gm-panel` (Drawer) com detalhe e `button.gs-cta` "COMEÇAR A CAÇA" (inicia na hora, ~1s) e `.gm-routebtn` PERSONALIZAR.
- TRAINING: cards `gm-card` Magic, Fist, Club, Sword, Axe, Distance, Boneco de Treino (500 charges).
  CLICAR NO CARD JA INICIA O TREINO (sem detalhe/confirmacao). Treinando: `section.ta[aria-label="Analisador de Treino"]`
  (Tipo, Ciclos, progresso da skill + shielding, "STAMINA DE TREINO Capacidade 12:00 Restante") e botao "End Training"
  (volta pra cidade na hora). Treino gasta a stamina de TREINO (separada da de caça).

## Capacidade e venda (testado ao vivo com MR Kina, 11/10/2026)
- Capacidade: passar o mouse em `.gs-goldrow .cap` -> tooltip `.mantine-Tooltip-tooltip` "Capacidade livre: X de Y oz" (Y = max,
  varia por personagem; Kina 570). O texto "CAP. N" = livre. Classes `is-warn`/`is-low` conforme enche. % usada = 1 - X/Y.
  (Sem hover nao ha o max no DOM: ler o tooltip 1x por conta e guardar o max; muda ao upar.)
- Venda completa (na cidade): `.gs-pill` "VENDER" -> `.gm-modal` "VENDA RÁPIDA" (Selecionados 0/N) -> `.qs-all` "SELECIONAR TUDO"
  (vira "DESMARCAR TUDO"; itens `.ti-slot.is-selected`; mostra o total em ouro) -> `.ab-conclude` "VENDER" -> 2a CONFIRMACAO
  modal "VENDER ITENS <total>" -> `.ti-confirm` "VENDER" (`.ti-cancel` cancela). Modais fecham sozinhos, sem toast.
  Resultado: ouro 5313 -> 5742 (+429), cap livre 0 -> 301. Itens do POUCH ("PROTEGIDO DE VENDA") nao entram na lista.
- Despachar (na caça): botao "Despachar em hh:mm:ss" disabled em intervalo; "Despachar" habilitado quando pronto.

## Party e amigos (testado ao vivo com MR Kina lv12, 11/10/2026)
- Chip `button.gs-chip[aria-label=Amigos]` -> `.gm-modal` "PARTY E AMIGOS" (abre mesmo caçando).
- Party: `section.pt-section`. Caçando: `.pt-refused` "Não dá para começar uma party durante uma caça". Na cidade: `.pt-send.pt-cta`
  "Criar party" -> `.pt-count` "1 / 4", `.pt-state` "Esperando na cidade", `.pt-row` (`.pt-who` "Nome · Líder (você)" / "Level 12 · Knight"),
  `.pt-add` input "Nome do personagem" + `.pt-send` "Convidar" (disabled vazio), `.pt-decline` "DESFAZER PARTY" (sem confirmacao).
- NAO existe trava de level 20: criou com lv12. Regra (ajuda `.bl-help` "Sobre parties"): ate 4; levels "dentro de dois terços um do
  outro"; XP dividida e multiplicada por vocacoes diferentes (x1.2/1.3/2.1/3.0); ITENS VAO PARA A MOCHILA DO LIDER (so o lider
  enche/vende), ouro dividido; party se desfaz quando o lider sai. Convidar so quem esta na cidade.
- Amigos: `.fr-section` (vazio: `.fr-empty`), `.fr-add` input "Nome do personagem" + `.fr-send` "ENVIAR PEDIDO". Pedido ainda NAO testado.
- `.gs-pill` "PARTY FINDER" sempre `aria-disabled="true"` (inclusive na Premium).
- Ainda a ver: aceitar pedido de amizade/convite na outra conta, iniciar caça com a party, o que acontece com os membros quando o lider caça/sai.

## Tasks e Bestiary (11/10/2026, so leitura)
- Chip `aria-label="Quadro de Tasks"` -> `.gm-modal` com abas `.tb-tab`: TASKS DIÁRIAS, PAW AND FUR, LOJA DE TASKS DE CAÇA (disabled).
  Diarias: dificuldade `.tb-diffbtn.tb-diff-0..3` (INICIANTE/ADEPTO/EXPERIENTE/MESTRE; `is-on`; acima do level = disabled),
  `.tb-btn.primary` REROLAR, `.tb-claim` COLETAR DIÁRIO, cards `.tb-card` ("SPIDER / 0/103 abates / recompensas") com `.tb-select`
  ("SELECIONAR TASK" ou "EM PROGRESSO" disabled) e `.ti-cancel` ABANDONAR. Bounty Talisman `.bt-card` + `.bt-upgrade` MELHORAR.
  Contadores: BOUNTY POINTS, TOKENS DE REROLL. A Kina tinha task de Spider mas caçava Bone Crypt (sem progresso): o bot deve casar task x caça.
- PAW AND FUR: lista `.pw-row` (criatura; `is-on` = selecionada), busca "Buscar criatura", detalhe "300 abates" + `.tb-select.pw-btn`; "CONCLUÍDAS 0 / 10".
- Rastreador na tela de caça: `section.ht-panel` aria "Rastreador de Tasks" ("Troll · 3 pts\n3/69") ou "Rastreador de Bestiary"
  ("Skeleton done / Ghoul 95/250"); alterna pelos `.gs-tool` "Rastreador de Bestiary/Tasks/Prey".
- Bestiary completo: chip "Enciclopédia" -> aba `.gm-tab` BESTIARY -> filtros `.ec-shelf` (TODOS/COMPLETANDO/COMPLETOS), `.ec-creature`
  ("Nome / HP · XP / 0 / 500"), 273 criaturas, 15/pagina, busca "Digite para buscar". Abas tambem: ITENS, BOSSTIARY, CHARMS.
- Detalhe da caça (`.gm-panel`) lista as CRIATURAS dela: da pra mapear caça <-> criatura da task/bestiary.

## Party completa - FLUXO VALIDADO (11/10/2026: Kina lider + Druid 9, Pally 10, Sorc 8 -> Troll Hills juntos)
1. Todos na cidade ("Finalizar Hunt" em cada um; ~5s).
2. Lider: chip Amigos -> lista `.fr-row` (`.fr-who` b=nome, small="Level 9 · Druid"; `.fr-place`/`.fr-dot` classe `is-town`
   texto "Na cidade") -> `.fr-accept` "CONVIDAR" (tambem MENSAGEM; `.fr-decline` REMOVER = desfaz amizade, nao clicar).
   CONVIDAR SEM party aberta ja cria a party. Na lider o convidado aparece "Esperando uma resposta" + CANCELAR.
3. Convidado: abre sozinho `.gm-modal` "CONVITE DE PARTY" ("<Lider> Level N convidou você", "58s restantes" = expira em 60s)
   -> `.pt-send.ti-confirm` "ENTRAR" (`.pt-decline` RECUSAR). Nao existe "aceitar tudo do lider" como no Huntera.
4. Lider: `.pt-count` "4 / 4", "A party está cheia.", membros com REMOVER. Depois: JOGAR -> HUNTS -> card -> "COMEÇAR A CAÇA"
   (sem confirmacao) -> TODOS entram na caça em ~1s.
- Na caça: chip `.gs-chip.gs-party` (aria "Party: 4 de 4 membros", texto "4/4") no topo de todos. Modal Amigos mostra
  `.pt-state` "Caçando · Troll Hills", membros com HP, e no membro so `.pt-decline` "SAIR DA PARTY".
- Cada membro continua com o proprio "Finalizar Hunt" (efeito ainda nao testado: provavel que saia so ele).
- Proximo a validar: lider "Finalizar Hunt" leva todos? party se desfaz? loot na mochila do lider (capacidade do lider manda).
- VALIDADO (11/10): lider "Finalizar Hunt" ("Saindo em Ns…", 5s) -> TODOS voltam pra cidade e a PARTY CONTINUA (4/4).
  Loot so na mochila do lider (cap da Kina caiu 259->241, membros iguais); ouro dividido (+2 em cada). Ciclo de venda
  validado: lider sai -> CADA conta vende (VENDER -> SELECIONAR TUDO -> VENDER -> confirmar) -> lider reinicia a caça -> todos
  entram juntos. Venda com 0 itens: o modal abre e o VENDER fica disabled (o bot deve so fechar com Escape).
  Membros solo antes de entrar na party chegaram cheios (Pally/Sorc CAP 7/0): vender todos antes de reiniciar.

## Tasks - levantamento (11/10/2026, so leitura nas 4 contas)
- Ajuda do quadro: "Escolha uma dificuldade e depois rerole: o token compra três cartas da dificuldade escolhida. Tasks mais
  difíceis pedem menos abates e pagam mais bounty points." -> a dificuldade (`.tb-diffbtn`) so vale no proximo REROLAR (gasta 1 token).
- Card `.tb-card`: `.tb-banner b` = criatura, `.tb-kills` "53/95 abates", `.tb-progress i` (width %), `.tb-rewards .rw`
  (img alt "XP" / "Bounty points" / "Token de reroll"), `.tb-select` ("Selecionar task" / "Em progresso" disabled), Abandonar.
  So 1 task em progresso por vez. Cada task da +1 token de reroll. Iniciante ~3 bounty pts, Adepto ~7 (Pally: Orc 96 kills 840xp 7pts,
  Orc Warrior 118 kills 2065xp, Skeleton 117 kills 1433xp).
- Bounty talisman: niveis custam 5, 17, 29, 41, 53... pontos (permanente por personagem): dano, life leech, mais loot, bestiary x2.
- A task conta abates fora do quadro: a Kina trocou Spider por Frost Troll e caçando em party Folda Icefields fez 61/78.
  Usuario: abates de task contam pra todos da party (quem tem a mesma criatura).
- Enciclopedia > Bestiary > criatura NAO diz onde ela aparece (so HP, XP, progresso, dano, drops). Mapa criatura->caça vem do
  detalhe de cada caça (`.gm-panel` CRIATURAS), so na cidade.
- Paw and Fur: "cada tarefa é uma criatura para vencer, uma vez ... uma criatura já paga nunca volta a aparecer" (nao e' diario).
  CONCLUÍDAS 0/10. Lista `.pw-row` (Crocodile 300 abates 800xp/160/1; Badger 300 500/100/1; Tarantula 300 1500/300/2;
  Carniphila 150 2500/500/3; Stone Golem 200 2000/400/3; Mammoth 300 4000/800/3; Terramite 300 2500/500/2;
  Thornback Tortoise 300 1500/300/2; Gargoyle 200 1500/300/2) - colunas: abates, XP, ouro?, pontos de rank.

## Tasks - entrega e reroll (testado ao vivo com MR Kina, 11/10/2026)
- Task completa: o card mostra `.tb-select` "COMPLETAR" (habilitado) -> clicar entrega na hora (sem confirmacao/toast; da pra
  entregar CAÇANDO). Kina Frost Troll 78/78: XP 77.9% -> 89.8%, bounty 3 -> 6, tokens 1 -> 2, e vieram 3 cartas NOVAS de graça
  na dificuldade atual (Iniciante). "COLETAR DIÁRIO" continuou disabled (ainda nao sei o que libera).
- Dificuldade: clicar `.tb-diffbtn` "ADEPTO" (os cards ganham etiqueta INICIANTE) -> `.tb-btn.primary` REROLAR (gasta 1 token,
  sem confirmacao) -> 3 cartas Adepto (Emerald Damselfly 95/1164xp, Orc 183/1601xp, Swampling 178/2804xp; todas 7 pts).
- Selecionar: `.tb-card:has(.tb-banner b:text-is('Orc')) .tb-select` -> vira "EM PROGRESSO" (sem confirmacao).
- Rastreador na caça (`section.ht-panel[aria-label="Rastreador de Tasks"]`): "Orc · 7 pts | 3/183"; alterna com
  `.gs-tool[aria-label="Rastreador de Tasks"]`.
- VALIDADO: party Kina (task Orc) + Pally (task Orc Warrior) em Orc Camp -> cada um sobe a sua (criaturas diferentes, mesma caça).
- Membro sai da party: chip Amigos -> `.pt-decline` "SAIR DA PARTY" (sem confirmacao). Lider fica "Party: 2 de 4".
- Lista de amigos e' por conta: o Druid so tem a Kina como amiga (os pedidos foram todos com a lider).

## Mapa de caças (`otxidle_bot/data/hunts.json`, lido em 11/10/2026)
- 158 caças: name, rec_level, min_level, where, creatures (do detalhe `.gm-panel` -> `.gm-creature`). Lido pela JOGAR->HUNTS
  (so na cidade) paginando `‹ 1/11 ›`; clicar os cards com dispatch_event (a gaveta cobre a lista).
- Ex.: Orc Camp (8/1) Orc+Orc Warrior; Marsh Stalkers (15/12) Emerald Damselfly+Swampling+...; Folda Icefields (12/10) Frost Troll+Badger+...
