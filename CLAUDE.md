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
- Rastreador com task CHEIA mostra "ready" no lugar de "N/N" (`.ht-num`) -> parse_tracker devolve (criatura, 1, 1).
- Regras do usuario (11/10): caça da task SOZINHO so' com level recomendado <= level; JUNTO com outra conta (2/3 de level)
  aceita ate +5 (`tasks.group_level_over`). Nenhuma carta junta e ha outras contas em task -> REROLA (ate max_rerolls)
  tentando juntar; senao pega a de mais XP/abate sozinho. Contagem do dia comeca do zero quando o bot liga.
- VALIDADO ao vivo 18:06 (v2): Kina entregou Orc e pegou Orc Warrior (Orc Camp, junto); Sorc entregou, rerolou 2x e
  achou Orc Warrior (junto) -> Kina+Pally+Sorc continuaram no Orc Camp; ciclo de capacidade no meio funcionou.
- Na cidade NAO ha rastreador: task trocada na mao na cidade passava despercebida (Druid mandado pro Spider Nest com task
  Valkyrie). Agora relê o quadro 1x a cada ida a cidade/treino (`Engine.city_board`).
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

## Licoes (11/10/2026)
- Release v2.0.1 saiu com o exe ANTIGO: o build rodou com `2>$null` enquanto o OtxIdleBot.exe de dist estava em uso, o
  PyInstaller nao conseguiu sobrescrever e o zip pegou o binario velho (asset trocado depois com --clobber). Antes de
  empacotar: conferir que o OtxIdleBot nao esta rodando, NAO esconder erros do build e conferir o icone/horario do exe
  (ExtractIconEx le o recurso; ExtractAssociatedIcon usa o cache do Windows).
- Icone: "OX" laranja (#ff8c1a) gerado com Pillow; destaque laranja na interface (Huntera = "H" verde).
- Caça da party (fase de party): `party.hunt` manda; vazio = automatica (tasks.party_hunt): recomendado ate +5 do lider,
  level minimo que TODOS alcançam, empate = mais tipos de criatura. Membro fora dos 2/3 do lider caça solo.

## Treino e arma de exercicio (testado ao vivo com MR Kina, 11/10/2026)
- Treinando aparece na barra de ferramentas `button.gs-tool.ta-drillbtn` aria "Train with the Exercise Club"
  (`aria-selected` = ligado; tooltip "Exercise Club: 500 charges left"). Veio da recompensa diaria; nao fica na mochila.
- Clicar LIGA a arma: NAO vai pra mao (Mace continuou equipada); o painel `section.ta` linha "Arma" passa de
  "Só no boneco" pras cargas ("498") e gasta ~1 carga por ciclo (~3s); o skill sobe MUITO mais rapido.
- Bot (v2.0.4): liga a arma em qualquer treino (`training.use_exercise`, tenta de novo a cada 5 min). Treino iniciado
  pelo USUARIO e' respeitado (conta fica fora do plano e nao e' encerrada). Treino do bot (stamina) que cair e'
  reiniciado. Ainda nao visto: o que acontece quando as cargas acabam (treino continua no boneco ou para).
- A interface agora grava `logs/otxidle_AAAA-MM-DD.log` ao lado do .exe (antes so na janela).

## Deslogado (11/10/2026, ao vivo)
- Contas paradas na cidade sao DESLOGADAS pelo jogo: a pagina vai pra tela 'OS SEUS PERSONAGENS' (`.ob-hero-name` = nome,
  `.ob-status.is-offline`, `.ob-center-cta button` 'JOGAR AGORA' -> cidade em ~1s). Ao entrar pode abrir `.gm-modal` 'PROMOÇÃO POR
  TEMPO LIMITADO' com botao 'Entendi' (so informativo). v2.0.5: fase 'offline' -> login automatico + fecha o aviso.
- `OtxIdleBot.exe --iniciar` abre ja rodando (usado pra reiniciar o bot remotamente).

