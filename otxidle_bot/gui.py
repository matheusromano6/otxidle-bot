"""Interface do bot do OtxIdle (CustomTkinter): contas, regras, party, treino e log.
Fechar (X) pergunta se fecha de vez ou guarda na bandeja; minimizar vai pra bandeja (Windows)."""
import datetime
import importlib
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk

import customtkinter as ctk

from . import VERSION, config, tasks, updater
from .credentials import Credentials
from .memory import Memory
from .paths import app_dir, resource_dir
from .runner import Runner

ROOT = app_dir()
CONFIG_PATH = os.path.join(ROOT, "config.json")
MEMORY_PATH = os.path.join(ROOT, "memory.json")
DEFAULT_CHOICE = "Padrão da vocação"
BG, PANEL, PANEL_ALT, BORDER = "#101418", "#161c22", "#1d252d", "#2b3640"
TEXT, MUTED, ACCENT, ACCENT_HOVER, DANGER, WARN = "#e6edf3", "#8b98a5", "#ff8c1a", "#e67a0f", "#f85149", "#d29922"
PHASES = {"hunting": "caçando", "city": "cidade", "training": "treinando", "leaving": "saindo", "unknown": "?"}
MAX_LOG_LINES = 500


def fmt_min(minutes):
    return "?" if minutes is None else f"{minutes // 60}:{minutes % 60:02d}h"


def outside_two_thirds(level_a, level_b):
    """Regra da party do jogo: os levels precisam estar dentro de 2/3 um do outro."""
    low, high = sorted((level_a or 0, level_b or 0))
    return bool(low and high and low * 3 < high * 2)


