import unittest

from otxidle_bot.account import build_state, parse_cap_tooltip, parse_hm, parse_party

RAW = {
    "name": "Conta Um", "level": "12", "vocation": "KNIGHT", "cap": "CAP. 36", "gold": "5,288",
    "stamina_hunt": "09:23", "stamina_train": "12:00", "hunting": True, "hunt_name": "Bone Crypt",
    "hunt_buttons": ["Ajustes da caça", "Despachar em 00:15:44", "Finalizar Hunt"], "training": False,
    "city": False, "party": "Party: 4 de 4 membros", "modals": [],
}


class ParseTest(unittest.TestCase):
    def test_numbers(self):
        self.assertEqual(parse_hm("09:31"), 571)
        self.assertEqual(parse_hm("12:00"), 720)
        self.assertIsNone(parse_hm(""))
        self.assertEqual(parse_cap_tooltip("Capacidade livre: 36 de 570 oz"), (36, 570))
        self.assertEqual(parse_cap_tooltip("Capacidade livre: 1,036 de 1,570 oz"), (1036, 1570))
        self.assertEqual(parse_party("Party: 4 de 4 membros"), 4)
        self.assertEqual(parse_party(""), 0)

    def test_hunting_state(self):
        st = build_state(RAW, cap_max=570)
        self.assertEqual((st.name, st.level, st.vocation, st.phase), ("Conta Um", 12, "Knight", "hunting"))
        self.assertEqual((st.cap_free, st.gold, st.stamina_hunt, st.party_size), (36, 5288, 563, 4))
        self.assertAlmostEqual(st.cap_pct, 100 * 534 / 570)

    def test_phases(self):
        leaving = dict(RAW, hunt_buttons=["Despachar", "Saindo em 3s…"])
        self.assertEqual(build_state(leaving).phase, "leaving")
        self.assertEqual(build_state(dict(RAW, hunting=False, training=True)).phase, "training")
        self.assertEqual(build_state(dict(RAW, hunting=False, city=True)).phase, "city")
        self.assertEqual(build_state(dict(RAW, hunting=False)).phase, "unknown")
        self.assertIsNone(build_state(RAW).cap_pct)          # sem o maximo (tooltip) nao ha %

    def test_offline(self):
        raw = {"name": "Conta Um", "offline": True, "modals": []}
        self.assertEqual(build_state(raw).phase, "offline")

    def test_invite(self):
        raw = dict(RAW, hunting=False, city=True,
                   modals=["CONVITE DE PARTY\n\nConta Lider Level 12 convidou você para uma party\n\n58s restantes\nRECUSAR\nENTRAR"])
        self.assertEqual(build_state(raw).invite_from, "Conta Lider")
        self.assertEqual(build_state(RAW).invite_from, "")


if __name__ == "__main__":
    unittest.main()