## Server save e relogin (12/10/2026 00:03, ao vivo)
- No server save as paginas vao pra PAGINA INICIAL do site (`otxidle.com.br/`, botao JOGAR -> `/play/`). Em `/play/` aparece o
  login: `input[name=username]`, `input[name=password]`, checkbox 'Salvar login' (marcado, mas os campos vem VAZIOS depois do
  save), `button[type=submit]` LOGIN e o aviso 'The server is being updated. Please sign in again in a moment.' enquanto atualiza.
- v2.0.6: aba Login (usuario/senha criptografados com DPAPI em credentials.json - NUNCA commitar, esta no .gitignore);
  Engine._relogin: site -> /play/, login com um usuario salvo livre (memory 'logins' = personagem -> usuario, nunca o
  mesmo usuario em 2 abas), espera 1 min se 'server is being updated'; depois tela de personagens -> JOGAR AGORA.
- Claude NAO digita senha de conta real: o usuario cadastra na aba Login.
- BUG achado 00:00: depois de completar/rerolar o bot lia as cartas cedo demais (lista velha) e o clique caia em OUTRA carta
  (Druid ficou com Marsh Stalker, Sorc com Tarantula achando que era Valkyrie). v2.0.6 espera as cartas mudarem e confere
  a task ativa depois de selecionar.
- O aviso 'The server is being updated' FICA na tela de login mesmo depois que o servidor volta (visto 00:40). v2.0.7: recarrega
  o /play/ e tenta o login mesmo assim; so espera 1 min se falhar. Relogin validado 00:44: 4 logins ok -> JOGAR AGORA.