class App:
    def __init__(self, root, runner_factory=Runner):
        self.root = root
        root.title(f"OTXIDLE BOT  v{VERSION}")
        root.geometry("920x680")
        root.configure(fg_color=BG)
        icon = os.path.join(resource_dir(), "icon.ico")
        if os.path.exists(icon):
            try:
                root.iconbitmap(icon)
            except Exception:
                pass
        self.cfg = config.load(CONFIG_PATH)
        self.log_queue = queue.Queue()
        self.runner = runner_factory(self.cfg, self.log)
        self.tray_icon = None
        self.tray_queue = queue.Queue()
        self.close_dialog = None
        self.updating = False
        self.update_overlay = None
        self.ui_queue = queue.Queue()
        try:
            self.hunts = tasks.load_hunts()
        except Exception:
            self.hunts = []

        self._build_header()
        self.tabs = ctk.CTkTabview(root, fg_color=PANEL, segmented_button_selected_color=ACCENT,
                                   segmented_button_selected_hover_color=ACCENT_HOVER, text_color="#1a0d00")
        self.tabs.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        for name in ("Contas", "Regras", "Tasks", "Party", "Treino", "Login", "Log"):
            self.tabs.add(name)
        self._build_accounts(self.tabs.tab("Contas"))
        self._build_rules(self.tabs.tab("Regras"))
        self._build_tasks(self.tabs.tab("Tasks"))
        self._build_party(self.tabs.tab("Party"))
        self._build_training(self.tabs.tab("Treino"))
        self._build_login(self.tabs.tab("Login"))
        self._build_log(self.tabs.tab("Log"))

        root.protocol("WM_DELETE_WINDOW", self.request_close)
        if sys.platform == "win32":
            root.bind("<Unmap>", self._on_unmap)
        root.after(100, self._poll_log)
        root.after(100, self._poll_ui)
        root.after(3000, self._startup_update_check)
        root.after(2000, self._poll_accounts)
        root.after(300, self._poll_tray)

    # ------------------------------------------------------------------ util
    def log(self, message):
        now = datetime.datetime.now()
        line = f"[{now.strftime('%H:%M:%S')}] {message}"
        self.log_queue.put(line)
        try:                      # tambem em arquivo (logs/otxidle_AAAA-MM-DD.log ao lado do .exe)
            folder = os.path.join(ROOT, "logs")
            os.makedirs(folder, exist_ok=True)
            with open(os.path.join(folder, f"otxidle_{now.strftime('%Y-%m-%d')}.log"), "a", encoding="utf-8") as file:
                file.write(line + "\n")
        except OSError:
            pass

    def save(self):
        config.save(CONFIG_PATH, self.cfg)

    def _poll_log(self):
        try:
            while True:
                line = self.log_queue.get_nowait()
                self.log_box.configure(state="normal")
                self.log_box.insert("end", line + "\n")
                count = int(self.log_box.index("end-1c").split(".")[0])
                if count > MAX_LOG_LINES:
                    self.log_box.delete("1.0", f"{count - MAX_LOG_LINES}.0")
                self.log_box.see("end")
                self.log_box.configure(state="disabled")
        except queue.Empty:
            pass
        self.root.after(150, self._poll_log)

    # ---------------------------------------------------------------- header
    def _build_header(self):
        bar = ctk.CTkFrame(self.root, fg_color=PANEL, corner_radius=8)
        bar.pack(fill="x", padx=14, pady=14)
        ctk.CTkLabel(bar, text="OTXIDLE BOT", font=("Segoe UI", 18, "bold"), text_color=TEXT).pack(side="left", padx=14, pady=10)
        self.status = ctk.CTkLabel(bar, text="● PARADO", font=("Segoe UI", 13, "bold"), text_color=MUTED)
        self.status.pack(side="left", padx=10)
        self.stop_btn = ctk.CTkButton(bar, text="Parar", width=80, command=self.stop, state="disabled",
                                      fg_color=PANEL_ALT, hover_color=BORDER, text_color=TEXT)
        self.stop_btn.pack(side="right", padx=4)
        self.start_btn = ctk.CTkButton(bar, text="Iniciar", width=90, command=self.start, fg_color=ACCENT,
                                       hover_color=ACCENT_HOVER, text_color="#1a0d00")
        self.start_btn.pack(side="right", padx=4)
        self.update_btn = ctk.CTkButton(bar, text="Atualizar", width=90, command=self.start_update, fg_color=PANEL_ALT,
                                        hover_color=BORDER, text_color=TEXT)
        self.update_btn.pack(side="right", padx=14)

    def start(self):
        self.runner.start()
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")

    def stop(self):
        self.runner.stop()
        self.stop_btn.configure(state="disabled")
        self.start_btn.configure(state="normal")
        self.status.configure(text="● PARADO", text_color=MUTED)

    def call_ui(self, fn):
        """Executa 'fn' na thread da interface (o Tk nao aceita after() de outra thread fora do mainloop)."""
        self.ui_queue.put(fn)

    def _poll_ui(self):
        try:
            while True:
                self.ui_queue.get_nowait()()
        except queue.Empty:
            pass
        self.root.after(100, self._poll_ui)

    # ------------------------------------------------------------- atualizar
    def _startup_update_check(self):
        """Ao abrir: avisa no log se ha versao nova (nao baixa nem troca nada sozinho)."""
        def work():
            info = updater.check_for_update(lambda m: None)
            if info:
                self.log(f"Nova versão disponível: v{info['version']} (você está na v{VERSION}). Clique em Atualizar.")
        threading.Thread(target=work, daemon=True).start()

    def start_update(self, confirm=True):
        """Atualizar: confere AGORA (no GitHub) se ha versao nova; se ja esta na ultima, so' avisa."""
        if self.updating:
            return
        if self.runner.running:
            self.log("Pare o bot antes de atualizar.")
            return
        self.update_btn.configure(state="disabled", text="Verificando...")

        def work():
            info = updater.check_for_update(self.log)
            self.call_ui(lambda: self._on_update_checked(info, confirm))

        threading.Thread(target=work, daemon=True).start()

    def _on_update_checked(self, info, confirm):
        self.update_btn.configure(state="normal", text="Atualizar")
        if info is None:
            self.log(f"Você já está na última versão (v{VERSION}).")
            return
        if not updater.is_frozen():
            self.log(f"Há uma versão nova (v{info['version']}), mas a atualização automática só funciona no executável (OtxIdleBot.exe).")
            return
        if confirm and not self._ask(f"Atualizar para a v{info['version']}?",
                                     "O bot vai baixar a versão nova, fechar e abrir sozinho de novo. "
                                     "Suas configurações (config.json, memory.json) ficam como estão."):
            return
        self._begin_update(info)

    def _ask(self, title, message):
        win = ctk.CTkToplevel(self.root)
        win.title(title)
        win.geometry("430x190")
        win.configure(fg_color=BG)
        win.transient(self.root)
        win.attributes("-topmost", True)
        result = {"ok": False}
        ctk.CTkLabel(win, text=message, wraplength=390, text_color=TEXT).pack(padx=20, pady=(22, 16))
        row = ctk.CTkFrame(win, fg_color="transparent")
        row.pack()

        def answer(value):
            result["ok"] = value
            win.destroy()

        ctk.CTkButton(row, text="Atualizar", command=lambda: answer(True), fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="#1a0d00").pack(side="left", padx=8)
        ctk.CTkButton(row, text="Cancelar", command=lambda: answer(False), fg_color=PANEL_ALT, hover_color=BORDER, text_color=TEXT).pack(side="left", padx=8)
        win.protocol("WM_DELETE_WINDOW", lambda: answer(False))
        win.grab_set()
        self.root.wait_window(win)
        return result["ok"]

    def _begin_update(self, info):
        """Tela de carregamento cobrindo a janela inteira (nao deixa clicar em nada ate' trocar)."""
        self.updating = True
        overlay = ctk.CTkFrame(self.root, fg_color=BG)
        overlay.place(x=0, y=0, relwidth=1, relheight=1)
        overlay.lift()
        ctk.CTkLabel(overlay, text=f"Atualizando para a v{info['version']}...", font=("Segoe UI", 18, "bold"), text_color=TEXT).place(relx=0.5, rely=0.42, anchor="center")
        self.update_status = ctk.CTkLabel(overlay, text="Baixando...", text_color=MUTED)
        self.update_status.place(relx=0.5, rely=0.5, anchor="center")
        self.update_bar = ctk.CTkProgressBar(overlay, width=360, progress_color=ACCENT)
        self.update_bar.set(0)
        self.update_bar.place(relx=0.5, rely=0.57, anchor="center")
        self.update_overlay = overlay

        def work():
            ok = updater.apply_update(info["asset_url"], self.log, lambda f: self.call_ui(lambda: self.update_bar.set(f)))
            self.call_ui(lambda: self._on_update_applied(ok))

        threading.Thread(target=work, daemon=True).start()

    def _on_update_applied(self, ok):
        if not ok:
            self.update_overlay.destroy()
            self.update_overlay = None
            self.updating = False
            self.log("Não consegui aplicar a atualização - tente de novo mais tarde ou baixe na página de releases.")
            return
        self.update_bar.set(1)
        self.update_status.configure(text="Instalando... reiniciando o bot.")
        self.root.after(1500, self.quit)       # o .bat so' troca o .exe depois que ESTE processo fechar

    # ---------------------------------------------------------------- contas
    # ---------------------------------------------------------------- contas
    def _build_accounts(self, tab):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("H.Treeview", background=PANEL_ALT, fieldbackground=PANEL_ALT, foreground=TEXT, rowheight=28, borderwidth=0)
        style.configure("H.Treeview.Heading", background=PANEL, foreground=MUTED, borderwidth=0)
        style.map("H.Treeview", background=[("selected", BORDER)])
        cols = ("conta", "voc", "fase", "caca", "cap", "stam", "treino", "task", "grupo")
        heads = ("Conta", "Vocação", "Fase", "Caça", "Cap.", "Stamina caça", "Treino", "Task", "Grupo")
        widths = (120, 100, 75, 120, 50, 85, 60, 150, 150)
        self.tree = ttk.Treeview(tab, columns=cols, show="headings", style="H.Treeview", height=8)
        for c, h, w in zip(cols, heads, widths):
            self.tree.heading(c, text=h)
            self.tree.column(c, width=w, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=10, pady=(10, 6))
        self.accounts_note = ctk.CTkLabel(
            tab, text="Abra o IdleDeck com as contas do OtxIdle e clique em Iniciar (o bot abre o IdleDeck com a porta se precisar).",
            text_color=MUTED, wraplength=840, justify="left")
        self.accounts_note.pack(anchor="w", padx=12, pady=(0, 10))

    def _poll_accounts(self):
        snap = self.runner.snapshot
        states = snap["states"]
        group_of = {n: label for label, names in snap["groups"].items() for n in names}
        self.tree.delete(*self.tree.get_children())
        for name, st in sorted(states.items()):
            cap = "?" if st.cap_pct is None else f"{st.cap_pct:.0f}%"
            label = group_of.get(name)
            names = snap["groups"].get(label, [])
            target = (snap.get("hunts") or {}).get(label) or ""
            info = (snap.get("tasks") or {}).get(name.casefold()) or {}
            if st.task:
                task = f"{st.task[0]} {st.task[1]}/{st.task[2]}"
            else:
                task = info.get("creature") or ("cota feita" if info.get("done") else "-")
            task += f" ({info.get('done', 0)} hoje)" if info else ""
            group = (f"party de {names[0]}" if len(names) > 1 else "solo") + (f" → {target}" if target else "")
            self.tree.insert("", "end", values=(name, f"{st.vocation} {st.level}", PHASES.get(st.phase, st.phase),
                                                st.hunt_name or "-", cap, fmt_min(st.stamina_hunt), fmt_min(st.stamina_train),
                                                task, group))
        if self.runner.running:
            self.status.configure(text="● RODANDO" if self.runner.connected else "● CONECTANDO",
                                  text_color=ACCENT if self.runner.connected else WARN)
        elif self.start_btn.cget("state") == "disabled":
            self.stop()
        if states:
            self._refresh_party(states)
            self._refresh_training(states)
        self.root.after(2000, self._poll_accounts)

    # ---------------------------------------------------------------- regras
    def _build_rules(self, tab):
        grid = ctk.CTkFrame(tab, fg_color="transparent")
        grid.pack(anchor="nw", padx=14, pady=14)
        self.rule_vars = {}

        def row(r, label, key, sub=None, hint=""):
            ctk.CTkLabel(grid, text=label, text_color=TEXT).grid(row=r, column=0, sticky="w", pady=4, padx=(0, 14))
            value = self.cfg[key] if sub is None else self.cfg[key][sub]
            var = tk.StringVar(value=str(value))
            ctk.CTkEntry(grid, textvariable=var, width=110, fg_color=PANEL_ALT).grid(row=r, column=1, sticky="w")
            ctk.CTkLabel(grid, text=hint, text_color=MUTED).grid(row=r, column=2, sticky="w", padx=12)
            self.rule_vars[(key, sub)] = var

        row(0, "Sair para vender com", "capacity_pct", None, "% da capacidade usada, de QUALQUER conta do grupo (ex.: 85)")
        row(1, "Treinar quando faltar", "training", "stamina_minutes", "minutos de stamina de CAÇA (de qualquer conta do grupo)")
        row(2, "Voltar a caçar com", "training", "resume_stamina_minutes", "minutos de stamina de caça em TODAS (600 = 10h)")
        row(3, "Assumir cidade parada após", "idle_city_seconds", None, "segundos (conta na cidade sem o bot ter levado)")
        row(4, "Pausa após uma falha", "cooldown_fail_seconds", None, "segundos")
        ctk.CTkLabel(grid, text="Caçada padrão", text_color=TEXT).grid(row=5, column=0, sticky="w", pady=4)
        self.default_hunt = tk.StringVar(value=self.cfg.get("default_hunt") or "")
        ctk.CTkEntry(grid, textvariable=self.default_hunt, width=200, fg_color=PANEL_ALT).grid(row=5, column=1, columnspan=2, sticky="w")
        ctk.CTkLabel(grid, text="nome exato (ex.: Troll Hills); usada quando o bot não sabe a última caça", text_color=MUTED
                     ).grid(row=6, column=1, columnspan=2, sticky="w")
        self.training_var = tk.BooleanVar(value=self.cfg["training"]["enabled"])
        ctk.CTkCheckBox(grid, text="Mandar o grupo treinar quando a stamina de caça acabar", variable=self.training_var,
                        fg_color=ACCENT, text_color=TEXT).grid(row=7, column=0, columnspan=3, sticky="w", pady=8)
        ctk.CTkButton(grid, text="Salvar regras", command=self._save_rules, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      text_color="#1a0d00").grid(row=8, column=0, sticky="w", pady=10)
        self.rules_msg = ctk.CTkLabel(grid, text="", text_color=MUTED)
        self.rules_msg.grid(row=8, column=1, columnspan=2, sticky="w")
        ctk.CTkLabel(tab, text="Na venda o bot usa 'SELECIONAR TUDO' da venda rápida: vende tudo do inventário. "
                               "Itens no POUCH ficam protegidos - guarde lá o que não pode ser vendido.",
                     text_color=MUTED, wraplength=840, justify="left").pack(anchor="w", padx=14)

    def _save_rules(self):
        try:
            new = {}
            for (key, sub), var in self.rule_vars.items():
                number = float(var.get().replace(",", "."))
                if number < 0 or (key == "capacity_pct" and not 1 <= number <= 100):
                    raise ValueError(key)
                new[(key, sub)] = int(number) if number == int(number) else number
        except ValueError:
            self.rules_msg.configure(text="Valor inválido (capacidade entre 1 e 100; o resto, números positivos).", text_color=DANGER)
            return
        for (key, sub), value in new.items():
            if sub is None:
                self.cfg[key] = value
            else:
                self.cfg[key][sub] = value
        self.cfg["training"]["enabled"] = bool(self.training_var.get())
        self.cfg["default_hunt"] = self.default_hunt.get().strip()
        self.save()
        self.rules_msg.configure(text="Salvo.", text_color=ACCENT)

    # ----------------------------------------------------------------- party
    def _known_accounts(self, states):
        """{minusculas: {'name', 'vocation', 'level'}}: contas ja vistas (memoria) + as ao vivo."""
        out = Memory(MEMORY_PATH).seen()
        for name, st in states.items():
            out[name.casefold()] = {"name": name, "vocation": st.vocation, "level": st.level}
        party = self.cfg["party"]
        for name in [party.get("leader")] + list(party.get("members") or []):
            if name:
                out.setdefault(name.casefold(), {"name": name, "vocation": "", "level": 0})
        return out

    def _build_party(self, tab):
        party = self.cfg["party"]
        self.party_enabled = tk.BooleanVar(value=bool(party.get("enabled")))
        ctk.CTkCheckBox(tab, text="Caçar em party (o líder monta a party e escolhe a caça)", variable=self.party_enabled,
                        command=self._party_changed, fg_color=ACCENT, text_color=TEXT).pack(anchor="w", padx=14, pady=(14, 4))
        ctk.CTkLabel(tab, text="Na cidade o líder convida os membros pelo nome e cada membro aceita sozinho (não precisa ser "
                               "amigo). Os levels precisam estar dentro de 2/3 do líder (regra do jogo). O loot vai pra mochila "
                               "do líder; quando ele sai, todos voltam pra cidade e vendem. Com as tasks ligadas, esta party "
                               "só se forma quando todas as contas terminam as tasks do dia.",
                     text_color=MUTED, wraplength=840, justify="left").pack(anchor="w", padx=14)
        row = ctk.CTkFrame(tab, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=10)
        ctk.CTkLabel(row, text="★ Líder:", text_color=TEXT).pack(side="left")
        self.party_leader = tk.StringVar(value="")
        self.party_leader_menu = ctk.CTkOptionMenu(row, values=["-"], variable=self.party_leader, width=220, fg_color=PANEL_ALT,
                                                   command=lambda _v: self._party_changed(rebuild=True))
        self.party_leader_menu.pack(side="left", padx=8)
        ctk.CTkLabel(row, text="Caça da party:", text_color=TEXT).pack(side="left", padx=(20, 0))
        self.party_hunt = tk.StringVar(value="")
        self.party_hunt_labels = {}           # texto da lista -> nome da caça ("" = automatica)
        self.party_hunt_menu = ctk.CTkOptionMenu(row, values=["-"], variable=self.party_hunt, width=330, fg_color=PANEL_ALT,
                                                 dynamic_resizing=False, command=lambda _v: self._party_changed())
        self.party_hunt_menu.pack(side="left", padx=8)
        ctk.CTkLabel(tab, text="A lista mostra só as caças que o grupo marcado pode fazer: recomendado até 5 levels acima do "
                               "líder e level mínimo que todos alcançam. 'Automática' escolhe a mais forte delas e acompanha "
                               "os levels conforme sobem.", text_color=MUTED, wraplength=840, justify="left"
                     ).pack(anchor="w", padx=14, pady=(0, 8))
        ctk.CTkLabel(tab, text="Quem pode ser chamado pra party:", text_color=TEXT).pack(anchor="w", padx=14)
        self.party_members_frame = ctk.CTkFrame(tab, fg_color=PANEL_ALT)
        self.party_members_frame.pack(fill="x", padx=14, pady=(6, 10))
        self.party_member_vars = {}
        self.party_signature = None
        self.party_accounts = {}
        self._refresh_party({})

    def _refresh_party(self, states, force=False):
        accounts = self._known_accounts(states)
        party = self.cfg["party"]
        leader = (party.get("leader") or "").casefold()
        signature = (tuple(sorted((k, v.get("level")) for k, v in accounts.items())), leader)
        if signature == self.party_signature and not force:
            return
        self.party_signature = signature
        self.party_accounts = accounts
        names = [accounts[k]["name"] for k in sorted(accounts)] or ["-"]
        self.party_leader_menu.configure(values=names)
        self.party_leader.set(accounts[leader]["name"] if leader in accounts else "-")
        for child in self.party_members_frame.winfo_children():
            child.destroy()
        self.party_member_vars = {}
        if not accounts:
            ctk.CTkLabel(self.party_members_frame, text="Nenhuma conta vista ainda. Inicie o bot com as contas abertas.",
                         text_color=MUTED).pack(anchor="w", padx=10, pady=8)
            self._refresh_party_hunts()
            return
        members = {m.casefold() for m in party.get("members") or []}
        lead_level = (accounts.get(leader) or {}).get("level") or 0
        for key in sorted(accounts):
            if key == leader:
                continue
            info = accounts[key]
            var = tk.BooleanVar(value=key in members)
            warn = outside_two_thirds(lead_level, info.get("level"))
            note = f"{info.get('vocation') or ''} {info.get('level') or ''}".strip()
            line = ctk.CTkFrame(self.party_members_frame, fg_color="transparent")
            line.pack(fill="x", padx=10, pady=2)
            ctk.CTkCheckBox(line, text=info["name"], variable=var, command=self._party_changed, fg_color=ACCENT,
                            text_color=TEXT, width=220).pack(side="left")
            ctk.CTkLabel(line, text=note + ("   ⚠ level fora dos 2/3 do líder (caça solo)" if warn else ""),
                         text_color=WARN if warn else MUTED).pack(side="left", padx=8)
            self.party_member_vars[key] = var
        self._refresh_party_hunts()

    def _refresh_party_hunts(self):
        """Lista da 'Caça da party': Automática (com a escolha de agora) + caças que o grupo marcado pode fazer."""
        party = self.cfg["party"]
        accounts = self.party_accounts
        leader = (party.get("leader") or "").casefold()
        lead_level = (accounts.get(leader) or {}).get("level") or 0
        chosen = party.get("hunt") or ""
        if not self.hunts or not lead_level:
            self.party_hunt_labels = {"Automática (escolha o líder)": ""}
        else:
            levels = [lead_level] + [(accounts.get(m) or {}).get("level") or 0 for m in party.get("members") or []]
            levels = [lv for lv in levels if lv and not outside_two_thirds(lead_level, lv)]
            over = self.cfg["tasks"].get("group_level_over", 5)
            low = min(levels)
            options = sorted([h for h in self.hunts if (h.get("rec_level") or 1) <= lead_level + over
                              and (h.get("min_level") or 1) <= low],
                             key=lambda h: (-(h.get("rec_level") or 1), h["name"]))
            auto = tasks.party_hunt(self.hunts, lead_level, levels, over)
            self.party_hunt_labels = {f"Automática → {auto or 'nenhuma'}": ""}
            for h in options:
                self.party_hunt_labels[f"{h['name']}  (rec {h.get('rec_level')} · mín {h.get('min_level')})"] = h["name"]
            if chosen and chosen not in self.party_hunt_labels.values():
                self.party_hunt_labels[f"{chosen}  ⚠ fora do level do grupo"] = chosen
        self.party_hunt_menu.configure(values=list(self.party_hunt_labels))
        self.party_hunt.set(next(label for label, name in self.party_hunt_labels.items() if name == chosen)
                            if chosen in self.party_hunt_labels.values() else next(iter(self.party_hunt_labels)))

    def _party_changed(self, rebuild=False):
        party = self.cfg["party"]
        leader = next((k for k, v in self.party_accounts.items() if v["name"] == self.party_leader.get()), "")
        party["enabled"] = bool(self.party_enabled.get())
        party["leader"] = leader
        party["members"] = sorted(k for k, var in self.party_member_vars.items() if var.get() and k != leader)
        party["hunt"] = self.party_hunt_labels.get(self.party_hunt.get(), party.get("hunt") or "")
        self.save()
        if rebuild:
            self._refresh_party(self.runner.snapshot["states"], force=True)
        else:
            self._refresh_party_hunts()
        self.log(f"party: {'ligada' if party['enabled'] else 'desligada'} - líder {leader or '-'}, "
                 f"membros {', '.join(party['members']) or '-'}")

    # ----------------------------------------------------------------- tasks
    def _build_tasks(self, tab):
        tasks = self.cfg["tasks"]
        self.tasks_enabled = tk.BooleanVar(value=bool(tasks.get("enabled")))
        ctk.CTkCheckBox(tab, text="Fazer as tasks diárias antes da party", variable=self.tasks_enabled, fg_color=ACCENT,
                        text_color=TEXT).pack(anchor="w", padx=14, pady=(14, 4))
        ctk.CTkLabel(tab, text="Cada conta faz suas tasks (contas com task na mesma caça caçam juntas em party). Quem termina "
                               "ajuda quem falta, se o level permitir; senão caça solo. Quando todas batem a cota, a party "
                               "configurada vai pra caça da party até o dia virar.",
                     text_color=MUTED, wraplength=840, justify="left").pack(anchor="w", padx=14)
        grid = ctk.CTkFrame(tab, fg_color="transparent")
        grid.pack(anchor="nw", padx=14, pady=10)
        self.task_vars = {}
        rows = (("Tasks por dia (cada conta)", "per_day", "depois disso a conta ajuda as outras / vai pra party"),
                ("XP mínimo por abate", "min_xp_per_kill", "cartas abaixo disso são ignoradas (ex.: 5 evita ratos)"),
                ("Rerolls seguidos", "max_rerolls", "procurando carta boa (cada um gasta 1 token)"),
                ("Hora que o dia vira", "reset_hour", "0 = meia-noite"))
        for r, (label, key, hint) in enumerate(rows):
            ctk.CTkLabel(grid, text=label, text_color=TEXT).grid(row=r, column=0, sticky="w", pady=4, padx=(0, 14))
            var = tk.StringVar(value=str(tasks.get(key, 0)))
            ctk.CTkEntry(grid, textvariable=var, width=90, fg_color=PANEL_ALT).grid(row=r, column=1, sticky="w")
            ctk.CTkLabel(grid, text=hint, text_color=MUTED).grid(row=r, column=2, sticky="w", padx=12)
            self.task_vars[key] = var
        ctk.CTkLabel(grid, text="Dificuldade", text_color=TEXT).grid(row=4, column=0, sticky="w", pady=4)
        self.task_difficulty = tk.StringVar(value=tasks.get("difficulty") or "Adepto")
        ctk.CTkOptionMenu(grid, values=["Iniciante", "Adepto", "Experiente", "Mestre"], variable=self.task_difficulty,
                          width=140, fg_color=PANEL_ALT).grid(row=4, column=1, sticky="w")
        self.task_helpers = tk.BooleanVar(value=bool(tasks.get("helpers", True)))
        ctk.CTkCheckBox(grid, text="Quem terminou ajuda quem ainda está em task", variable=self.task_helpers,
                        fg_color=ACCENT, text_color=TEXT).grid(row=5, column=0, columnspan=3, sticky="w", pady=8)
        ctk.CTkButton(grid, text="Salvar tasks", command=self._save_tasks, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      text_color="#1a0d00").grid(row=6, column=0, sticky="w", pady=6)
        self.tasks_msg = ctk.CTkLabel(grid, text="", text_color=MUTED)
        self.tasks_msg.grid(row=6, column=1, columnspan=2, sticky="w")

    def _save_tasks(self):
        tasks = self.cfg["tasks"]
        try:
            values = {k: float(v.get().replace(",", ".")) for k, v in self.task_vars.items()}
            if any(v < 0 for v in values.values()) or values["reset_hour"] > 23:
                raise ValueError
        except ValueError:
            self.tasks_msg.configure(text="Valor inválido (números positivos; hora de 0 a 23).", text_color=DANGER)
            return
        for key, value in values.items():
            tasks[key] = int(value) if value == int(value) else value
        tasks["enabled"] = bool(self.tasks_enabled.get())
        tasks["difficulty"] = self.task_difficulty.get()
        tasks["helpers"] = bool(self.task_helpers.get())
        self.save()
        self.tasks_msg.configure(text="Salvo.", text_color=ACCENT)

    # ----------------------------------------------------------------- treino
    def _build_training(self, tab):
        ctk.CTkLabel(tab, text="O que cada personagem treina quando a stamina de caça acabar (o treino usa a stamina de TREINO, "
                               "separada). Padrão: Knight = Axe, Paladin = Distance, Druid/Sorcerer = Magic.",
                     text_color=MUTED, wraplength=840, justify="left").pack(anchor="w", padx=14, pady=(14, 8))
        self.training_frame = ctk.CTkFrame(tab, fg_color=PANEL_ALT)
        self.training_frame.pack(fill="x", padx=14)
        self.training_signature = None
        self._refresh_training({})

    def _refresh_training(self, states):
        accounts = self._known_accounts(states)
        signature = tuple(sorted(accounts))
        if signature == self.training_signature:
            return
        self.training_signature = signature
        for child in self.training_frame.winfo_children():
            child.destroy()
        if not accounts:
            ctk.CTkLabel(self.training_frame, text="Nenhuma conta vista ainda.", text_color=MUTED).pack(anchor="w", padx=10, pady=8)
            return
        chosen = self.cfg["training"].get("by_name") or {}
        for key in sorted(accounts):
            info = accounts[key]
            line = ctk.CTkFrame(self.training_frame, fg_color="transparent")
            line.pack(fill="x", padx=10, pady=3)
            ctk.CTkLabel(line, text=f"{info['name']} ({info.get('vocation') or '?'})", text_color=TEXT, width=260,
                         anchor="w").pack(side="left")
            var = tk.StringVar(value=chosen.get(key) or DEFAULT_CHOICE)
            ctk.CTkOptionMenu(line, values=[DEFAULT_CHOICE] + config.ALL_SKILLS, variable=var, width=180, fg_color=PANEL,
                              command=lambda value, k=key: self._training_changed(k, value)).pack(side="left", padx=8)

    def _training_changed(self, key, value):
        by_name = self.cfg["training"].setdefault("by_name", {})
        if value == DEFAULT_CHOICE:
            by_name.pop(key, None)
        else:
            by_name[key] = value
        self.save()
        self.log(f"treino de {key}: {value}")

    # ----------------------------------------------------------------- login
    def _build_login(self, tab):
        self.credentials = Credentials(os.path.join(ROOT, "credentials.json"))
        ctk.CTkLabel(tab, text="Logins do OtxIdle pra o bot entrar sozinho quando o jogo deslogar (server save às 00h). "
                               "Cadastre um login por conta. A senha fica criptografada pelo Windows neste PC "
                               "(credentials.json só abre no seu usuário) e nunca aparece no log.",
                     text_color=MUTED, wraplength=840, justify="left").pack(anchor="w", padx=14, pady=(14, 8))
        form = ctk.CTkFrame(tab, fg_color="transparent")
        form.pack(anchor="w", padx=14, pady=4)
        ctk.CTkLabel(form, text="Usuário", text_color=TEXT).grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.login_user = tk.StringVar()
        ctk.CTkEntry(form, textvariable=self.login_user, width=200, fg_color=PANEL_ALT).grid(row=0, column=1, padx=(0, 16))
        ctk.CTkLabel(form, text="Senha", text_color=TEXT).grid(row=0, column=2, sticky="w", padx=(0, 8))
        self.login_pass = tk.StringVar()
        ctk.CTkEntry(form, textvariable=self.login_pass, width=200, show="•", fg_color=PANEL_ALT).grid(row=0, column=3, padx=(0, 16))
        ctk.CTkButton(form, text="Salvar login", command=self._save_login, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      text_color="#1a0d00").grid(row=0, column=4)
        self.login_msg = ctk.CTkLabel(tab, text="", text_color=MUTED)
        self.login_msg.pack(anchor="w", padx=14)
        self.login_list = ctk.CTkFrame(tab, fg_color=PANEL_ALT)
        self.login_list.pack(fill="x", padx=14, pady=8)
        self._refresh_logins()

    def _refresh_logins(self):
        for child in self.login_list.winfo_children():
            child.destroy()
        names = self.credentials.usernames()
        if not names:
            ctk.CTkLabel(self.login_list, text="Nenhum login salvo.", text_color=MUTED).pack(anchor="w", padx=10, pady=8)
            return
        for name in names:
            line = ctk.CTkFrame(self.login_list, fg_color="transparent")
            line.pack(fill="x", padx=10, pady=3)
            ctk.CTkLabel(line, text=f"{name}   ••••••", text_color=TEXT, width=300, anchor="w").pack(side="left")
            ctk.CTkButton(line, text="Remover", width=80, fg_color=PANEL, hover_color=BORDER, text_color=TEXT,
                          command=lambda n=name: self._remove_login(n)).pack(side="left")

    def _save_login(self):
        user, password = self.login_user.get().strip(), self.login_pass.get()
        if not user or len(password) < 6:
            self.login_msg.configure(text="Preencha o usuário e a senha (mínimo 6 caracteres).", text_color=DANGER)
            return
        try:
            self.credentials.save(user, password)
        except Exception as error:
            self.login_msg.configure(text=f"Não consegui salvar: {error}", text_color=DANGER)
            return
        self.login_user.set("")
        self.login_pass.set("")
        self.login_msg.configure(text=f"Login {user} salvo.", text_color=ACCENT)
        self.log(f"login salvo: {user}")
        self._refresh_logins()

    def _remove_login(self, name):
        self.credentials.remove(name)
        self.log(f"login removido: {name}")
        self._refresh_logins()

    # ------------------------------------------------------------------- log
    def _build_log(self, tab):
        self.log_box = ctk.CTkTextbox(tab, fg_color=BG, text_color=TEXT, font=("Consolas", 11), state="disabled")
        self.log_box.pack(fill="both", expand=True, padx=8, pady=8)
        ctk.CTkButton(tab, text="Abrir pasta dos logs", command=lambda: os.startfile(os.path.join(ROOT, "logs")) if os.path.isdir(os.path.join(ROOT, "logs")) else None,
                      fg_color=PANEL_ALT, hover_color=BORDER, text_color=TEXT).pack(anchor="e", padx=8, pady=(0, 8))

    # ------------------------------------------------------- fechar / bandeja
    def request_close(self):
        if self.updating:
            return
        if sys.platform != "win32":
            self.quit()
            return
        if self.close_dialog is not None and self.close_dialog.winfo_exists():
            self.close_dialog.lift()
            return
        win = ctk.CTkToplevel(self.root)
        win.title("Fechar o bot")
        win.geometry("430x200")
        win.configure(fg_color=BG)
        win.transient(self.root)
        win.attributes("-topmost", True)
        win.resizable(False, False)
        self.close_dialog = win

        def choose(action):
            win.destroy()
            if action == "tray":
                self.hide_to_tray()
            elif action == "quit":
                self.quit()

        ctk.CTkLabel(win, text="O que deseja fazer?", text_color=TEXT, font=("Segoe UI", 13)).pack(padx=20, pady=(20, 6))
        hint = ("O bot está rodando: na bandeja ele continua; fechar de vez para tudo." if self.runner.running
                else "Na bandeja o app fica escondido; fechar de vez encerra o programa.")
        ctk.CTkLabel(win, text=hint, text_color=MUTED, wraplength=390).pack(padx=20, pady=(0, 16))
        row = ctk.CTkFrame(win, fg_color="transparent")
        row.pack()
        ctk.CTkButton(row, text="Guardar na bandeja", command=lambda: choose("tray"), fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="#1a0d00").pack(side="left", padx=6)
        ctk.CTkButton(row, text="Fechar de vez", command=lambda: choose("quit"), fg_color=PANEL_ALT, hover_color=BORDER, text_color=TEXT).pack(side="left", padx=6)
        ctk.CTkButton(row, text="Cancelar", command=lambda: choose("cancel"), fg_color="transparent", hover_color=BORDER, text_color=MUTED).pack(side="left", padx=6)
        win.protocol("WM_DELETE_WINDOW", lambda: choose("cancel"))

    def _on_unmap(self, event):
        if event.widget is not self.root:
            return
        try:
            if self.root.state() == "iconic":
                self.root.after(50, self.hide_to_tray)
        except tk.TclError:
            pass

    def hide_to_tray(self):
        if sys.platform != "win32" or self.tray_icon is not None:
            return
        try:
            pystray = importlib.import_module("pystray")
            image_module = importlib.import_module("PIL.Image")
            icon_path = os.path.join(resource_dir(), "icon.ico")
            image = image_module.open(icon_path) if os.path.exists(icon_path) else image_module.new("RGB", (64, 64), ACCENT)
            menu = pystray.Menu(
                pystray.MenuItem("Abrir", lambda icon, item: self.tray_queue.put("open"), default=True),
                pystray.MenuItem("Fechar de vez", lambda icon, item: self.tray_queue.put("quit")))
            self.tray_icon = pystray.Icon("OtxIdleBot", image, "OTXIDLE BOT", menu)
            self.tray_icon.run_detached()
        except Exception as error:
            self.tray_icon = None
            self.log(f"Bandeja indisponivel ({error}) - o app fica so minimizado.")
            return
        self.root.withdraw()

    def _stop_tray(self):
        icon, self.tray_icon = self.tray_icon, None
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass

    def show_from_tray(self):
        self._stop_tray()
        try:
            self.root.deiconify()
            self.root.state("normal")
            self.root.lift()
            self.root.focus_force()
        except tk.TclError:
            pass

    def _poll_tray(self):
        try:
            while True:
                action = self.tray_queue.get_nowait()
                if action == "open":
                    self.show_from_tray()
                elif action == "quit":
                    self.quit()
                    return
        except queue.Empty:
            pass
        self.root.after(300, self._poll_tray)

    def quit(self):
        self.runner.stop()
        self._stop_tray()
        self.root.destroy()


def main():
    root = ctk.CTk()
    app = App(root)
    if "--iniciar" in sys.argv:          # OtxIdleBot.exe --iniciar: ja abre rodando (atalho / reinicio remoto)
        root.after(1500, app.start)
    root.mainloop()


if __name__ == "__main__":
    main()
