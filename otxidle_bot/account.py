"""Uma conta do OtxIdle (uma pagina otxidle.com.br no IdleDeck): read() -> State e as acoes do jogo.
Tudo que e' clicado aqui foi testado ao vivo (ver CLAUDE.md)."""
import re
import time
from dataclasses import dataclass, field

from . import selectors as S

READ_JS = r"""() => {
  const q = s => document.querySelector(s);
  const txt = s => (q(s)?.innerText || '').trim();
  const vis = e => !!(e && e.offsetParent !== null);
  const stam = sel => { const bar = q(sel); const nums = bar?.previousElementSibling?.querySelectorAll('p.ti-numeric'); return nums && nums.length ? nums[nums.length - 1].innerText.trim() : ''; };
  const hb = q('section.hb-panel');
  const hbButtons = hb ? [...hb.querySelectorAll('button')].map(b => (b.innerText || '').trim()) : [];
  const modals = [...document.querySelectorAll('.gm-modal')].filter(vis).map(m => (m.innerText || '').slice(0, 300));
  return {
    name: txt('.gs-me .name'), level: txt('.gs-me .lvl'), vocation: txt('.gs-right .voc'),
    cap: txt('.gs-goldrow .cap'), gold: txt('.gs-goldrow .gold'),
    stamina_hunt: stam('.ta-bar[aria-label="Stamina de caça restante"]'),
    stamina_train: stam('.ta-bar[aria-label="Stamina de treino restante"]'),
    hunting: vis(hb), hunt_name: (q('section.hb-panel .gs-panelhead p')?.innerText || '').trim(), hunt_buttons: hbButtons,
    training: vis(q('section.ta')), city: vis(q('button.gs-cta.gs-cta-play')),
    party: q('.gs-chip.gs-party')?.getAttribute('aria-label') || '',
    modals: modals, url: location.pathname,
  };
}"""


def parse_hm(text):
    """'09:31' (horas:minutos) -> 571 minutos; vazio -> None."""
    m = re.search(r"(\d+):(\d{2})", text or "")
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def parse_int(text):
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else None


def parse_cap_tooltip(text):
    """'Capacidade livre: 36 de 570 oz' -> (36, 570)."""
    m = re.search(r"([\d.,]+)\s+de\s+([\d.,]+)\s*oz", text or "")
    return (parse_int(m.group(1)), parse_int(m.group(2))) if m else (None, None)


def parse_party(label):
    """'Party: 4 de 4 membros' -> 4; sem party -> 0."""
    m = re.search(r"(\d+)\s+de\s+\d+", label or "")
    return int(m.group(1)) if m else 0


@dataclass
class State:
    name: str = ""
    level: int = 0
    vocation: str = ""
    phase: str = "unknown"          # hunting / leaving / city / training / unknown
    hunt_name: str = ""
    cap_free: int = None
    cap_max: int = None
    gold: int = None
    stamina_hunt: int = None        # minutos
    stamina_train: int = None
    party_size: int = 0
    invite_from: str = ""           # nome de quem convidou (modal CONVITE DE PARTY aberto)
    modals: list = field(default_factory=list)

    @property
    def cap_pct(self):
        if self.cap_free is None or not self.cap_max:
            return None
        return max(0.0, min(100.0, 100.0 * (self.cap_max - self.cap_free) / self.cap_max))


def build_state(raw, cap_max=None):
    st = State(name=raw.get("name", ""), level=parse_int(raw.get("level")) or 0,
               vocation=(raw.get("vocation") or "").title(), hunt_name=raw.get("hunt_name", ""),
               cap_free=parse_int(raw.get("cap")), cap_max=cap_max, gold=parse_int(raw.get("gold")),
               stamina_hunt=parse_hm(raw.get("stamina_hunt")), stamina_train=parse_hm(raw.get("stamina_train")),
               party_size=parse_party(raw.get("party")), modals=list(raw.get("modals") or []))
    if raw.get("hunting"):
        st.phase = "leaving" if any(b.startswith(S.LEAVING_TEXT) for b in raw.get("hunt_buttons") or []) else "hunting"
    elif raw.get("training"):
        st.phase = "training"
    elif raw.get("city"):
        st.phase = "city"
    for text in st.modals:
        if text.startswith(S.INVITE_TITLE):
            m = re.search(r"\n\s*(.+?)\s+Level\s+\d+\s+convidou", text)
            st.invite_from = m.group(1).strip() if m else "?"
    return st


class GameError(Exception):
    pass


