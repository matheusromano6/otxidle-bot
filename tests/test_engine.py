import copy
import unittest

from otxidle_bot import config
from otxidle_bot import tasks as T
from otxidle_bot.account import State
from otxidle_bot.engine import Engine, build_groups, hunt_triggers, training_done
from otxidle_bot.memory import Memory

HUNTS = [
    {"name": "Rat Cellars", "rec_level": 1, "min_level": 1, "creatures": ["Rat", "Cave Rat"]},
    {"name": "Troll Hills", "rec_level": 6, "min_level": 1, "creatures": ["Troll"]},
    {"name": "Orc Camp", "rec_level": 8, "min_level": 1, "creatures": ["Orc", "Orc Warrior"]},
    {"name": "Folda Icefields", "rec_level": 12, "min_level": 10, "creatures": ["Frost Troll", "Badger"]},
    {"name": "Marsh Stalkers", "rec_level": 15, "min_level": 12, "creatures": ["Swampling"]},
]


class World:
    """Simula as parties do jogo: lider saindo traz todos; membro saindo sai da party (party de 1 some)."""

    def __init__(self):
        self.accounts = []
        self.parties = {}             # lider -> [membros]

    def party_of(self, name):
        for leader, members in self.parties.items():
            if name == leader or name in members:
                return leader, members
        return None, None

    def sizes(self):
        for acc in self.accounts:
            leader, members = self.party_of(acc.name)
            acc.state.party_size = len(members) + 1 if leader else 0


class FakeAccount:
    """Conta falsa: as acoes mudam o estado como o jogo faz (confirmado ao vivo)."""

    def __init__(self, world, name, phase="hunting", cap_free=300, cap_max=500, stamina=600, train=720, vocation="Knight",
                 level=10, hunt="Troll Hills", board=None):
        self.world = world
        world.accounts.append(self)
        self.name = name
        self.state = State(name=name, level=level, vocation=vocation, phase=phase, hunt_name=hunt if phase == "hunting" else "",
                           cap_free=cap_free, cap_max=cap_max, stamina_hunt=stamina, stamina_train=train)
        self.actions = []
        self.board = board

    def read(self):
        self.world.sizes()
        if self.board and self.board.active:
            a = self.board.active
            self.state.task = (a.creature, a.kills, a.need)
            self.state.tracker_shown = True
        return self.state

    def close_modals(self):
        pass

    def show_task_tracker(self):
        self.actions.append("tracker")

    def finish_hunt(self):
        self.actions.append("finish")
        leader, members = self.world.party_of(self.name)
        if leader == self.name:
            for acc in self.world.accounts:
                if acc.name in members:
                    acc.state.phase, acc.state.hunt_name = "city", ""
        elif leader:
            members.remove(self.name)
            if not members:
                del self.world.parties[leader]
        self.state.phase, self.state.hunt_name = "city", ""

    def wait_city(self, timeout=30):
        return self.read().phase == "city"

    def sell_all(self):
        self.actions.append("sell")
        self.state.cap_free = self.state.cap_max
        return 10

    def start_hunt(self, hunt):
        self.actions.append(f"hunt:{hunt}")
        leader, members = self.world.party_of(self.name)
        for acc in self.world.accounts:
            if acc is self or (leader == self.name and acc.name in members):
                acc.state.phase, acc.state.hunt_name = "hunting", hunt

    def start_training(self, skill):
        self.actions.append(f"train:{skill}")
        self.state.phase = "training"

    def end_training(self):
        self.actions.append("end_training")
        self.state.phase = "city"

    # party
    def read_party(self):
        leader, members = self.world.party_of(self.name)
        return {"members": ([leader] + members) if leader else [], "leader": leader == self.name}

    def leave_party(self):
        self.actions.append("leave_party")
        leader, members = self.world.party_of(self.name)
        if leader == self.name:
            del self.world.parties[leader]
        elif leader:
            members.remove(self.name)
            if not members:
                del self.world.parties[leader]

    def invite_by_name(self, names):
        for name in names:
            self.actions.append(f"invite:{name}")
            next(a for a in self.world.accounts if a.name == name).state.invite_from = self.name

    def accept_invite(self):
        self.actions.append("accept")
        self.world.parties.setdefault(self.state.invite_from, []).append(self.name)
        self.state.invite_from = ""

    # tasks
    def open_board(self):
        self.actions.append("board")
        return self.board

    def complete_task(self, creature):
        self.actions.append(f"complete:{creature}")
        self.board = T.Board(cards=[T.Card("Rat", 0, 90, 150, 3), T.Card("Troll", 0, 90, 600, 3), T.Card("Cave Rat", 0, 80, 200, 3)],
                             difficulty=self.board.difficulty, tokens=self.board.tokens + 1)
        self.state.task = None
        return self.board

    def reroll(self, difficulty):
        self.actions.append(f"reroll:{difficulty}")
        self.board = T.Board(cards=[T.Card("Orc", 0, 180, 1600, 7), T.Card("Swampling", 0, 178, 2800, 7),
                                    T.Card("Orc Warrior", 0, 118, 2065, 7)],
                             difficulty=difficulty, tokens=self.board.tokens - 1)
        return self.board

    def select_task(self, creature):
        self.actions.append(f"select:{creature}")
        for card in self.board.cards:
            if card.creature == creature:
                card.status = "progress"


