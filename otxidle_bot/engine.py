"""Motor: le as contas, monta os grupos, decide e executa os ciclos.

Grupos:
- Tasks ligadas (v2): o plano do dia (tasks.plan) junta em party quem tem task na mesma caça, poe quem ja terminou
  pra ajudar e, quando TODAS terminam a cota, monta a party configurada na caça padrao da party.
- Tasks desligadas (v1): a party configurada (lider + membros abertos) e o resto solo.

Regras dentro de um grupo:
- Capacidade: QUALQUER conta >= capacity_pct (e acima do "piso" de depois de vender) -> o lider sai (traz todos) -> cada
  conta vende -> volta pra caça do grupo.
- Stamina de caça <= training.stamina_minutes -> a conta vai treinar (sai do plano) ate recuperar resume_stamina_minutes.
- Plano mudou (task nova em outra caça, alguem terminou, party errada) -> o grupo volta pra cidade e refaz a party.
- Party: na cidade quem esta numa party errada sai, o lider convida PELO NOME (nao precisa ser amigo) e cada membro aceita.
- Cidade parada sem o bot ter levado: espera idle_city_seconds (pode ser voce mexendo) e assume.
"""
import datetime
import time

from . import config as cfgmod
from . import tasks as T
from .account import GameError
from .memory import Memory

FLOOR_MARGIN = 10      # pontos de % acima do "piso" (peso que fica depois de vender) pra sair de novo


class Group:
    def __init__(self, leader, members=(), hunt=None, reason=""):
        self.leader = leader
        self.members = list(members)
        self.hunt = hunt
        self.reason = reason

    @property
    def accounts(self):
        return [self.leader] + self.members

    @property
    def names(self):
        return [a.name for a in self.accounts]

    @property
    def is_party(self):
        return bool(self.members)

    @property
    def label(self):
        return " + ".join(self.names)


def build_groups(accounts, cfg, skip=()):
    """v1: party ligada e lider aberto: lider + membros configurados que estao abertos (menos 'skip'); o resto solo."""
    by_name = {a.name.casefold(): a for a in accounts if a.name}
    party = cfg["party"]
    groups, used = [], set()
    leader = by_name.get((party.get("leader") or "").casefold()) if party.get("enabled") else None
    if leader:
        members = [by_name[m.casefold()] for m in party.get("members") or []
                   if m.casefold() in by_name and m.casefold() != leader.name.casefold() and m.casefold() not in skip]
        groups.append(Group(leader, members))
        used.update(a.name.casefold() for a in groups[0].accounts)
    for name, acc in by_name.items():
        if name not in used:
            groups.append(Group(acc))
    return groups


def hunt_triggers(states, cfg, floors=None):
    """Motivo pra tirar o grupo da caça ('capacidade' / 'stamina', detalhe, contas) ou None. 'states' = as que caçam.
    'floors': % de capacidade de cada conta logo depois de vender (equipamento/pouch nao saem): sem isso, um limite
    abaixo do piso faria o grupo sair e voltar sem parar."""
    floors = floors or {}
    for st in states:
        floor = floors.get(st.name.casefold(), 0)
        if st.cap_pct is not None and st.cap_pct >= cfg["capacity_pct"] and st.cap_pct >= floor + FLOOR_MARGIN:
            return "capacidade", f"{st.name} com {st.cap_pct:.0f}% da capacidade", [st.name]
    tr = cfg["training"]
    if tr["enabled"]:
        tired = [st for st in states if st.stamina_hunt is not None and st.stamina_hunt <= tr["stamina_minutes"]]
        if tired:
            return "stamina", f"{tired[0].name} com {tired[0].stamina_hunt} min de stamina de caça", [st.name for st in tired]
    return None


def training_done(st, cfg):
    """Volta a caçar quando a stamina de caça voltou, ou acabou a stamina de treino."""
    if st.stamina_train is not None and st.stamina_train <= 1:
        return True
    return st.stamina_hunt is not None and st.stamina_hunt >= cfg["training"]["resume_stamina_minutes"]


