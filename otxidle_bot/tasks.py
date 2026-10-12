"""Tasks diarias (logica pura, testavel): ler o quadro, escolher a carta, achar a caça e planejar os grupos do dia.

O dia (renova em tasks.reset_hour):
- Fase de TASKS: cada conta faz ate 'per_day' tasks (dificuldade configurada). Contas com task na MESMA caça caçam juntas
  em party (abates de task contam pra todos da party que tem a criatura). Quem ja terminou AJUDA um grupo que ainda faz
  task (se o level permitir: min da caça e 2/3 entre todos); senao caça solo.
- Fase de PARTY: todas terminaram (cota ou sem carta/token) -> a party configurada vai pra caça padrao da party.
"""
import json
import os
import re
from dataclasses import dataclass, field

from .paths import resource_dir

DIFFICULTIES = ["Iniciante", "Adepto", "Experiente", "Mestre"]
MAX_PARTY = 4


# ------------------------------------------------------------------ catalogo
def user_hunts_path():
    """Lista de caças relida do jogo pelo bot (fica ao lado do .exe e vale mais que a embutida)."""
    from .paths import app_dir
    return os.path.join(app_dir(), "hunts.json")


def load_hunts(path=None):
    if path is None and os.path.exists(user_hunts_path()):
        path = user_hunts_path()
    path = path or os.path.join(resource_dir(), "otxidle_bot", "data", "hunts.json")
    if not os.path.exists(path):
        path = os.path.join(os.path.dirname(__file__), "data", "hunts.json")
    with open(path, encoding="utf-8") as file:
        data = json.load(file)
    return data["hunts"] if isinstance(data, dict) else data


def hunts_age(path=None):
    """Segundos desde a ultima releitura da lista (infinito se nunca releu)."""
    path = path or user_hunts_path()
    try:
        with open(path, encoding="utf-8") as file:
            return max(0.0, __import__("time").time() - float(json.load(file).get("read_at", 0)))
    except (OSError, ValueError, AttributeError):
        return float("inf")


def save_hunts(hunts, path=None):
    with open(path or user_hunts_path(), "w", encoding="utf-8") as file:
        json.dump({"read_at": __import__("time").time(), "hunts": hunts}, file, ensure_ascii=False, indent=1)


def strongest_hunt(hunts, max_rec, min_level, current=None):
    """Modo XP: a caça mais forte permitida (recomendado <= max_rec, minimo <= min_level). Empate de level recomendado
    com a atual = fica na atual (nao fica trocando)."""
    options = [h for h in hunts if (h.get("rec_level") or 1) <= max_rec and (h.get("min_level") or 1) <= min_level]
    if not options:
        return None
    top = max(h.get("rec_level") or 1 for h in options)
    now = next((h for h in options if current and h["name"].casefold() == current.casefold()), None)
    if now is not None and (now.get("rec_level") or 1) >= top:
        return now["name"]
    return max(options, key=lambda h: (h.get("rec_level") or 1, len(h["creatures"])))["name"]


def hunt_options(hunts, creature, level, over=0):
    """Caças com a criatura que o jogo libera (level minimo) e com level recomendado <= level + over."""
    return [h for h in hunts if creature.casefold() in (c.casefold() for c in h["creatures"])
            and (h.get("min_level") or 1) <= level and (h.get("rec_level") or 1) <= level + over]


def hunt_for(hunts, creature, level, over=0):
    """Melhor caça com a criatura: a de maior level recomendado <= level + over. None se nenhuma serve.
    Regra do usuario: sozinho over=0 (recomendado <= level); com outra conta na mesma caça ate group_level_over (5)."""
    options = hunt_options(hunts, creature, level, over)
    if not options:
        return None
    return max(options, key=lambda h: h.get("rec_level") or 1)["name"]


def solo_hunt(hunts, level):
    """Caça solo automatica: a de maior level recomendado que a conta ja alcança."""
    easy = [h for h in hunts if (h.get("rec_level") or 1) <= level and (h.get("min_level") or 1) <= level]
    return max(easy, key=lambda h: h.get("rec_level") or 1)["name"] if easy else None