def make_cfg(tasks=False, **changes):
    cfg = copy.deepcopy(config.DEFAULTS)
    cfg["tasks"]["enabled"] = tasks
    cfg.update(changes)
    return cfg


def engine_for(world, cfg):
    return Engine(world.accounts, cfg, log=lambda m: None, memory=Memory(), hunts=HUNTS)


def board(active=None, kills=0, need=100, difficulty="Adepto", tokens=2):
    cards = [T.Card("Rat", 0, 90, 150, 3), T.Card("Cave Rat", 0, 80, 200, 3)]
    if active:
        cards.insert(0, T.Card(active, kills, need, 1600, 7, "complete" if kills >= need else "progress"))
    return T.Board(cards=cards, difficulty=difficulty, tokens=tokens)


class TriggerTest(unittest.TestCase):
    def test_capacity_and_stamina(self):
        cfg = make_cfg()
        full = State(name="a", cap_free=50, cap_max=500, stamina_hunt=600)
        tired = State(name="b", cap_free=400, cap_max=500, stamina_hunt=10)
        fine = State(name="c", cap_free=400, cap_max=500, stamina_hunt=600)
        self.assertEqual(hunt_triggers([fine, full], cfg)[0], "capacidade")
        self.assertEqual(hunt_triggers([fine, tired], cfg)[:3:2], ("stamina", ["b"]))
        self.assertIsNone(hunt_triggers([fine], cfg))
        cfg["training"]["enabled"] = False
        self.assertIsNone(hunt_triggers([tired], cfg))

    def test_capacity_floor(self):
        cfg = make_cfg(capacity_pct=40)
        st = State(name="A", cap_free=265, cap_max=500, stamina_hunt=600)          # 47%
        self.assertEqual(hunt_triggers([st], cfg)[0], "capacidade")
        self.assertIsNone(hunt_triggers([st], cfg, {"a": 47}))                      # piso depois de vender
        st.cap_free = 200                                                          # 60%
        self.assertEqual(hunt_triggers([st], cfg, {"a": 47})[0], "capacidade")

    def test_training_done(self):
        cfg = make_cfg()
        self.assertFalse(training_done(State(stamina_hunt=100, stamina_train=300), cfg))
        self.assertTrue(training_done(State(stamina_hunt=650, stamina_train=300), cfg))
        self.assertTrue(training_done(State(stamina_hunt=100, stamina_train=0), cfg))


class GroupTest(unittest.TestCase):
    def test_groups_v1(self):
        w = World()
        accs = [FakeAccount(w, n) for n in ("Lider", "Um", "Dois", "Solo")]
        cfg = make_cfg(party={"enabled": True, "leader": "lider", "members": ["um", "dois", "fechado"]})
        self.assertEqual([g.names for g in build_groups(accs, cfg)], [["Lider", "Um", "Dois"], ["Solo"]])
        self.assertEqual([g.names for g in build_groups(accs, cfg, skip={"dois"})], [["Lider", "Um"], ["Dois"], ["Solo"]])
        cfg["party"]["enabled"] = False
        self.assertEqual(len(build_groups(accs, cfg)), 4)


