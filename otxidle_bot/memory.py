"""Memoria pequena em disco (memory.json): ultima caça e modo (caça/treino) de cada grupo e as contas ja vistas,
pra continuar certo mesmo se o bot for fechado e aberto de novo."""
import json
import os


def key(names):
    return ",".join(sorted(n.casefold() for n in names))


class Memory:
    def __init__(self, path=None):
        self.path = path
        self.data = {}
        if path and os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as file:
                    self.data = json.load(file)
            except (OSError, ValueError):
                self.data = {}

    def group(self, names):
        return dict((self.data.get("groups") or {}).get(key(names)) or {})

    def update_group(self, names, **values):
        current = self.data.setdefault("groups", {}).setdefault(key(names), {})
        if all(current.get(k) == v for k, v in values.items()):
            return
        current.update(values)
        self._save()

    def seen(self):
        """{minusculas: {'name', 'vocation', 'level'}} das contas ja lidas (a interface usa com o bot parado)."""
        return dict(self.data.get("accounts") or {})

    def set_seen(self, name, vocation, level):
        value = {"name": name, "vocation": vocation, "level": level}
        if (self.data.get("accounts") or {}).get(name.casefold()) != value:
            self.data.setdefault("accounts", {})[name.casefold()] = value
            self._save()

    def _save(self):
        if not self.path:
            return
        with open(self.path, "w", encoding="utf-8") as file:
            json.dump(self.data, file, ensure_ascii=False, indent=2)