def party_hunt(hunts, leader_level, levels, over=5):
    """Caça automatica da party (quando 'Caça da party' esta vazia): recomendado ate 'over' acima do LIDER e level
    minimo que TODOS alcançam (senao o jogo nao deixa entrar). Empate: a de mais tipos de criatura."""
    low = min([leader_level] + list(levels))
    options = [h for h in hunts if (h.get("rec_level") or 1) <= leader_level + over and (h.get("min_level") or 1) <= low]
    if not options:
        return None
    return max(options, key=lambda h: (h.get("rec_level") or 1, len(h["creatures"])))["name"]


def hunt_rec_level(hunts, name):
    return next((h.get("rec_level") or 1 for h in hunts if h["name"].casefold() == (name or "").casefold()), 1)


def hunt_min_level(hunts, name):
    return next((h.get("min_level") or 1 for h in hunts if h["name"].casefold() == (name or "").casefold()), 1)


def levels_ok(levels):
    """Regra da party do jogo: levels dentro de 2/3 um do outro."""
    levels = [lv for lv in levels if lv]
    return not levels or min(levels) * 3 >= max(levels) * 2


# --------------------------------------------------------------- quadro
@dataclass
class Card:
    creature: str
    kills: int = 0
    need: int = 0
    xp: int = 0
    points: int = 0
    status: str = "available"      # available / progress / complete

    @property
    def xp_per_kill(self):
        return self.xp / self.need if self.need else 0


@dataclass
class Board:
    cards: list = field(default_factory=list)
    difficulty: str = ""
    tokens: int = 0
    points: int = 0

    @property
    def active(self):
        return next((c for c in self.cards if c.status in ("progress", "complete")), None)


def _num(text):
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else 0


def parse_board(raw):
    """raw (do BOARD_JS da conta): {'cards': [{'creature', 'kills', 'rewards': {...}, 'button'}], 'difficulty', 'footer'}."""
    board = Board(difficulty=(raw.get("difficulty") or "").title())
    for c in raw.get("cards") or []:
        m = re.search(r"([\d.,]+)\s*/\s*([\d.,]+)", c.get("kills") or "")
        button = (c.get("button") or "").casefold()
        status = "complete" if "completar" in button else "progress" if "progresso" in button else "available"
        rewards = c.get("rewards") or {}
        board.cards.append(Card(creature=(c.get("creature") or "").strip(), kills=_num(m.group(1)) if m else 0,
                                need=_num(m.group(2)) if m else 0, xp=_num(rewards.get("XP")),
                                points=_num(rewards.get("Bounty points")), status=status))
    footer = raw.get("footer") or ""
    m = re.search(r"BOUNTY POINTS\s*\|?\s*([\d.,]+)", footer, re.I)
    board.points = _num(m.group(1)) if m else 0
    m = re.search(r"TOKENS DE REROLL\s*\|?\s*([\d.,]+)", footer, re.I)
    board.tokens = _num(m.group(1)) if m else 0
    return board


def parse_tracker(text):
    """'RASTREADOR DE TASKS | Orc · 7 pts | 3/183' -> ('Orc', 3, 183). Task cheia o jogo mostra 'ready' no lugar dos
    numeros (confirmado ao vivo) -> ('Orc', 1, 1). Sem task -> None."""
    m = re.search(r"([A-Za-z][\w' -]+?)\s*·\s*\d+\s*pts\W*(ready|([\d.,]+)\s*/\s*([\d.,]+))", text or "", re.S | re.I)
    if not m:
        return None
    if m.group(2).casefold() == "ready":
        return m.group(1).strip(), 1, 1
    return m.group(1).strip(), _num(m.group(3)), _num(m.group(4))


def choose_card(cards, level, hunts, cfg, others=()):
    """Carta a pegar: (card, caça, junta) ou None. 'others' = [(caça, level)] das tasks das OUTRAS contas.
    - junta: a caça da carta e' a de outra conta com level compativel (2/3) -> aceita caça ate group_level_over acima;
    - sozinho: so' caça com recomendado <= level.
    Preferencia: junta > mais XP por abate. Cartas abaixo de min_xp_per_kill ficam de fora."""
    min_xpk = cfg.get("min_xp_per_kill", 0)
    over = cfg.get("group_level_over", 5)
    best, best_key = None, None
    for card in cards:
        if card.status != "available" or card.xp_per_kill < min_xpk:
            continue
        options = []
        for hunt, other_level in others:
            if hunt and levels_ok([level, other_level]) and any(
                    h["name"].casefold() == hunt.casefold() for h in hunt_options(hunts, card.creature, level, over)):
                options.append((hunt, True))
        solo = hunt_for(hunts, card.creature, level)
        if solo:
            options.append((solo, False))
        for hunt, together in options:
            key = (together, card.xp_per_kill)
            if best_key is None or key > best_key:
                best, best_key = (card, hunt, together), key
    return best


