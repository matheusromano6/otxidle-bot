import copy
import unittest

from otxidle_bot import config
from otxidle_bot.account import State
from otxidle_bot.engine import Engine, build_groups, hunt_triggers, training_done
from otxidle_bot.memory import Memory


class FakeAccount:
    """Conta falsa: as acoes mudam o estado como o jogo faz (confirmado ao vivo)."""

    def __init__(self, name, phase="hunting", cap_free=300, cap_max=500, stamina=600, train=720, vocation="Knight",
                 level=10, hunt="Troll Hills"):
        self.name = name
        self.state = State(name=name, level=level, vocation=vocation, phase=phase, hunt_name=hunt if phase == "hunting" else "",
                           cap_free=cap_free, cap_max=cap_max, stamina_hunt=stamina, stamina_train=train)
        self.actions = []
        self.world = None              # lista de todas as contas (lider saindo traz a party)
        self.party = []                # nomes na party (so' no lider)

    def read(self):
        return self.state

    def close_modals(self):
        pass

    def finish_hunt(self):
        self.actions.append("finish")
        for acc in self._party_accounts():
            acc.state.phase, acc.state.hunt_name = "city", ""

    def _party_accounts(self):
        if not self.party:
            return [self]
        return [a for a in self.world if a.name in self.party] + [self]

    def wait_city(self, timeout=30):
        return self.state.phase == "city"

    def sell_all(self):
        self.actions.append("sell")
        self.state.cap_free = self.state.cap_max
        return 10

    def start_hunt(self, hunt):
        self.actions.append(f"hunt:{hunt}")
        for acc in self._party_accounts():
            acc.state.phase, acc.state.hunt_name = "hunting", hunt

    def start_training(self, skill):
        self.actions.append(f"train:{skill}")
        self.state.phase = "training"

    def end_training(self):
        self.actions.append("end_training")
        self.state.phase = "city"

    def open_friends(self):
        self.actions.append("friends")
        return {"members": [self.name] + self.party, "friends": [{"name": a.name} for a in self.world if a is not self]}

    def read_friends(self):
        return {"members": [self.name] + self.party}

    def invite(self, name):
        self.actions.append(f"invite:{name}")
        target = next(a for a in self.world if a.name == name)
        target.state.invite_from = self.name
        return True

    def accept_invite(self):
        self.actions.append("accept")
        leader = next(a for a in self.world if a.name == self.state.invite_from)
        leader.party.append(self.name)
        self.state.invite_from = ""


def make_cfg(**changes):
    cfg = copy.deepcopy(config.DEFAULTS)
    cfg.update(changes)
    return cfg


def engine_for(accounts, cfg):
    for acc in accounts:
        acc.world = accounts
    eng = Engine(accounts, cfg, log=lambda m: None, memory=Memory())
    return eng


class TriggerTest(unittest.TestCase):
    def test_capacity_and_stamina(self):
        cfg = make_cfg()
        full = State(name="a", cap_free=50, cap_max=500, stamina_hunt=600)
        tired = State(name="b", cap_free=400, cap_max=500, stamina_hunt=10)
        fine = State(name="c", cap_free=400, cap_max=500, stamina_hunt=600)
        self.assertEqual(hunt_triggers([fine, full], cfg)[0], "capacidade")
        self.assertEqual(hunt_triggers([fine, tired], cfg)[0], "stamina")
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
        self.assertFalse(training_done([State(stamina_hunt=600, stamina_train=300), State(stamina_hunt=100, stamina_train=300)], cfg))
        self.assertTrue(training_done([State(stamina_hunt=600, stamina_train=300), State(stamina_hunt=650, stamina_train=300)], cfg))
        self.assertTrue(training_done([State(stamina_hunt=100, stamina_train=0)], cfg))


class GroupTest(unittest.TestCase):
    def test_groups(self):
        accs = [FakeAccount("Lider"), FakeAccount("Um"), FakeAccount("Dois"), FakeAccount("Solo")]
        cfg = make_cfg(party={"enabled": True, "leader": "lider", "members": ["um", "dois", "fechado"]})
        groups = build_groups(accs, cfg)
        self.assertEqual([g.names for g in groups], [["Lider", "Um", "Dois"], ["Solo"]])
        groups = build_groups(accs, cfg, skip={"dois"})
        self.assertEqual([g.names for g in groups], [["Lider", "Um"], ["Dois"], ["Solo"]])
        cfg["party"]["enabled"] = False
        self.assertEqual(len(build_groups(accs, cfg)), 4)


