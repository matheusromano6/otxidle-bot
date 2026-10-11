"""python -m otxidle_bot [--status] [--config caminho]

  --status   le as contas e mostra o estado (nao faz nada no jogo)
"""
import argparse
import logging
import os
import sys
import threading
import time

from . import VERSION, config
from .engine import Engine
from .idledeck import Pool
from .memory import Memory
from .paths import app_dir

ROOT = app_dir()


def make_logger():
    os.makedirs(os.path.join(ROOT, "logs"), exist_ok=True)
    path = os.path.join(ROOT, "logs", f"otxidle_{time.strftime('%Y-%m-%d')}.log")
    logger = logging.getLogger("otxidle")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("[%(asctime)s] %(message)s", "%H:%M:%S")
    for handler in (logging.FileHandler(path, encoding="utf-8"), logging.StreamHandler(sys.stdout)):
        handler.setFormatter(fmt)
        logger.addHandler(handler)
    return logger.info


def fmt_min(minutes):
    return "?" if minutes is None else f"{minutes // 60}:{minutes % 60:02d}h"


def show_status(pool, cfg):
    accounts = pool.refresh()
    engine = Engine(accounts, cfg, print, memory=Memory(os.path.join(ROOT, "memory.json")))
    states = engine.read_all()
    for st in states.values():
        cap = "?" if st.cap_pct is None else f"{st.cap_pct:.0f}% ({st.cap_max - st.cap_free}/{st.cap_max} oz)"
        print(f"- {st.name} ({st.vocation} {st.level}) | {st.phase} {st.hunt_name} | cap {cap} | stamina caça "
              f"{fmt_min(st.stamina_hunt)} treino {fmt_min(st.stamina_train)} | party {st.party_size or '-'}")
    if engine.tasks_on:
        from . import tasks as T
        engine.hunts = T.load_hunts()
    for group in engine._groups([a for a in accounts if a.name in states]):
        print(f"  grupo: {group.label} ({'party' if group.is_party else 'solo'}) -> {group.hunt or '-'} {group.reason}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="otxidle_bot")
    ap.add_argument("--config", default=os.path.join(ROOT, "config.json"))
    ap.add_argument("--status", action="store_true", help="so' le e mostra o estado das contas")
    args = ap.parse_args(argv)
    cfg = config.load(args.config)
    log = print if args.status else make_logger()
    pool = Pool(cfg["cdp_url"], log)
    pool.open(launch=not args.status)
    try:
        if args.status:
            show_status(pool, cfg)
            return 0
        log(f"otxidle_bot {VERSION}")
        engine = Engine(pool.refresh(), cfg, log, refresh=pool.refresh, memory=Memory(os.path.join(ROOT, "memory.json")))
        stop = threading.Event()
        try:
            engine.run(stop)
        except KeyboardInterrupt:
            stop.set()
        return 0
    finally:
        pool.close()


if __name__ == "__main__":
    sys.exit(main())