def task_day(cfg, now=None):
    """Dia das tasks: muda em tasks.reset_hour (padrao 0h)."""
    now = now or datetime.datetime.now()
    return (now - datetime.timedelta(hours=cfg["tasks"].get("reset_hour", 0))).strftime("%Y-%m-%d")


class Engine:
    def __init__(self, accounts, cfg, log=print, refresh=None, memory=None, hunts=None):
        self.accounts = accounts
        self.cfg = cfg
        self.log = log
        self.refresh = refresh
        self.memory = memory or Memory()
        self.hunts = hunts
        self.snapshot = {"states": {}, "groups": {}, "hunts": {}, "tasks": {}}
        self.city_since = {}          # grupo -> quando foi visto parado na cidade
        self.ours = set()             # contas que o BOT levou pra cidade (o grupo delas assume na hora)
        self.cooldown = {}            # grupo/conta -> ate quando nao tentar de novo
        self.party_skip = {}          # conta -> ate quando fica fora de party (nao entrou)
        self.cap_floor = {}           # conta -> % de capacidade logo depois de vender
        self.mismatch = {}            # grupo -> vezes seguidas com party/caça diferente do plano
        self.expected_leader = {}     # conta -> lider do grupo dela (aceita convite so' dele)
        self.city_board = set()       # contas que ja releram o quadro nesta ida a cidade/treino
        self.exercise_try = {}        # conta -> quando pode tentar ligar a arma de exercicio de novo
        self.credentials = None       # logins salvos (aba Login) pra relogar depois do server save
        self.targets = {}             # conta -> (caça do grupo dela, motivo) do ultimo plano
        self.current_hunt = {}        # conta -> caça do grupo (estabilidade: so' troca se outra atender mais tasks)
        self.login_busy = set()
        self._warned = set()

    # ---------------------------------------------------------------- loop
    def run(self, stop):
        while not stop.is_set():
            try:
                if self.refresh:
                    self.accounts = self.refresh()
                self.tick()
            except Exception as error:
                self.log(f"erro no ciclo: {error}")
            stop.wait(self.cfg["poll_seconds"])

    def read_all(self):
        states = {}
        for acc in self.accounts:
            try:
                st = acc.read()
            except Exception as error:
                self.log(f"erro lendo uma conta: {error}")
                continue
            if st.name:
                states[st.name] = st
                self.memory.set_seen(st.name, st.vocation, st.level)
        return states

    @property
    def tasks_on(self):
        return bool(self.cfg["tasks"].get("enabled"))

    def _relogin(self):
        """Paginas fora do jogo (sem nome): site -> /play/; login -> usa um login salvo que nao esta em uso."""
        if not self.credentials:
            return
        out = [a for a in self.accounts if a.state.phase in ("site", "login")]
        if not out:
            return
        if time.time() < self.cooldown.get("login", 0):
            return
        for acc in out:
            if acc.state.phase == "site":
                self._safe("login", acc.open_play, [acc])
        for acc in out:
            st = acc.read()
            if st.phase != "login":
                continue
            if st.updating:
                # o aviso "server is being updated" FICA na pagina depois que o servidor volta (visto ao vivo):
                # recarrega o /play/ e tenta o login mesmo assim; so' espera se o login falhar
                self._safe("login", acc.open_play, [acc])
                st = acc.read()
                if st.phase != "login":
                    continue
            in_use = {self.memory.login_of(a.name) for a in self.accounts if a.name and a.state.phase not in ("site", "login")}
            free = [u for u in self.credentials.usernames() if u not in in_use and u not in self.login_busy]
            if not free:
                self._warn_once(("nologin", len(out)), "há aba fora do jogo e nenhum login salvo livre - cadastre na aba Login")
                return
            before = self.memory.login_of(acc.name) if acc.name else None    # o login que esta aba usava
            username = before if before in free else free[0]
            self.login_busy.add(username)
            try:
                if acc.login_with(username, self.credentials.get(username)):
                    st = acc.read()
                    if st.name:
                        self.memory.set_login_of(st.name, username)
                else:
                    self.cooldown["login"] = time.time() + 60
                    return
            except Exception as error:
                self.log(f"login falhou: {error}")
                self.cooldown["login"] = time.time() + 60
                return
            finally:
                self.login_busy.discard(username)

    def tick(self):
        states = self.read_all()
        self._relogin()
        for acc in [a for a in self.accounts if a.name in states and a.state.phase == "offline"]:
            if time.time() >= self.cooldown.get(acc.name, 0):
                self._safe(acc.name, acc.login, [acc])          # o jogo derrubou: entra de novo
        for acc in [a for a in self.accounts if a.name in states and (a.state.notes or a.state.death)]:
            self._safe(acc.name, acc.dismiss_gates, [acc])
            states[acc.name] = acc.read()
        for acc in [a for a in self.accounts if a.name in states and any(m.startswith("PROMOÇÃO") for m in a.state.modals)]:
            self._safe(acc.name, acc.dismiss_notices, [acc])
        states = {n: st for n, st in states.items() if st.phase != "offline"}
        accounts = [a for a in self.accounts if a.name in states and a.state.phase != "offline"]
        if self.tasks_on:
            if self.hunts is None:
                self.hunts = T.load_hunts()
            for acc in accounts:
                if time.time() >= self.cooldown.get(acc.name, 0):
                    self._safe(acc.name, lambda acc=acc: self._task_upkeep(acc), [acc])
        # treinando: as que o bot mandou (stamina) e as que VOCE colocou pra treinar (o bot respeita e nao encerra)
        training = [a for a in accounts if self.memory.training(a.name) or a.state.phase == "training"]
        playing = [a for a in accounts if a not in training]
        groups = self._groups(playing)
        self.expected_leader = {a.name.casefold(): g.leader.name for g in groups for a in g.members}
        if not self.tasks_on:
            party = self.cfg["party"]
            if party.get("enabled"):
                for m in party.get("members") or []:
                    self.expected_leader.setdefault(m.casefold(), party.get("leader") or "")
        self.snapshot = {"states": states, "groups": {g.label: g.names for g in groups},
                         "hunts": {g.label: g.hunt for g in groups}, "tasks": self.memory.tasks_today(task_day(self.cfg))}
        self._invites(accounts)
        for acc in training:
            self._safe(acc.name, lambda acc=acc: self._train(acc), [acc])
        for group in groups:
            if time.time() < self.cooldown.get(group.label, 0):
                continue
            self._safe(group.label, lambda group=group: self._group(group), group.accounts)

    def _safe(self, label, fn, accounts=()):
        try:
            fn()
        except Exception as error:
            self.log(f"[{label}] falhou: {error} - tento de novo em {self.cfg['cooldown_fail_seconds']}s")
            self.cooldown[label] = time.time() + self.cfg["cooldown_fail_seconds"]
            for acc in accounts:
                try:
                    acc.close_modals()
                except Exception:
                    pass

    def _warn_once(self, key, message):
        if key not in self._warned:
            self._warned.add(key)
            self.log(message)

    # ---------------------------------------------------------- grupos
    def _groups(self, accounts):
        skip = {k for k, until in self.party_skip.items() if time.time() < until}
        if not self.tasks_on:
            return build_groups(accounts, self.cfg, skip)
        by = {a.name.casefold(): a for a in accounts}
        day = self.memory.tasks_today(task_day(self.cfg))
        if self.party_first:
            return self._groups_party_first(accounts, by, day, skip)
        infos = []
        for acc in accounts:
            info = day.get(acc.name.casefold()) or {}
            infos.append({"name": acc.name, "level": acc.state.level or 1, "task_hunt": info.get("hunt"),
                          "done": self._day_done(info)})
        groups = []
        for pg in T.plan(infos, self.hunts, self.cfg):
            names = list(pg.accounts)
            for name in list(names[1:]):
                if name.casefold() in skip:            # nao conseguiu entrar na party: caça sozinho
                    names.remove(name)
                    groups.append(Group(by[name.casefold()], hunt=pg.hunt, reason="solo"))
            groups.append(Group(by[names[0].casefold()], [by[n.casefold()] for n in names[1:]], pg.hunt, pg.reason))
        return groups

    @property
    def party_first(self):
        return self.tasks_on and bool(self.cfg["party"].get("enabled"))

    def _groups_party_first(self, accounts, by, day, skip):
        infos = []
        for acc in accounts:
            info = day.get(acc.name.casefold()) or {}
            infos.append({"name": acc.name, "level": acc.state.level or 1, "daily": info.get("creature"),
                          "cards": info.get("cards") or [], "paw": info.get("paw"), "paw_options": info.get("paw_options") or []})
        groups = []
        for pg in T.plan_party_first(infos, self.hunts, self.cfg, self.current_hunt):
            names = list(pg.accounts)
            for name in list(names[1:]):
                if name.casefold() in skip:            # nao conseguiu entrar na party: caça sozinho, em caça segura
                    names.remove(name)
                    me = next(i for i in infos if i["name"] == name)
                    hunt = T.best_hunt(self.hunts, [me], me["level"], me["level"], self.current_hunt.get(name))[0]
                    if hunt:
                        groups.append(Group(by[name.casefold()], hunt=hunt, reason="solo"))
            groups.append(Group(by[names[0].casefold()], [by[n.casefold()] for n in names[1:]], pg.hunt, pg.reason))
        self.targets = {a.name: (g.hunt, g.reason) for g in groups for a in g.accounts}
        for g in groups:
            for a in g.accounts:
                if self.current_hunt.get(a.name) != g.hunt:
                    self.current_hunt[a.name] = g.hunt
        return groups

    def _day_done(self, info):
        if info.get("hunt"):
            return False
        per_day = self.cfg["tasks"].get("per_day") or 0
        return (per_day and info.get("done", 0) >= per_day) or bool(info.get("stuck"))

    # ---------------------------------------------------------- convites
    def _invites(self, accounts):
        """Convite aberto: aceita so' se veio do lider que o bot espera pra essa conta."""
        for acc in accounts:
            st = acc.state
            if not st.invite_from:
                continue
            expected = self.expected_leader.get(acc.name.casefold(), "")
            if expected and st.invite_from.casefold() == expected.casefold():
                acc.accept_invite()
            else:
                self._warn_once(("invite", acc.name, st.invite_from),
                                f"{acc.name}: convite de party de {st.invite_from} ignorado (não é o líder esperado)")

    # ------------------------------------------------------------- tasks
    def _task_upkeep(self, acc):
        """Entrega a task cheia, pega a proxima (cota do dia) e mantem o rastreador de tasks na tela."""
        st = acc.state
        if st.phase not in ("hunting", "city", "training") or st.modals:
            return
        day = task_day(self.cfg)
        info = dict(self.memory.tasks_today(day).get(acc.name.casefold()) or {})
        if st.phase == "hunting" and not st.tracker_shown and not info.get("tracker_tried"):
            acc.show_task_tracker()
            info["tracker_tried"] = True
            self.memory.set_task(day, acc.name, info)
        need = not info.get("checked")
        if st.task:
            creature, kills, total = st.task
            if total and kills >= total:
                need = True                                  # cheia: entregar
            elif creature.casefold() != (info.get("creature") or "").casefold():
                need = True                                  # trocaram a task na mao
        elif st.phase == "city" and not info.get("hunt") and not self._day_done(info):
            need = True                                      # sem task e ainda falta cota
        if st.phase == "hunting":
            self.city_board.discard(acc.name)
        elif acc.name not in self.city_board:
            need = True                                      # na cidade nao ha rastreador: relê o quadro 1x por visita
            self.city_board.add(acc.name)
        target = self.targets.get(acc.name, (None, ""))[0] if self.party_first else None
        if self.party_first:
            if target and info.get("target") != target:
                need = True                                  # caça do grupo mudou: tasks/Paw da caça nova
            if time.time() - info.get("checked_at", 0) > 900:
                need = True                                  # revisa (Paw and Fur nao tem rastreador)
        if not need:
            return
        board = acc.open_board()
        try:
            self._board(acc, board, info, target)
            if self.party_first:
                self._paw(acc, info, target)
        finally:
            acc.close_modals()
        info["checked"] = True
        info["checked_at"] = time.time()
        info["target"] = target
        self.memory.set_task(day, acc.name, info)

    def _board(self, acc, board, info, target=None):
        tcfg = self.cfg["tasks"]
        acc.claim_daily()
        active = board.active
        if active and active.status == "complete":
            board = acc.complete_task(active.creature)
            info["done"] = info.get("done", 0) + 1
            active = None
        info["creature"] = info["hunt"] = None
        level = acc.state.level or 1
        others = self._other_tasks(acc)
        if active:
            info["creature"] = active.creature
            info["hunt"] = self._active_hunt(active.creature, level, others)
            if not info["hunt"]:
                self._warn_once(("nohunt", acc.name, active.creature),
                                f"{acc.name}: task {active.creature} sem caça possível no level {level} - abandone ou troque")
            return
        if tcfg.get("per_day") and info.get("done", 0) >= tcfg["per_day"]:
            self.log(f"{acc.name}: terminou as {tcfg['per_day']} tasks do dia")
            return
        if self.party_first and target:
            self._pick_for_hunt(acc, board, info, target)
            return
        rerolls = 0
        difficulty = tcfg["difficulty"]
        if board.difficulty.casefold() != difficulty.casefold() and board.tokens > 0:
            board = acc.reroll(difficulty)
        while True:
            pick = T.choose_card(board.cards, level, self.hunts, tcfg, others)
            can_reroll = board.tokens > 0 and rerolls < tcfg.get("max_rerolls", 2)
            # nenhuma carta junta com outra conta: rerola tentando juntar (cada task devolve 1 token)
            if pick and (pick[2] or not others or not can_reroll):
                card, hunt, together = pick
                got = acc.select_task(card.creature)
                if got and got.casefold() != card.creature.casefold():      # o jogo ficou com outra carta
                    info.update(creature=got, hunt=self._active_hunt(got, level, others), stuck=False)
                    return
                info.update(creature=card.creature, hunt=hunt, stuck=False)
                self.log(f"{acc.name}: task {card.creature} ({card.need} abates, {card.xp} XP) em {hunt}"
                         + (" - junto com outra conta" if together else " - sozinho"))
                return
            if can_reroll:
                rerolls += 1
                board = acc.reroll(difficulty)
                continue
            info["stuck"] = True
            self.log(f"{acc.name}: nenhuma task boa e sem reroll - fica livre pelo resto do dia")
            return

    def _all_trained(self):
        """Todas as contas marcadas pra treinar ja recuperaram (as que nao estao treinando contam como prontas)."""
        return all(training_done(a.state, self.cfg) for a in self.accounts
                   if a.name and self.memory.training(a.name) and a.state.phase == "training")

    def _hunt_creatures(self, hunt):
        h = next((x for x in self.hunts if x["name"].casefold() == (hunt or "").casefold()), None)
        return {c.casefold() for c in h["creatures"]} if h else set()

    def _pick_for_hunt(self, acc, board, info, target):
        """Party primeiro: so' pega carta cuja criatura esta na caça do grupo (senao a task nao anda). Nenhuma serve ->
        rerola (ate max_rerolls, se tiver token); continua sem -> espera a proxima revisao (caça do grupo pode mudar)."""
        tcfg = self.cfg["tasks"]
        there = self._hunt_creatures(target)
        difficulty = tcfg["difficulty"]
        rerolls = 0
        if board.difficulty.casefold() != difficulty.casefold() and board.tokens > 0:
            board = acc.reroll(difficulty)
        while True:
            cards = [c for c in board.cards if c.status == "available" and c.creature.casefold() in there
                     and c.xp_per_kill >= tcfg.get("min_xp_per_kill", 0)]
            if cards:
                card = max(cards, key=lambda c: c.xp_per_kill)
                got = acc.select_task(card.creature)
                info.update(creature=got or card.creature, hunt=target, stuck=False, waiting=False)
                self.log(f"{acc.name}: task {card.creature} ({card.need} abates, {card.xp} XP) - na caça do grupo, {target}")
                break
            if board.tokens > 0 and rerolls < tcfg.get("max_rerolls", 2):
                rerolls += 1
                board = acc.reroll(difficulty)
                continue
            if not info.get("waiting"):
                self.log(f"{acc.name}: nenhuma task diária de {target} no quadro - espera a próxima revisão")
            info["waiting"] = True
            break
        info["cards"] = [c.creature for c in acc._board_now().cards if c.status == "available"]

    def _paw(self, acc, info, target):
        """Paw and Fur sempre ativo (roda junto com a diaria): entrega o cheio e pega o da caça do grupo; sem nenhum la',
        pega o que a conta consegue fazer sozinha numa caça segura (fica pra quando o grupo passar por la')."""
        paw = acc.open_paw()
        active = paw["active"]
        if active and active[2] and active[1] >= active[2]:
            paw = acc.complete_paw(active[0])
            active = paw["active"]
        if not active and paw["options"]:
            choice = self._group_paw(acc, paw["options"], target)
            if choice:
                got = acc.select_paw(choice)
                paw = acc._paw_now()
                active = paw["active"]
        info["paw"] = active[0] if active else None
        info["paw_kills"] = list(active[1:]) if active else None
        info["paw_options"] = paw["options"]

    def _group_paw(self, acc, options, target):
        """Paw and Fur e' a MESMA lista pras contas: o grupo pega a MESMA criatura pra caçar junto.
        1) a que outra conta do grupo ja pegou; 2) uma da caça atual do grupo; 3) a da caça mais forte que o grupo
        aguenta (recomendado ate +group_level_over do lider, minimo que todos alcançam)."""
        day = self.memory.tasks_today(task_day(self.cfg))
        mates = [a for a in self.accounts if a.name and self.targets.get(a.name, (None,))[0] == target] or [acc]
        for mate in mates:
            paw = (day.get(mate.name.casefold()) or {}).get("paw")
            if paw and paw in options and mate is not acc:
                return paw
        there = self._hunt_creatures(target)
        choice = next((c for c in options if c.casefold() in there), None)
        if choice:
            return choice
        levels = [a.state.level or 1 for a in mates]
        top = max(levels) + (self.cfg["tasks"].get("group_level_over", 5) if len(mates) > 1 else 0)
        best = None
        for creature in options:
            for h in T.hunt_options(self.hunts, creature, min(levels), over=top - min(levels)):
                if (h.get("rec_level") or 1) <= top and (best is None or (h.get("rec_level") or 1) > best[1]):
                    best = (creature, h.get("rec_level") or 1)
        return best[0] if best else None

    def _other_tasks(self, acc):
        """[(caça, level)] das tasks em andamento das OUTRAS contas abertas."""
        day = self.memory.tasks_today(task_day(self.cfg))
        out = []
        for other in self.accounts:
            key = (other.name or "").casefold()
            if not key or key == acc.name.casefold():
                continue
            level = other.state.level or 1
            hunt = (day.get(key) or {}).get("hunt")
            if not hunt and other.state.task and not (day.get(key) or {}).get("checked"):
                hunt = T.hunt_for(self.hunts, other.state.task[0], level)   # ainda nao lida: usa o rastreador
            if hunt:
                out.append((hunt, level))
        return out

    def _active_hunt(self, creature, level, others):
        """Caça de uma task ja em andamento: a de outra conta (ate group_level_over acima), senao a recomendada pro
        level; se a task foi escolhida na mao e e' mais dificil, aceita a mais facil que o jogo libera."""
        over = self.cfg["tasks"].get("group_level_over", 5)
        for hunt, other_level in others:
            if T.levels_ok([level, other_level]) and any(
                    h["name"].casefold() == hunt.casefold() for h in T.hunt_options(self.hunts, creature, level, over)):
                return hunt
        hard = T.hunt_options(self.hunts, creature, level, over=99)
        return T.hunt_for(self.hunts, creature, level) or (min(hard, key=lambda h: h.get("rec_level") or 1)["name"] if hard else None)

    # ------------------------------------------------------------- treino
    def _train(self, acc):
        st = acc.state
        if st.phase == "hunting":
            acc.finish_hunt()
            return
        if st.phase == "training":
            if self.cfg["training"].get("use_exercise", True) and any(not d.get("on") for d in st.drills) \
                    and time.time() >= self.exercise_try.get(acc.name, 0):
                self.exercise_try[acc.name] = time.time() + 300      # se nao ligar, tenta de novo em 5 min
                acc.use_exercise_weapon()
            if not self.memory.training(acc.name):
                return                      # treino que voce iniciou: o bot nao encerra
            if self.party_first and not self._all_trained():
                return                      # party: espera TODAS recuperarem pra voltar junto
            if training_done(st, self.cfg):
                acc.end_training()
                self.memory.set_training(acc.name, False)
                self.log(f"{acc.name}: stamina de caça recuperada - volta a caçar")
            return
        if st.phase == "city":
            if training_done(st, self.cfg):
                self.memory.set_training(acc.name, False)
                return
            if st.party_size:
                acc.leave_party()
            acc.sell_all()
            skill = cfgmod.skill_for(self.cfg["training"], acc.name, st.vocation)
            if not skill:
                self._warn_once(("skill", acc.name), f"{acc.name}: sem treino definido pra vocação {st.vocation}")
                return
            acc.start_training(skill)

    # ------------------------------------------------------------- grupo
    def _group(self, group):
        states = [a.state for a in group.accounts]
        if {st.phase for st in states} & {"unknown", "leaving"}:
            return
        leader = group.leader
        if leader.state.phase == "hunting":
            self.city_since.pop(group.label, None)
            if leader.state.hunt_name:
                self.memory.update_group(group.names, hunt=leader.state.hunt_name)
            wrong = self._mismatch(group)
            if wrong:
                self.mismatch[group.label] = self.mismatch.get(group.label, 0) + 1
                if self.mismatch[group.label] >= 2:          # 2 leituras seguidas (o chip da party atualiza com atraso)
                    self.mismatch.pop(group.label, None)
                    self._leave(group, wrong, everyone=True)
                return
            self.mismatch.pop(group.label, None)
            trigger = hunt_triggers([a.state for a in group.accounts], self.cfg, self.cap_floor)
            if trigger:
                reason, detail, names = trigger
                if reason == "stamina":
                    # party primeiro: treinam TODAS juntas (e voltam juntas) pra nao quebrar a party
                    for name in (group.names if self.party_first and group.is_party else names):
                        self.memory.set_training(name, True)
                self._leave(group, detail)
            return
        # lider fora da caça: quem esta caçando volta pra cidade (pra entrar na party/caça certa)
        hunting = [a for a in group.members if a.state.phase == "hunting"]
        if hunting:
            for acc in hunting:
                self.log(f"[{group.label}] {acc.name} caçando fora do plano - voltando pra cidade")
                acc.finish_hunt()
            return
        if any(a.state.phase == "training" for a in group.accounts):
            for acc in group.accounts:
                if acc.state.phase == "training":
                    acc.end_training()
            self.ours.update(a.name for a in group.accounts)
            return
        self._town(group)

    def _mismatch(self, group):
        """Motivo se a caça/party real difere do esperado (v1: so' membro fora da caça)."""
        out = [a.name for a in group.members if a.state.phase != "hunting"]
        if out:
            return f"reagrupar a party ({', '.join(out)} fora da caça)"
        if not self.tasks_on:
            return None
        if group.hunt and group.leader.state.hunt_name.casefold() != group.hunt.casefold():
            return f"plano mudou: caça {group.hunt} (está em {group.leader.state.hunt_name})"
        size = len(group.accounts) if group.is_party else 0
        for acc in group.accounts:
            if acc.state.hunt_name.casefold() != group.leader.state.hunt_name.casefold() or acc.state.party_size != size:
                return "party diferente do plano (" + (f"party de {size}" if size else "solo") + ")"
        return None

    def _leave(self, group, why, everyone=False):
        self.log(f"[{group.label}] saindo da caça: {why}")
        lead = group.leader.state
        if lead.party_size:          # o lider saindo traz a party REAL dele (pode ter gente de outro grupo do plano)
            self.ours.update(a.name for a in self.accounts if a.state.phase == "hunting" and a.state.party_size
                             and a.state.hunt_name == lead.hunt_name)
        group.leader.finish_hunt()
        if everyone:
            for acc in group.members:
                if acc.state.phase == "hunting" and acc.state.party_size != len(group.accounts):
                    acc.finish_hunt()
        if not all(a.wait_city(30) for a in group.accounts if a.state.phase == "hunting" or a is group.leader):
            raise GameError("nem todos chegaram na cidade")
        self.ours.update(a.name for a in group.accounts)
        if any(self.memory.training(a.name) for a in group.accounts):
            return              # quem vai treinar sai do plano; o resto reagrupa no proximo ciclo
        self._town(group)

    def _note_floor(self, acc):
        pct = acc.read().cap_pct
        if pct is None:
            return
        self.cap_floor[acc.name.casefold()] = pct
        if pct >= self.cfg["capacity_pct"]:
            self._warn_once(("floor", acc.name), f"{acc.name}: depois de vender continua com {pct:.0f}% da capacidade "
                            f"(equipamento/pouch) - o limite de {self.cfg['capacity_pct']}% está baixo; o bot só sai de novo "
                            f"com {pct + FLOOR_MARGIN:.0f}%")

    def _town(self, group):
        """Todos do grupo na cidade: vende, acerta a party e o lider inicia a caça do grupo."""
        if not all(a.name in self.ours for a in group.accounts):
            since = self.city_since.setdefault(group.label, time.time())
            if time.time() - since < self.cfg["idle_city_seconds"]:
                return
            self.log(f"[{group.label}] parado na cidade - o bot assume")
        hunt = group.hunt or self.memory.group(group.names).get("hunt") or self.cfg.get("default_hunt")
        if not hunt:
            self._warn_once(("nohunt", group.label), f"[{group.label}] não sei pra qual caça ir: escolha a caçada padrão na interface")
            return
        for acc in group.accounts:
            acc.sell_all()
            self._note_floor(acc)
        self._fix_party(group)
        group.leader.start_hunt(hunt)
        self.ours.difference_update(group.names)
        self.city_since.pop(group.label, None)

    # ------------------------------------------------------------- party
    def _fix_party(self, group):
        """Deixa a party do jeito do grupo: quem esta numa party errada sai; o lider convida pelo nome; membros aceitam."""
        wanted = {n.casefold() for n in group.names}
        leader = group.leader
        for acc in group.accounts:
            if not acc.read().party_size:
                continue
            info = acc.read_party()
            members = {m.casefold() for m in info.get("members") or []}
            if not (group.is_party and members <= wanted and info.get("leader") == (acc is leader)):
                acc.leave_party()
        if not group.is_party:
            return
        inside = {m.casefold() for m in leader.read_party().get("members") or []} if leader.read().party_size else set()
        missing = [a for a in group.members if a.name.casefold() not in inside]
        if not missing:
            return
        leader.invite_by_name([a.name for a in missing])
        for acc in missing:
            for _ in range(16):
                if acc.read().invite_from:
                    if acc.state.invite_from.casefold() == leader.name.casefold():
                        acc.accept_invite()
                    break
                time.sleep(0.5)
        inside = {m.casefold() for m in leader.read_party().get("members") or []}
        for acc in missing:
            if acc.name.casefold() not in inside:
                self.log(f"[{group.label}] {acc.name} não entrou na party (level fora dos 2/3 do líder?) - fica de fora "
                         f"{self.cfg['party_skip_seconds'] // 60} min")
                self.party_skip[acc.name.casefold()] = time.time() + self.cfg["party_skip_seconds"]
                group.members.remove(acc)
        self.log(f"[{group.label}] party com {len(inside)} -> {group.hunt or 'caça'}")