class EngineV1Test(unittest.TestCase):
    def test_solo_capacity_cycle(self):
        w = World()
        acc = FakeAccount(w, "Solo", cap_free=40)
        engine_for(w, make_cfg()).tick()
        self.assertEqual(acc.actions, ["finish", "sell", "hunt:Troll Hills"])
        self.assertEqual(acc.state.phase, "hunting")

    def test_party_capacity_cycle_keeps_party(self):
        w = World()
        leader, um = FakeAccount(w, "Lider", cap_free=20), FakeAccount(w, "Um")
        w.parties["Lider"] = ["Um"]
        engine_for(w, make_cfg(party={"enabled": True, "leader": "lider", "members": ["um"]})).tick()
        self.assertEqual(leader.actions, ["finish", "sell", "hunt:Troll Hills"])
        self.assertEqual(um.actions, ["sell"])
        self.assertEqual(um.state.phase, "hunting")

    def test_party_formation_in_city(self):
        w = World()
        leader = FakeAccount(w, "Lider", phase="city")
        um, dois = FakeAccount(w, "Um", phase="city"), FakeAccount(w, "Dois", phase="city")
        cfg = make_cfg(party={"enabled": True, "leader": "lider", "members": ["um", "dois"]}, idle_city_seconds=0,
                       default_hunt="Troll Hills")
        engine_for(w, cfg).tick()
        self.assertEqual(leader.actions, ["sell", "invite:Um", "invite:Dois", "hunt:Troll Hills"])
        self.assertEqual(um.actions, ["sell", "accept"])
        self.assertEqual(w.parties, {"Lider": ["Um", "Dois"]})
        self.assertEqual({a.state.phase for a in (leader, um, dois)}, {"hunting"})

    def test_city_waits_for_user_then_takes_over(self):
        w = World()
        acc = FakeAccount(w, "Solo", phase="city")
        eng = engine_for(w, make_cfg(default_hunt="Rat Cellars"))
        eng.tick()
        self.assertEqual(acc.actions, [])          # pode ser o usuario mexendo
        eng.city_since["Solo"] -= 1000
        eng.tick()
        self.assertEqual(acc.actions, ["sell", "hunt:Rat Cellars"])

    def test_no_loop_when_floor_above_limit(self):
        w = World()
        acc = FakeAccount(w, "Solo", cap_free=200, cap_max=500)       # 60%
        acc.sell_all = lambda: (acc.actions.append("sell"), setattr(acc.state, "cap_free", 260))  # fica 48% (equipamento)
        eng = engine_for(w, make_cfg(capacity_pct=40))
        eng.tick()
        eng.tick()
        self.assertEqual(acc.actions, ["finish", "sell", "hunt:Troll Hills"])

    def test_stamina_goes_training_and_back(self):
        w = World()
        acc = FakeAccount(w, "Solo", stamina=10, vocation="Druid")
        eng = engine_for(w, make_cfg())
        eng.tick()
        self.assertEqual(acc.actions, ["finish"])
        eng.tick()
        self.assertEqual(acc.actions, ["finish", "sell", "train:Magic"])
        acc.actions.clear()
        eng.tick()
        self.assertEqual(acc.actions, [])           # treinando, stamina ainda baixa
        acc.state.stamina_hunt = 650
        eng.tick()
        self.assertEqual(acc.actions, ["end_training"])
        
        eng.tick()
        self.assertEqual(acc.actions, ["end_training", "sell", "hunt:Troll Hills"])

    def test_invite_from_stranger_ignored(self):
        w = World()
        acc = FakeAccount(w, "Um")
        acc.state.invite_from = "Estranho"
        engine_for(w, make_cfg(party={"enabled": True, "leader": "lider", "members": ["um"]})).tick()
        self.assertNotIn("accept", acc.actions)

    def test_member_alone_in_hunt_returns(self):
        w = World()
        FakeAccount(w, "Lider", phase="city")
        um = FakeAccount(w, "Um")
        engine_for(w, make_cfg(party={"enabled": True, "leader": "lider", "members": ["um"]})).tick()
        self.assertEqual(um.actions, ["finish"])

    def test_skill_choice(self):
        tr = config.DEFAULTS["training"]
        self.assertEqual(config.skill_for(tr, "x", "Elite Knight"), "Axe")
        self.assertEqual(config.skill_for(dict(tr, by_name={"x": "Club"}), "X", "Knight"), "Club")