class EngineTest(unittest.TestCase):
    def test_solo_capacity_cycle(self):
        acc = FakeAccount("Solo", cap_free=40)
        eng = engine_for([acc], make_cfg())
        eng.tick()
        self.assertEqual(acc.actions, ["finish", "sell", "hunt:Troll Hills"])
        self.assertEqual(acc.state.phase, "hunting")

    def test_party_capacity_cycle_keeps_party(self):
        leader, um = FakeAccount("Lider", cap_free=20), FakeAccount("Um")
        leader.party = ["Um"]
        eng = engine_for([leader, um], make_cfg(party={"enabled": True, "leader": "lider", "members": ["um"]}))
        eng.tick()
        self.assertEqual(leader.actions, ["finish", "sell", "friends", "hunt:Troll Hills"])
        self.assertEqual(um.actions, ["sell"])
        self.assertEqual(um.state.phase, "hunting")

    def test_party_formation_in_city(self):
        leader = FakeAccount("Lider", phase="city")
        um, dois = FakeAccount("Um", phase="city"), FakeAccount("Dois", phase="city")
        cfg = make_cfg(party={"enabled": True, "leader": "lider", "members": ["um", "dois"]}, idle_city_seconds=0,
                       default_hunt="Troll Hills")
        eng = engine_for([leader, um, dois], cfg)
        eng.tick()
        self.assertIn("invite:Um", leader.actions)
        self.assertIn("invite:Dois", leader.actions)
        self.assertEqual(um.actions, ["sell", "accept"])
        self.assertEqual(leader.party, ["Um", "Dois"])
        self.assertEqual(leader.actions[-1], "hunt:Troll Hills")
        self.assertEqual({a.state.phase for a in (leader, um, dois)}, {"hunting"})

    def test_city_waits_for_user_then_takes_over(self):
        acc = FakeAccount("Solo", phase="city")
        eng = engine_for([acc], make_cfg(default_hunt="Rat Cellars"))
        eng.tick()
        self.assertEqual(acc.actions, [])          # pode ser o usuario mexendo
        eng.city_since["Solo"] -= 1000
        eng.tick()
        self.assertEqual(acc.actions, ["sell", "hunt:Rat Cellars"])

    def test_stamina_goes_training_and_back(self):
        acc = FakeAccount("Solo", stamina=10, vocation="Druid")
        cfg = make_cfg()
        eng = engine_for([acc], cfg)
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

    def test_no_loop_when_floor_above_limit(self):
        acc = FakeAccount("Solo", cap_free=200, cap_max=500)       # 60%
        acc.sell_all = lambda: (acc.actions.append("sell"), setattr(acc.state, "cap_free", 260))  # fica 48% (equipamento)
        eng = engine_for([acc], make_cfg(capacity_pct=40))
        eng.tick()
        eng.tick()
        self.assertEqual(acc.actions, ["finish", "sell", "hunt:Troll Hills"])

    def test_invite_from_stranger_ignored(self):
        acc = FakeAccount("Um", phase="hunting")
        acc.state.invite_from = "Estranho"
        eng = engine_for([acc], make_cfg(party={"enabled": True, "leader": "lider", "members": ["um"]}))
        eng.tick()
        self.assertNotIn("accept", acc.actions)

    def test_member_alone_in_hunt_returns(self):
        leader, um = FakeAccount("Lider", phase="city"), FakeAccount("Um")
        eng = engine_for([leader, um], make_cfg(party={"enabled": True, "leader": "lider", "members": ["um"]}))
        eng.tick()
        self.assertEqual(um.actions, ["finish"])

    def test_skill_choice(self):
        tr = config.DEFAULTS["training"]
        self.assertEqual(config.skill_for(tr, "x", "Elite Knight"), "Axe")
        self.assertEqual(config.skill_for(dict(tr, by_name={"x": "Club"}), "X", "Knight"), "Club")


if __name__ == "__main__":
    unittest.main()