# -------------------------------------------------------------- plano
@dataclass
class PlanGroup:
    hunt: str
    accounts: list                  # nomes; o 1o e' o lider
    reason: str = "task"            # task / ajuda / party / solo

    @property
    def leader(self):
        return self.accounts[0]


def plan(accounts, hunts, cfg, leader_pref=""):
    """accounts: [{'name', 'level', 'task_hunt' (None = sem task), 'done' (terminou o dia)}] -> [PlanGroup].
    Fase de party quando TODAS terminaram; senao grupos por caça de task + ajudantes + solo."""
    party = cfg.get("party") or {}
    names = {a["name"].casefold(): a for a in accounts}
    if accounts and all(a["done"] for a in accounts):
        return _party_phase(accounts, hunts, cfg)
    groups = []
    # 1) grupos por caça de task (respeitando 2/3 e 4 por party)
    for acc in sorted([a for a in accounts if a.get("task_hunt") and not a["done"]], key=lambda a: -a["level"]):
        target = next((g for g in groups if g.hunt.casefold() == acc["task_hunt"].casefold() and len(g.accounts) < MAX_PARTY
                       and levels_ok([names[n.casefold()]["level"] for n in g.accounts] + [acc["level"]])), None)
        if target:
            target.accounts.append(acc["name"])
        else:
            groups.append(PlanGroup(acc["task_hunt"], [acc["name"]], "task"))
    # 2) quem terminou (ou esta sem task) ajuda um grupo de task; senao solo
    for acc in sorted([a for a in accounts if not (a.get("task_hunt") and not a["done"])], key=lambda a: -a["level"]):
        options = [g for g in groups if g.reason == "task" and len(g.accounts) < MAX_PARTY
                   and hunt_min_level(hunts, g.hunt) <= acc["level"]
                   and levels_ok([names[n.casefold()]["level"] for n in g.accounts] + [acc["level"]])]
        if cfg.get("tasks", {}).get("helpers", True) and options:
            # prioridade: grupo numa caça ACIMA do level de quem esta nele (pegou a task contando com ajuda),
            # depois o grupo com menos gente
            def need(g):
                top = max(names[n.casefold()]["level"] for n in g.accounts)
                return hunt_rec_level(hunts, g.hunt) > top
            min(options, key=lambda g: (not need(g), len(g.accounts))).accounts.append(acc["name"])
        else:
            hunt = (cfg.get("tasks", {}).get("solo_hunts") or {}).get(acc["name"].casefold()) or solo_hunt(hunts, acc["level"])
            if hunt:
                groups.append(PlanGroup(hunt, [acc["name"]], "solo"))
    # lider: o lider configurado se estiver no grupo, senao o de maior level
    pref = (leader_pref or party.get("leader") or "").casefold()
    for g in groups:
        g.accounts.sort(key=lambda n: (n.casefold() != pref, -names[n.casefold()]["level"]))
    return groups


# ------------------------------------------------- party primeiro (v2.1)
def _account_score(there, a):
    """Pontos de UMA conta numa caça (criaturas 'there'): Paw ativo la' = 10 (Paw primeiro: a lista e' igual pra todas),
    diaria ativa = 3; sem diaria/Paw ativos, carta/opcao de Paw disponivel la' = 1 (pega de graça)."""
    score = 0
    paw = (a.get("paw") or "").casefold()
    if paw:
        score += 10 if paw in there else 0
    elif any(c.casefold() in there for c in a.get("paw_options") or []):
        score += 1
    daily = (a.get("daily") or "").casefold()
    if daily:
        score += 3 if daily in there else 0
    elif any(c.casefold() in there for c in a.get("cards") or []):
        score += 1
    return score


def hunt_score(hunt, accounts):
    """(quantas contas tem task la', pontos). Prioridade do usuario: caça com task de TODAS juntas."""
    there = {c.casefold() for c in hunt["creatures"]}
    scores = [_account_score(there, a) for a in accounts]
    return sum(1 for x in scores if x), sum(scores)