## Telas ao entrar e busca de caça (12/10/2026, ao vivo)
- Depois do login aparece `.un-modal` 'NOVIDADES' (patch notes): `.un-confirm` CONFIRMAR fica DISABLED ate rolar `.un-notes` ate o fim
  (wheel + scrollTop=scrollHeight). Morte: `.gm-modal.dm-modal` 'VOCÊ MORREU' ('Morto por X', XP/skills/ouro perdidos, 'As suas
  blessings acabaram') -> `.dm-ok` CONTINUAR. v2.0.8 trata os dois e loga a morte. `.tb-claim` 'COLETAR DIÁRIO' habilitou
  depois das tasks do dia -> o bot coleta ao abrir o quadro.
- Atualizacao do jogo (11/10) mudou a busca de caças: placeholder 'Caça ou criatura' (antes 'Buscar caças') e .fill() NAO
  filtra; e' preciso DIGITAR (press_sequentially). Busca aceita criatura ('Tarantula' -> Tiquanda Tarantula Cave). v2.0.9 digita
  e, se nao achar, pagina a lista (antes so olhava a 1a pagina -> 'caça nao encontrada').
- Druid MORREU no Marsh Stalkers (lv 17, caça rec 15) para Swampling - solo com recomendado <= level nao garante segurança.
- 01:18: Kina terminou as tasks e foi ajudar o Pally (Bone Crypt, facil), largando o Sorc 18 sozinho na Tiquanda (rec 20).
  v2.0.10: ajudante prioriza o grupo numa caça ACIMA do level de quem esta nele (tasks.plan / hunt_rec_level). E o lider
  saindo traz a party: o membro ja esta na cidade quando o bot tenta 'Finalizar Hunt' -> finish_hunt agora confere a fase
  (antes dava timeout e pausava a conta 5 min).

## v2.1.0 - party primeiro, tasks seguem a caça da party (12/10/2026)
- Usuario: 'mesmo com tasks, priorizar a hunt x4 porque podemos ir em criaturas mais fortes'; Paw and Fur e importante;
  sem cota travando (per_day 0); party de 4 quando acabarem as tasks boas. Caso real: Sorc bateu a cota (2) e caiu na
  'caça solo de maior recomendado', trocando Barbarian Camp por Daramian Minotaur so por ter subido pro 20, ignorando as
  cartas (Barbarian Skullhunter, Cyclops) e o Paw.
- Paw and Fur RODA EM PARALELO com a diaria (testado no Pally: Mummy diaria + Paw Crocodile 0/300). Linha ativa mostra
  '0 / 300' e o detalhe troca SELECIONAR por ABANDONAR. Botao de entregar o Paw cheio: ainda NAO visto.
- tasks.plan_party_first: party = lider + membros nos 2/3; caça = best_hunt (hunt_score: diaria ativa 3, Paw ativo 2,
  carta/opcao de Paw disponivel 1; empate = mais forte; so troca se outra atender MAIS). Fora da party: solo seguro.
  Engine: _pick_for_hunt (so carta da caça do grupo; senao rerola; senao espera), _paw (entrega cheio, pega o da caça
  do grupo), revisao a cada 15 min e quando a caça do grupo muda. 'Caça da party' fixa ainda manda (voltei pra Automatica).

## v2.2.0 - as 4 juntas (12/10/2026, decisao do usuario)
- Prioridade: tasks que juntem as 4; senao a caça padrao da party pras 4 (nunca de 2 em 2 / separadas). Paw and Fur primeiro
  (lista igual pras 4), depois as diarias. hunt_score = (contas com task la', pontos): Paw ativo 10, diaria 3, carta/opcao 1.
  'Caça da party' virou a caça PADRAO (fallback quando nenhuma caça tem task); vazia = a mais forte que o grupo aguenta.
- Treino SINCRONIZADO: stamina de uma -> as 4 treinam; voltam juntas quando todas recuperarem (Engine._all_trained).
- Atencao: Kina 24 x Pally 16 no limite dos 2/3 (16*3=48 >= 24*2); Kina no 25 tira o Pally.

- Paw entregue (08:55): a linha fica na lista como `.pw-row.is-done` com tag 'Concluída' e o `.pw-btn` vira 'CONCLUÍDA' (disabled).
  v2.2.2 ignora linhas is-done (antes tentava pegar o Crocodile de novo -> timeout). E nao rerola diaria quando o grupo
  esta na caça por causa do Paw (Sorc gastou 2 tokens). Proximo Paw do grupo: Tarantula (Tiquanda) - Stone Golem pede min 20.

## v2.3.0 - LEVEL primeiro (12/10/2026, usuario)
- 'Nao compensa no inicio fazer as diarias (retorno baixo); precisamos de level: priorizar a hunt x4 em hunts maiores.'
  `tasks.priority` = 'xp' (padrao): party na caça MAIS FORTE permitida (rec <= lider+5, min <= o mais baixo; empate fica
  na atual) via tasks.strongest_hunt; diaria/Paw so de carona (sem reroll, Paw so se a criatura estiver na caça).
  'tasks' = logica anterior (best_hunt por tasks, Paw primeiro).
- Lista de caças desatualizava (usuario viu caças novas no jogo). Account.read_hunt_list relê tudo (nome + LEVEL/MIN) e
  abre detalhe so das novas; Engine._refresh_hunts antes de iniciar caça se `hunts.json` (ao lado do .exe, {read_at,
  hunts}) tiver mais de 20h. load_hunts prefere esse arquivo ao embutido.

## v2.4.0 - minimo da caça pelo LIDER (12/10/2026, usuario)
- 'O lv maior atinge o esperado: o Kina pode ir e levar a party porque o conjunto e forte.' Caça da party: rec <= lider+5
  e MIN <= level do LIDER (`party.min_by_leader`, padrao true). Se algum membro nao entrar (so o lider caçando), o bot
  bloqueia a caça 6h (Engine.blocked_hunts / _check_party_entered) e vai pra proxima. Lider 26: Dwarf Mines / Corym Caves (30/24).
- Lista relida 15:58: as mesmas 158 caças (nenhuma nova); Corym Caves ja existia (rec 30, min 24).

## 14/10/2026 - tela de personagens 'TREINANDO' e botao traduzido
- O treino CONTINUA com a conta deslogada: a tela 'OS SEUS PERSONAGENS' mostra status 'TREINANDO' (antes 'OFFLINE'); JOGAR AGORA
  cai direto no treino. O jogo TRADUZIU o botao: 'End Training' -> 'Finalizar Training' (END_TRAIN_TEXT agora e regex).
  Exercise: aria 'Usar Exercise Club para treinar'; depois de relogar o painel volta pra 'Arma: Só no boneco' (o bot religa).
- 06:40 o bot falhou a cada ~30s procurando 'End Training' (o _train nao respeitava a pausa de falha): corrigido em v2.4.1.

## 14/10/2026 - servidor fora do ar (Cloudflare) e recarregar a pagina
- Servidor cai: a aba fica em 'Error 1033 ... Cloudflare Tunnel error ... Please try again in a few minutes' (url /play/, sem
  elementos do jogo) e NAO volta sozinha. Antes: JOGAR AGORA falhava ('nao entrou no jogo') e a aba ficava parada horas.
- v2.4.2: fase 'error' (Cloudflare / Error 10xx / Bad Gateway / ERR_ / pagina em branco, sem nome do jogo) -> Account.reload
  (goto /play/) na hora e a cada 1 min; fase 'unknown' por > 2 min tambem recarrega (Engine._recover_pages). Depois o fluxo
  normal: login -> JOGAR AGORA -> NOVIDADES -> party -> caça.
- v2.4.3: party ligada e algum membro ainda voltando (erro/login/personagens) -> as online NAO caçam sozinhas: saem da caça
  e esperam na cidade ate 10 min (Engine._party_waiting); depois seguem com quem esta online (solo = caça segura do level).

## 15/10/2026 - mortes repetidas e relogin
- Madrugada: Druid (96) morreu 6x pra Hydra (~900k XP cada) e Sorc 4x - com min pelo lider (Kina 124) a party ia em caças
  fortes demais pro membro mais fraco e o bot voltava sempre. v2.4.4: 2 mortes da mesma conta na mesma caça em 3h ->
  caça bloqueada 12h (Engine._note_death / blocked_hunts, vale pro plano da party e pro solo). Morte isolada: so log.
- A aba do Druid estava na pagina inicial do site com o bot PARADO (o usuario parou 06:35/12:26). Com o bot rodando o fluxo
  site -> /play/ -> login salvo -> JOGAR AGORA funciona (validado 15:19); o aviso 'server is being updated' continua grudado.

## v2.5.0 - contas solo com caça escolhida (15/10/2026, usuario)
- Sorc morreu muito e ficou levels atras (nao acompanha a party). Aba Party: cada conta tem 'na party' (marcada) e 'Caça solo'
  (`tasks.solo_hunts` nome->caça; Automatica = mais forte segura rec<=level). Desmarcada = caça sozinha com fluxo completo
  (venda, treino proprio, relogin). Engine.party_first tambem quando ha solo_hunts (party desligada).

## v2.6.0 - modo por conta (15/10/2026, usuario)
- Aba Party: cada conta (inclusive a lider) tem modo Party / Solo / Só treinar (`party.modes`; sem modo: lider+members = party,
  resto = solo; config.account_mode). Party fora dos 2/3 do lider ja caça solo e volta sozinha quando alcança. Solo = caça
  em `tasks.solo_hunts` (ou Automatica). 'Só treinar' = treina direto com a arma de exercicio e nunca encerra (Engine._train).
  Lider em modo nao-party: a party usa a conta de maior level em modo party.

## v2.6.1 - ao ligar, cada conta vai pro destino do modo (15/10/2026, usuario)
- Treino que o bot nao mandou (na mao / antes de ligar) NAO e mais respeitado: se a stamina de caça < resume -> vira treino
  do bot (fica ate recuperar); senao encerra e a conta segue o modo (party: cidade -> party -> caça; solo: caça escolhida).
  Ao ligar (first_tick) o bot assume na hora as contas na cidade (sem a espera de 'cidade parada'). Caça errada -> _mismatch.

## v2.6.2 - notificacao DESCONECTADO (15/10/2026, ao vivo)
- Queda de conexao: aparece `.ti-note.ti-note--error` (Mantine Notification) titulo 'DESCONECTADO' e corpo 'WebSocket closed with
  status code: 1006' ou 'Cannot send data if the connection is not in the Connected State'. A tela de caça/treino fica CONGELADA
  (o bot achava que estava tudo certo). Agora vira fase 'error' -> recarrega a aba (Engine._recover_pages) e sai do plano
  ate voltar. Validado 20:54: Kina e Druid recarregados -> JOGAR AGORA.