class TasksLogicTest(unittest.TestCase):
    def test_hunt_for_level(self):
        self.assertEqual(T.hunt_for(HUNTS, "Orc", 10), "Orc Camp")
        self.assertIsNone(T.hunt_for(HUNTS, "Swampling", 13))                 # sozinho: recomendado 15 > 13
        self.assertEqual(T.hunt_for(HUNTS, "Swampling", 15), "Marsh Stalkers")
        self.assertEqual(T.hunt_for(HUNTS, "Swampling", 12, over=5), "Marsh Stalkers")   # junto: ate +5
        self.assertIsNone(T.hunt_for(HUNTS, "Swampling", 11, over=5))         # level minimo 12 do jogo
        self.assertEqual(T.solo_hunt(HUNTS, 13), "Folda Icefields")
        self.assertTrue(T.levels_ok([12, 8]))
        self.assertFalse(T.levels_ok([13, 8]))

    def test_choose_card_prefers_shared_hunt_then_xp(self):
        cards = [T.Card("Orc", 0, 183, 1601, 7), T.Card("Swampling", 0, 178, 2804, 7), T.Card("Troll", 0, 90, 900, 7)]
        cfg = config.DEFAULTS["tasks"]
        pick = T.choose_card(cards, 13, HUNTS, cfg)
        self.assertEqual((pick[0].creature, pick[2]), ("Troll", False))       # sozinho: Swampling (rec 15) fica de fora
        pick = T.choose_card(cards, 13, HUNTS, cfg, [("Marsh Stalkers", 12)])
        self.assertEqual((pick[0].creature, pick[1], pick[2]), ("Swampling", "Marsh Stalkers", True))   # junto: ate +5
        pick = T.choose_card(cards, 13, HUNTS, cfg, [("Orc Camp", 11)])
        self.assertEqual((pick[0].creature, pick[2]), ("Orc", True))          # junta mesmo pagando menos
        pick = T.choose_card(cards, 13, HUNTS, cfg, [("Marsh Stalkers", 8)])
        self.assertEqual((pick[0].creature, pick[2]), ("Troll", False))       # 8 fora dos 2/3 de 13: nao junta
        self.assertIsNone(T.choose_card(cards, 10, HUNTS, dict(cfg, min_xp_per_kill=20)))

    def test_parse_board_and_tracker(self):
        raw = {"difficulty": "ADEPTO", "footer": "MELHORAR | BOUNTY POINTS | 6 | TOKENS DE REROLL | 2",
               "cards": [{"creature": "Orc", "kills": "183/183 abates", "rewards": {"XP": "1,601", "Bounty points": "7"},
                          "button": "Completar"},
                         {"creature": "Swampling", "kills": "0/178 abates", "rewards": {"XP": "2,804"}, "button": "Selecionar task"}]}
        b = T.parse_board(raw)
        self.assertEqual((b.difficulty, b.points, b.tokens), ("Adepto", 6, 2))
        self.assertEqual((b.active.creature, b.active.status, b.cards[0].xp), ("Orc", "complete", 1601))
        self.assertEqual(T.parse_tracker("Rastreador de Tasks | RASTREADOR DE TASKS\nOrc Warrior · 7 pts\n12/118"), ("Orc Warrior", 12, 118))
        self.assertIsNone(T.parse_tracker("RASTREADOR DE BESTIARY\nTroll\n0/50"))
        self.assertEqual(T.parse_tracker("Rastreador de Tasks | RASTREADOR DE TASKS\nOrc · 7 pts\nready"), ("Orc", 1, 1))

    def test_plan_groups_by_task_hunt_and_helpers(self):
        cfg = make_cfg(tasks=True, party={"enabled": True, "leader": "kina", "members": [], "hunt": "Folda Icefields"})
        accs = [{"name": "Kina", "level": 13, "task_hunt": "Orc Camp", "done": False},
                {"name": "Pally", "level": 11, "task_hunt": "Orc Camp", "done": False},
                {"name": "Druid", "level": 10, "task_hunt": "Troll Hills", "done": False},
                {"name": "Sorc", "level": 9, "task_hunt": None, "done": True}]
        groups = T.plan(accs, HUNTS, cfg)
        self.assertEqual([(g.hunt, g.accounts, g.reason) for g in groups],
                         [("Orc Camp", ["Kina", "Pally"], "task"), ("Troll Hills", ["Druid", "Sorc"], "task")])

    def test_plan_respects_two_thirds(self):
        cfg = make_cfg(tasks=True)
        accs = [{"name": "Alto", "level": 15, "task_hunt": "Orc Camp", "done": False},
                {"name": "Baixo", "level": 8, "task_hunt": "Orc Camp", "done": False}]
        self.assertEqual([g.accounts for g in T.plan(accs, HUNTS, cfg)], [["Alto"], ["Baixo"]])

    def test_plan_party_phase_when_all_done(self):
        cfg = make_cfg(tasks=True, party={"enabled": True, "leader": "kina", "members": ["pally", "sorc"], "hunt": "Orc Camp"})
        accs = [{"name": n, "level": lv, "task_hunt": None, "done": True} for n, lv in (("Kina", 13), ("Pally", 11), ("Sorc", 9), ("Druid", 10))]
        groups = T.plan(accs, HUNTS, cfg)
        self.assertEqual((groups[0].hunt, groups[0].accounts, groups[0].reason), ("Orc Camp", ["Kina", "Pally", "Sorc"], "party"))
        self.assertEqual((groups[1].accounts, groups[1].reason), (["Druid"], "solo"))


