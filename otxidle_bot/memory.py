"""Memoria pequena em disco (memory.json): ultima caça de cada grupo, tasks do dia, quem esta treinando e as contas vistas,
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

    # treino por conta (stamina de caça acabou): sai do plano ate recuperar
    def training(self, name):
        return name.casefold() in (self.data.get("training") or [])

    def set_training(self, name, value):
        current = set(self.data.get("training") or [])
        new = (current | {name.casefold()}) if value else (current - {name.casefold()})
        if new != current:
            self.data["training"] = sorted(new)
            self._save()

    # tasks do dia: {'day': 'AAAA-MM-DD', 'accounts': {nome: {done, creature, hunt, stuck, checked}}}
    def tasks_today(self, day):
        tasks = self.data.get("tasks") or {}
        return dict(tasks.get("accounts") or {}) if tasks.get("day") == day else {}

    def set_task(self, day, name, info):
        tasks = self.data.get("tasks") or {}
        if tasks.get("day") != day:
            tasks = {"day": day, "accounts": {}}
        tasks["accounts"][name.casefold()] = info
        self.data["tasks"] = tasks
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