def best_hunt(hunts, accounts, max_rec, min_level, current=None, fallback=None):
    """Caça com task pra mais contas (depois mais pontos; empate = a mais forte) entre as permitidas
    (recomendado <= max_rec, minimo <= min_level). Nenhuma com task -> 'fallback' (caça padrao da party) ou a mais
    forte permitida. A atual so' e' trocada se outra for MELHOR (subir de level sozinho nao troca)."""
    options = [h for h in hunts if (h.get("rec_level") or 1) <= max_rec and (h.get("min_level") or 1) <= min_level]
    if not options:
        return None, (0, 0)
    best = max(options, key=lambda h: (hunt_score(h, accounts), h.get("rec_level") or 1, len(h["creatures"])))
    best_score = hunt_score(best, accounts)
    if best_score[1] == 0:
        if fallback:
            return fallback, best_score
        now = next((h for h in options if current and h["name"].casefold() == current.casefold()), None)
        return (now or best)["name"], best_score
    now = next((h for h in options if current and h["name"].casefold() == current.casefold()), None)
    if now is not None and hunt_score(now, accounts) >= best_score:
        return now["name"], best_score
    return best["name"], best_score


def plan_party_first(accounts, hunts, cfg, current=None):
    """Party de 4 primeiro (juntas aguentam criaturas mais fortes) e as tasks seguem a caça da party.
    accounts: [{'name', 'level', 'daily', 'cards', 'paw', 'paw_options'}] (so' as que estao jogando).
    current: {nome: caça atual do grupo da conta} pra estabilidade. Fora da party (2/3) = solo com caça segura."""
    party = cfg.get("party") or {}
    over = cfg.get("tasks", {}).get("group_level_over", 5)
    by = {a["name"].casefold(): a for a in accounts}
    current = {k.casefold(): v for k, v in (current or {}).items()}
    leader = by.get((party.get("leader") or "").casefold())
    if leader is None and accounts:
        leader = max(accounts, key=lambda a: a["level"])
    groups = []
    members = []
    if leader is not None and party.get("enabled"):
        wanted = [m.casefold() for m in party.get("members") or []]
        members = [leader] + [by[m] for m in wanted if m in by and m != leader["name"].casefold()
                              and levels_ok([leader["level"], by[m]["level"]])]
    if len(members) >= 2:
        max_rec, low, now = leader["level"] + over, min(a["level"] for a in members), current.get(leader["name"].casefold())
        if (cfg.get("tasks") or {}).get("priority", "xp") == "xp":
            # LEVEL primeiro (usuario): a caça mais forte que a party aguenta; tasks/Paw so' de carona
            hunt = party.get("hunt") or strongest_hunt(hunts, max_rec, low, now)
        else:
            # 'Caça da party' = caça PADRAO: so' quando nenhuma caça tem task das contas
            hunt = best_hunt(hunts, members, max_rec, low, now, fallback=party.get("hunt") or None)[0]
        if hunt:
            groups.append(PlanGroup(hunt, [a["name"] for a in members], "party"))
    used = {n.casefold() for g in groups for n in g.accounts}
    for a in accounts:
        if a["name"].casefold() in used:
            continue
        hunt = (cfg.get("tasks", {}).get("solo_hunts") or {}).get(a["name"].casefold()) or \
            best_hunt(hunts, [a], a["level"], a["level"], current.get(a["name"].casefold()))[0]
        if hunt:
            groups.append(PlanGroup(hunt, [a["name"]], "solo"))
    return groups


def _party_phase(accounts, hunts, cfg):
    party = cfg.get("party") or {}
    leader = (party.get("leader") or "").casefold()
    members = [m.casefold() for m in party.get("members") or []]
    by = {a["name"].casefold(): a for a in accounts}
    groups = []
    if party.get("enabled") and leader in by:
        names = [by[leader]["name"]] + [by[m]["name"] for m in members if m in by and m != leader
                                        and levels_ok([by[leader]["level"], by[m]["level"]])]
        over = cfg.get("tasks", {}).get("group_level_over", 5)
        hunt = party.get("hunt") or party_hunt(hunts, by[leader]["level"], [by[n.casefold()]["level"] for n in names], over)
        if hunt:
            groups.append(PlanGroup(hunt, names, "party"))
    used = {n.casefold() for g in groups for n in g.accounts}
    for a in accounts:
        if a["name"].casefold() not in used:
            h = (cfg.get("tasks", {}).get("solo_hunts") or {}).get(a["name"].casefold()) or solo_hunt(hunts, a["level"])
            if h:
                groups.append(PlanGroup(h, [a["name"]], "solo"))
    return groups