class EngineTasksTest(unittest.TestCase):
    def test_completes_rerolls_and_picks_while_hunting(self):
        w = World()
        acc = FakeAccount(w, "Kina", level=13, hunt="Orc Camp", board=board("Orc", 183, 183, difficulty="Iniciante"))
        eng = engine_for(w, make_cfg(tasks=True))
        eng.tick()
        self.assertEqual(acc.actions[:4], ["board", "complete:Orc", "reroll:Adepto", "select:Orc Warrior"])
        day = eng.memory.tasks_today(eng.snapshot and __import__("otxidle_bot.engine", fromlist=["task_day"]).task_day(eng.cfg))
        self.assertEqual((day["kina"]["done"], day["kina"]["hunt"]), (1, "Orc Camp"))

    def test_rerolls_to_join_another_account(self):
        w = World()
        kina = FakeAccount(w, "Kina", level=13, hunt="Orc Camp", board=board("Orc", 183, 183))
        FakeAccount(w, "Pally", level=11, hunt="Orc Camp", board=board("Orc Warrior", 5, 118))
        w.parties["Kina"] = ["Pally"]
        eng = engine_for(w, make_cfg(tasks=True, party={"enabled": True, "leader": "kina", "members": [], "hunt": ""}))
        eng.tick()
        # cartas da entrega (Rat/Troll/Cave Rat) nao juntam com o Pally -> rerola -> Orc Warrior no Orc Camp
        self.assertEqual(kina.actions[:4], ["board", "complete:Orc", "reroll:Adepto", "select:Orc Warrior"])

    def test_new_task_elsewhere_regroups(self):
        w = World()
        kina = FakeAccount(w, "Kina", level=13, hunt="Orc Camp", board=board("Orc", 10, 183))
        pally = FakeAccount(w, "Pally", level=11, hunt="Orc Camp", board=board("Orc Warrior", 5, 118))
        w.parties["Kina"] = ["Pally"]
        eng = engine_for(w, make_cfg(tasks=True, party={"enabled": True, "leader": "kina", "members": [], "hunt": ""}))
        eng.tick()
        self.assertNotIn("finish", kina.actions)                    # plano bate com a realidade
        pally.board = board("Troll", 0, 90)                         # Pally trocou de task: Troll Hills
        pally.state.task = None
        eng.tick()                                                  # 1a leitura diferente: espera confirmar
        eng.tick()
        self.assertIn("finish", kina.actions)
        self.assertEqual(kina.state.hunt_name, "Orc Camp")
        self.assertEqual(pally.state.hunt_name, "Troll Hills")
        self.assertEqual(w.parties, {})
        self.assertIn("leave_party", kina.actions + pally.actions)

    def test_done_account_helps(self):
        w = World()
        kina = FakeAccount(w, "Kina", phase="city", level=13, board=board("Orc", 10, 183))
        sorc = FakeAccount(w, "Sorc", phase="city", level=9, board=board())
        cfg = make_cfg(tasks=True, idle_city_seconds=0)
        cfg["tasks"]["per_day"] = 0                                 # Sorc ja bateu a cota
        eng = engine_for(w, cfg)
        eng.memory.set_task(__import__("otxidle_bot.engine", fromlist=["task_day"]).task_day(cfg), "Kina",
                            {"checked": True, "creature": "Orc", "hunt": "Orc Camp"})
        eng.tick()
        self.assertEqual(w.parties, {"Kina": ["Sorc"]})
        self.assertEqual((kina.state.hunt_name, sorc.state.hunt_name), ("Orc Camp", "Orc Camp"))


if __name__ == "__main__":
    unittest.main()
