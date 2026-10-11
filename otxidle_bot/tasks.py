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
def load_hunts(path=None):
    path = path or os.path.join(resource_dir(), "otxidle_bot", "data", "hunts.json")
    if not os.path.exists(path):
        path = os.path.join(os.path.dirname(__file__), "data", "hunts.json")
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def hunt_for(hunts, creature, level):
    """Melhor caça com a criatura que a conta aguenta: a de maior level recomendado <= level; senao a mais facil
    permitida (level minimo). None se nenhuma aceita esse level."""
    options = [h for h in hunts if creature.casefold() in (c.casefold() for c in h["creatures"])
               and (h.get("min_level") or 1) <= level]
    if not options:
        return None
    easy = [h for h in options if (h.get("rec_level") or 1) <= level]
    if easy:
        return max(easy, key=lambda h: h.get("rec_level") or 1)["name"]
    return min(options, key=lambda h: h.get("rec_level") or 1)["name"]


def solo_hunt(hunts, level):
    """Caça solo automatica: a de maior level recomendado que a conta ja alcança."""
    easy = [h for h in hunts if (h.get("rec_level") or 1) <= level and (h.get("min_level") or 1) <= level]
    return max(easy, key=lambda h: h.get("rec_level") or 1)["name"] if easy else None


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
    """'RASTREADOR DE TASKS | Orc · 7 pts | 3/183' -> ('Orc', 3, 183); sem task -> None."""
    m = re.search(r"([A-Za-z][\w' -]+?)\s*·\s*\d+\s*pts.*?([\d.,]+)\s*/\s*([\d.,]+)", text or "", re.S)
    if not m:
        return None
    return m.group(1).strip(), _num(m.group(2)), _num(m.group(3))


def choose_card(cards, level, hunts, cfg, other_hunts=()):
    """Carta a pegar (ou None = rerolar/ficar sem). So' cartas com caça possivel pro level e XP/abate >= minimo.
    Preferencia: caça onde outra conta ja esta fazendo task (party) > mais XP por abate."""
    min_xpk = cfg.get("min_xp_per_kill", 0)
    others = {h.casefold() for h in other_hunts if h}
    best, best_key = None, None
    for card in cards:
        if card.status != "available":
            continue
        hunt = hunt_for(hunts, card.creature, level)
        if not hunt or card.xp_per_kill < min_xpk:
            continue
        key = (hunt.casefold() in others, card.xp_per_kill)
        if best_key is None or key > best_key:
            best, best_key = (card, hunt), key
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
            min(options, key=lambda g: len(g.accounts)).accounts.append(acc["name"])
        else:
            hunt = (cfg.get("tasks", {}).get("solo_hunts") or {}).get(acc["name"].casefold()) or solo_hunt(hunts, acc["level"])
            if hunt:
                groups.append(PlanGroup(hunt, [acc["name"]], "solo"))
    # lider: o lider configurado se estiver no grupo, senao o de maior level
    pref = (leader_pref or party.get("leader") or "").casefold()
    for g in groups:
        g.accounts.sort(key=lambda n: (n.casefold() != pref, -names[n.casefold()]["level"]))
    return groups


def _party_phase(accounts, hunts, cfg):
    party = cfg.get("party") or {}
    leader = (party.get("leader") or "").casefold()
    members = [m.casefold() for m in party.get("members") or []]
    by = {a["name"].casefold(): a for a in accounts}
    groups = []
    hunt = party.get("hunt") or cfg.get("default_hunt")
    if party.get("enabled") and leader in by and hunt:
        names = [by[leader]["name"]] + [by[m]["name"] for m in members if m in by and m != leader]
        groups.append(PlanGroup(hunt, names, "party"))
    used = {n.casefold() for g in groups for n in g.accounts}
    for a in accounts:
        if a["name"].casefold() not in used:
            h = (cfg.get("tasks", {}).get("solo_hunts") or {}).get(a["name"].casefold()) or solo_hunt(hunts, a["level"])
            if h:
                groups.append(PlanGroup(h, [a["name"]], "solo"))
    return groups
