import os
import tempfile
import unittest
from unittest import mock

from otxidle_bot.account import State


class FakeRunner:
    def __init__(self, cfg, log):
        self.cfg, self.running, self.connected = cfg, False, False
        self.snapshot = {"states": {"Lider": State(name="Lider", level=12, vocation="Knight", phase="hunting", hunt_name="Troll Hills",
                                                   cap_free=100, cap_max=500, stamina_hunt=500, stamina_train=720),
                                    "Membro": State(name="Membro", level=7, vocation="Druid", phase="hunting")},
                         "groups": {"Lider + Membro": ["Lider", "Membro"]}}

    def start(self):
        self.running = True

    def stop(self):
        self.running = False


class GuiTest(unittest.TestCase):
    def test_builds_and_shows_accounts(self):
        try:
            import customtkinter as ctk
            root = ctk.CTk()
        except Exception as error:          # sem display
            self.skipTest(str(error))
        from otxidle_bot import gui
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(gui, "CONFIG_PATH", os.path.join(tmp, "config.json")), \
                mock.patch.object(gui, "MEMORY_PATH", os.path.join(tmp, "memory.json")), \
                mock.patch.object(gui.updater, "check_for_update", lambda log: None):
            app = gui.App(root, runner_factory=FakeRunner)
            app.cfg["party"].update(enabled=True, leader="lider")
            app._poll_accounts()
            rows = [app.tree.item(i)["values"] for i in app.tree.get_children()]
            self.assertEqual(rows[0][0], "Lider")
            self.assertEqual(rows[0][4], "80%")
            self.assertIn("party de Lider", rows[0][7])
            self.assertIn("membro", app.party_member_vars)
            self.assertTrue(gui.outside_two_thirds(12, 7))
            self.assertFalse(gui.outside_two_thirds(12, 8))
            root.destroy()


if __name__ == "__main__":
    unittest.main()