class Account:
    CAP_MAX_EVERY = 600          # relê o maximo da capacidade (tooltip) a cada 10 min (muda ao upar)

    def __init__(self, page, log=print):
        self.page = page
        self.log = log
        self.name = ""
        self.state = State()
        self._cap_max = None
        self._cap_read_at = 0
        self._cap_level = None

    # ------------------------------------------------------------- leitura
    def read(self):
        raw = self.page.evaluate(READ_JS)
        st = build_state(raw)
        if st.cap_free is not None and (self._cap_max is None or st.level != self._cap_level
                                        or time.time() - self._cap_read_at > self.CAP_MAX_EVERY
                                        or st.cap_free > self._cap_max) and not st.modals:
            self._read_cap_max(st.level)
        st.cap_max = self._cap_max
        self.state = st
        if st.name:
            self.name = st.name
        return st

    def _read_cap_max(self, level):
        """O maximo so' existe no tooltip do CAP (hover)."""
        try:
            self.page.locator(S.CAP).first.hover(timeout=3000)
            tip = self.page.locator(S.TOOLTIP).filter(has_text="Capacidade").first
            tip.wait_for(timeout=2000)
            _, cap_max = parse_cap_tooltip(tip.inner_text())
            if cap_max:
                self._cap_max, self._cap_read_at, self._cap_level = cap_max, time.time(), level
            self.page.mouse.move(1, 1)
        except Exception:
            pass

    # --------------------------------------------------------------- util
    def _modal(self):
        return self.page.locator(S.MODAL).last

    def _click(self, locator, timeout=6000):
        """Clique robusto: se algo cobre o botao (janela do HUD), dispara o click direto."""
        try:
            locator.click(timeout=timeout)
        except Exception as error:
            if "intercepts pointer events" not in str(error):
                raise
            locator.dispatch_event("click")

    def close_modals(self):
        for _ in range(3):
            if not self.page.locator(S.MODAL).count():
                return
            self.page.keyboard.press("Escape")
            time.sleep(0.5)

    def _wait(self, check, timeout, step=0.5):
        end = time.time() + timeout
        while time.time() < end:
            if check():
                return True
            time.sleep(step)
        return False

    def _phase(self):
        return self.read().phase

    # --------------------------------------------------------------- acoes
    def finish_hunt(self):
        """Clica 'Finalizar Hunt' (sem confirmacao; sai em 5s). Em party, a LIDER leva todos."""
        if self.state.phase == "leaving":
            return
        self.close_modals()
        self._click(self.page.locator(S.HUNT_PANEL + " button", has_text=S.FINISH_TEXT).first)
        self.log(f"{self.name}: finalizando a caça")

    def wait_city(self, timeout=30):
        return self._wait(lambda: self._phase() == "city", timeout, 1)

    def sell_all(self):
        """Venda rapida: VENDER -> SELECIONAR TUDO -> VENDER -> confirmar. Retorna o ouro ganho (0 = nada a vender)."""
        self.close_modals()
        before = self.read().gold or 0
        self._click(self.page.locator(S.PILL, has_text=S.SELL_TEXT).first)
        modal = self._modal()
        modal.locator(S.SELL_ALL).wait_for(timeout=6000)
        if modal.locator(S.SELL_ITEM).count() == 0:
            self.close_modals()
            return 0
        if "SELECIONAR" in modal.locator(S.SELL_ALL).inner_text().upper():
            self._click(modal.locator(S.SELL_ALL))
            time.sleep(0.5)
        conclude = modal.locator(S.SELL_CONCLUDE)
        if conclude.is_disabled():
            self.close_modals()
            return 0
        self._click(conclude)
        confirm = self.page.locator(S.MODAL + " " + S.CONFIRM, has_text=S.SELL_TEXT).last
        confirm.wait_for(timeout=6000)
        self._click(confirm)
        self._wait(lambda: self.page.locator(S.MODAL).count() == 0, 6)
        self.close_modals()
        gained = (self.read().gold or 0) - before
        self.log(f"{self.name}: vendeu o loot (+{gained:,} de ouro)".replace(",", "."))
        return gained

    def _open_play(self, tab):
        self.close_modals()
        self._click(self.page.locator(S.PLAY))
        tab_btn = self.page.locator(S.GM_TAB, has_text=tab).first
        tab_btn.wait_for(timeout=6000)
        self._click(tab_btn)                      # a janela lembra a ultima aba: sempre clicar
        time.sleep(0.8)

    def start_hunt(self, hunt):
        """JOGAR -> HUNTS -> card da caça -> COMEÇAR A CAÇA. Em party so' a lider chama (todos entram)."""
        self._open_play("HUNTS")
        search = self.page.locator(S.HUNT_SEARCH)
        if search.count():
            search.fill(hunt)
            time.sleep(0.8)
        cards = self.page.locator(S.GM_CARD)
        card = None
        for i in range(cards.count()):
            if cards.nth(i).inner_text().split("\n")[0].strip().casefold() == hunt.casefold():
                card = cards.nth(i)
                break
        if card is None:
            self.close_modals()
            raise GameError(f"caça '{hunt}' nao encontrada")
        self._click(card)
        start = self.page.locator(S.DRAWER + " " + S.START_HUNT, has_text=S.START_HUNT_TEXT).first
        start.wait_for(timeout=6000)
        self._click(start)
        ok = self._wait(lambda: self._phase() == "hunting", 15, 1)
        self.close_modals()
        if not ok:
            raise GameError(f"nao entrou na caça '{hunt}'")
        self.log(f"{self.name}: iniciou a caça {hunt}")

    def start_training(self, skill):
        """JOGAR -> TRAINING -> card da habilidade. CLICAR NO CARD JA INICIA o treino (sem confirmacao)."""
        self._open_play("TRAINING")
        cards = self.page.locator(S.GM_CARD)
        for i in range(cards.count()):
            if cards.nth(i).inner_text().split("\n")[0].strip().casefold() == skill.casefold():
                self._click(cards.nth(i))
                ok = self._wait(lambda: self._phase() == "training", 10, 1)
                self.close_modals()
                if not ok:
                    raise GameError(f"treino de {skill} nao iniciou")
                self.log(f"{self.name}: iniciou o treino de {skill}")
                return
        self.close_modals()
        raise GameError(f"treino '{skill}' nao encontrado")

    def end_training(self):
        self._click(self.page.locator(S.TRAIN_PANEL + " button", has_text=S.END_TRAIN_TEXT).first)
        self._wait(lambda: self._phase() == "city", 10, 1)
        self.log(f"{self.name}: encerrou o treino")

    # --------------------------------------------------------------- party
    PARTY_JS = r"""() => {
      const m = [...document.querySelectorAll('.gm-modal')].pop(); if (!m) return null;
      const members = [...m.querySelectorAll('.pt-row')].map(r => { const who = r.querySelector('.pt-who') || r;
        const b = who.querySelector('b'); return ((b ? b.innerText : who.innerText.split('\n')[0]) || '').split(' · ')[0].replace(/\(você\)/, '').trim(); });
      const friends = [...m.querySelectorAll('.fr-row')].map(r => ({ name: (r.querySelector('.fr-who b')?.innerText || '').trim(),
        info: (r.querySelector('.fr-who small')?.innerText || '').trim(), place: (r.querySelector('.fr-place')?.innerText || '').trim(),
        in_town: !!r.querySelector('.fr-place.is-town') }));
      return { count: (m.querySelector('.pt-count')?.innerText || '').trim(), members, friends,
               text: (m.querySelector('.pt-section')?.innerText || '').slice(0, 300) };
    }"""

    def open_friends(self):
        self.close_modals()
        self._click(self.page.locator(S.FRIENDS_CHIP))
        self.page.locator(S.MODAL + " " + S.PARTY_SECTION).wait_for(timeout=6000)
        time.sleep(0.5)
        return self.page.evaluate(self.PARTY_JS) or {}

    def read_friends(self):
        """{'members': [...], 'friends': [{name, info, place, in_town}], ...} (abre e fecha a janela)."""
        try:
            return self.open_friends()
        finally:
            self.close_modals()

    def invite(self, name):
        """Na janela Amigos ja aberta: CONVIDAR o amigo (sem party, o 1o convite ja cria)."""
        rows = self.page.locator(S.MODAL + " " + S.FRIEND_ROW)
        for i in range(rows.count()):
            row = rows.nth(i)
            if row.locator(".fr-who b").inner_text().strip().casefold() == name.casefold():
                self._click(row.locator(S.FRIEND_INVITE, has_text="CONVIDAR"))
                self.log(f"{self.name}: convidou {name} pra party")
                return True
        self.log(f"{self.name}: {name} nao esta na lista de amigos")
        return False

    def accept_invite(self):
        self._click(self.page.locator(S.MODAL + " " + S.INVITE_ACCEPT).last)
        time.sleep(1)
        self.log(f"{self.name}: entrou na party")
