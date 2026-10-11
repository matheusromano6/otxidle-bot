"""Motor: le as contas, agrupa (party ou solo), decide e executa os ciclos.

Regras (v1):
- Capacidade: QUALQUER conta do grupo >= capacity_pct -> o lider sai (traz todos) -> CADA conta vende tudo -> o lider
  reinicia a mesma caça (a party continua formada).
- Stamina de caça <= training.stamina_minutes -> grupo pra cidade, vende e cada um treina; volta quando TODAS tiverem
  resume_stamina_minutes (ou a stamina de treino acabar).
- Party: na cidade, antes de caçar, o lider convida pelos amigos quem falta e cada membro aceita. Membro que nao entra
  (ex.: level fora dos 2/3) fica de fora por party_skip_seconds. Membro caçando sem o lider -> sai pra reagrupar.
- Cidade parada sem o bot ter levado: espera idle_city_seconds (pode ser voce mexendo) e assume.
"""
import time

from . import config as cfgmod
from .account import GameError
from .memory import Memory


class Group:
    def __init__(self, leader, members=()):
        self.leader = leader
        self.members = list(members)

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
    """Party ligada e lider aberto: lider + membros configurados que estao abertos (menos 'skip'); o resto joga solo."""
    by_name = {a.name.casefold(): a for a in accounts if a.name}
    party = cfg["party"]
    groups, used = [], set()
    leader = by_name.get((party.get("leader") or "").casefold()) if party.get("enabled") else None
    if leader:
        members = [by_name[m.casefold()] for m in party.get("members") or [] if m.casefold() in by_name and m.casefold() != leader.name.casefold() and m.casefold() not in skip]
        groups.append(Group(leader, members))
        used.update(a.name.casefold() for a in groups[0].accounts)
    for name, acc in by_name.items():
        if name not in used:
            groups.append(Group(acc))
    return groups


FLOOR_MARGIN = 10      # pontos de % acima do "piso" (peso que fica depois de vender) pra sair de novo


def hunt_triggers(states, cfg, floors=None):
    """Motivo pra tirar o grupo da caça ('capacidade' / 'stamina') ou None. 'states' = so' as contas caçando.
    'floors': % de capacidade de cada conta logo depois de vender (equipamento/pouch nao saem): sem isso, um limite
    abaixo do piso faria o grupo sair e voltar sem parar."""
    floors = floors or {}
    for st in states:
        floor = floors.get(st.name.casefold(), 0)
        if st.cap_pct is not None and st.cap_pct >= cfg["capacity_pct"] and st.cap_pct >= floor + FLOOR_MARGIN:
            return "capacidade", f"{st.name} com {st.cap_pct:.0f}% da capacidade"
    tr = cfg["training"]
    if tr["enabled"]:
        for st in states:
            if st.stamina_hunt is not None and st.stamina_hunt <= tr["stamina_minutes"]:
                return "stamina", f"{st.name} com {st.stamina_hunt} min de stamina de caça"
    return None


def training_done(states, cfg):
    """Volta a caçar quando TODAS tem a stamina de caça de volta, ou alguma ficou sem stamina de treino."""
    tr = cfg["training"]
    if any(st.stamina_train is not None and st.stamina_train <= 1 for st in states):
        return True
    return all(st.stamina_hunt is not None and st.stamina_hunt >= tr["resume_stamina_minutes"] for st in states)


class Engine:
    def __init__(self, accounts, cfg, log=print, refresh=None, memory=None):
        self.accounts = accounts
        self.cfg = cfg
        self.log = log
        self.refresh = refresh
        self.memory = memory or Memory()
        self.snapshot = {"states": {}, "groups": {}}
        self.city_since = {}          # nome do grupo -> quando foi visto parado na cidade
        self.ours = set()             # grupos que o BOT levou pra cidade (assume na hora)
        self.cooldown = {}            # grupo -> ate quando nao tentar de novo
        self.party_skip = {}          # membro -> ate quando fica de fora da party
        self.cap_floor = {}           # conta -> % de capacidade logo depois de vender
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

    def tick(self):
        states = self.read_all()
        accounts = [a for a in self.accounts if a.name in states]
        skip = {k for k, until in self.party_skip.items() if time.time() < until}
        groups = build_groups(accounts, self.cfg, skip)
        self.snapshot = {"states": states, "groups": {g.label: g.names for g in groups}}
        self._invites(accounts, groups)
        for group in groups:
            if time.time() < self.cooldown.get(group.label, 0):
                continue
            try:
                self._group(group)
            except Exception as error:
                self.log(f"[{group.label}] falhou: {error} - tento de novo em {self.cfg['cooldown_fail_seconds']}s")
                self.cooldown[group.label] = time.time() + self.cfg["cooldown_fail_seconds"]
                for acc in group.accounts:
                    try:
                        acc.close_modals()
                    except Exception:
                        pass

    def _warn_once(self, key, message):
        if key not in self._warned:
            self._warned.add(key)
            self.log(message)

    # ---------------------------------------------------------- convites
    def _invites(self, accounts, groups):
        """Convite aberto: aceita so' se veio do lider configurado e a conta e' membro dele."""
        party = self.cfg["party"]
        members = {m.casefold() for m in party.get("members") or []}
        leader = (party.get("leader") or "").casefold()
        for acc in accounts:
            st = acc.state
            if not st.invite_from:
                continue
            if party.get("enabled") and st.invite_from.casefold() == leader and acc.name.casefold() in members:
                acc.accept_invite()
            else:
                self._warn_once(("invite", acc.name, st.invite_from),
                                f"{acc.name}: convite de party de {st.invite_from} ignorado (não é o líder configurado)")

    # ------------------------------------------------------------- grupo
    def _group(self, group):
        states = [a.state for a in group.accounts]
        phases = {st.phase for st in states}
        if phases & {"unknown", "leaving"}:
            return
        leader = group.leader
        mem = self.memory.group(group.names)
        if leader.state.phase == "hunting":
            self.city_since.pop(group.label, None)
            self.ours.discard(group.label)
            if leader.state.hunt_name:
                self.memory.update_group(group.names, hunt=leader.state.hunt_name)
            if mem.get("mode") == "training":
                self.memory.update_group(group.names, mode="hunt")
            outside = [a for a in group.members if a.state.phase != "hunting"]
            if outside:
                self._leave(group, f"reagrupar a party ({', '.join(a.name for a in outside)} fora da caça)")
                return
            trigger = hunt_triggers([a.state for a in group.accounts if a.state.phase == "hunting"], self.cfg, self.cap_floor)
            if trigger:
                reason, detail = trigger
                if reason == "stamina":
                    self.memory.update_group(group.names, mode="training")
                self._leave(group, detail)
            return
        # lider fora da caça: membro caçando sozinho volta pra reagrupar
        for acc in group.members:
            if acc.state.phase == "hunting":
                self.log(f"[{group.label}] {acc.name} caçando sem o líder - voltando pra cidade")
                acc.finish_hunt()
                return
        self._town(group, mem)

    def _note_floor(self, acc):
        pct = acc.read().cap_pct
        if pct is None:
            return
        self.cap_floor[acc.name.casefold()] = pct
        if pct >= self.cfg["capacity_pct"]:
            self._warn_once(("floor", acc.name), f"{acc.name}: depois de vender continua com {pct:.0f}% da capacidade "
                            f"(equipamento/pouch) - o limite de {self.cfg['capacity_pct']}% está baixo; o bot só sai de novo "
                            f"com {pct + FLOOR_MARGIN:.0f}%")

    def _skipped(self, acc):
        return time.time() < self.party_skip.get(acc.name.casefold(), 0)

    def _leave(self, group, why):
        self.log(f"[{group.label}] saindo da caça: {why}")
        group.leader.finish_hunt()
        if not all(a.wait_city(30) for a in group.accounts if a.state.phase == "hunting" or a is group.leader):
            raise GameError("nem todos chegaram na cidade")
        self.ours.add(group.label)
        self._town(group, self.memory.group(group.names))

    def _town(self, group, mem):
        """Todos na cidade ou treinando."""
        states = [a.state for a in group.accounts]
        training = [a for a in group.accounts if a.state.phase == "training"]
        if mem.get("mode") == "training" and self.cfg["training"]["enabled"]:
            if training_done(states, self.cfg):
                self.log(f"[{group.label}] stamina de caça recuperada - voltando a caçar")
                for acc in training:
                    acc.end_training()
                self.memory.update_group(group.names, mode="hunt")
                self.ours.add(group.label)
                return
            for acc in group.accounts:
                if acc.state.phase == "city":
                    acc.sell_all()
                    skill = cfgmod.skill_for(self.cfg["training"], acc.name, acc.state.vocation)
                    if not skill:
                        self._warn_once(("skill", acc.name), f"{acc.name}: sem treino definido pra vocação {acc.state.vocation}")
                        continue
                    acc.start_training(skill)
            return
        if training and len(training) == len(group.accounts):
            return          # treino que voce iniciou: o bot nao mexe
        # cidade: o bot so' assume na hora se foi ele que trouxe; senao espera (pode ser voce mexendo)
        if group.label not in self.ours:
            since = self.city_since.setdefault(group.label, time.time())
            if time.time() - since < self.cfg["idle_city_seconds"]:
                return
            self.log(f"[{group.label}] parado na cidade - o bot assume")
        hunt = mem.get("hunt") or self.cfg.get("default_hunt")
        if not hunt:
            self._warn_once(("nohunt", group.label), f"[{group.label}] não sei pra qual caça ir: escolha a caçada padrão na interface")
            return
        for acc in training:
            acc.end_training()
        for acc in group.accounts:
            acc.sell_all()
            self._note_floor(acc)
        if group.is_party:
            self._form_party(group)
        group.leader.start_hunt(hunt)
        self.ours.discard(group.label)
        self.city_since.pop(group.label, None)

    # ------------------------------------------------------------- party
    def _form_party(self, group):
        leader = group.leader
        info = leader.open_friends()
        try:
            inside = {m.casefold() for m in info.get("members") or []}
            missing = [a for a in group.members if a.name.casefold() not in inside and not self._skipped(a)]
            if not missing:
                return
            friends = {f["name"].casefold() for f in info.get("friends") or []}
            invited = []
            for acc in missing:
                if acc.name.casefold() not in friends:
                    self._warn_once(("friend", acc.name), f"[{group.label}] {acc.name} não é amigo de {leader.name}: mande o pedido de amizade")
                    self.party_skip[acc.name.casefold()] = time.time() + self.cfg["party_skip_seconds"]
                    continue
                if leader.invite(acc.name):
                    invited.append(acc)
                    time.sleep(0.5)
        finally:
            leader.close_modals()
        for acc in invited:
            got = False
            for _ in range(16):
                if acc.read().invite_from:
                    acc.accept_invite()
                    got = True
                    break
                time.sleep(0.5)
            if not got:
                self.log(f"[{group.label}] {acc.name} não recebeu o convite")
        inside = {m.casefold() for m in leader.read_friends().get("members") or []}
        for acc in invited:
            if acc.name.casefold() not in inside:
                self.log(f"[{group.label}] {acc.name} não entrou na party (level fora dos 2/3 do líder?) - fica de fora "
                         f"{self.cfg['party_skip_seconds'] // 60} min")
                self.party_skip[acc.name.casefold()] = time.time() + self.cfg["party_skip_seconds"]
        self.log(f"[{group.label}] party: {len(inside)} membro(s)")
