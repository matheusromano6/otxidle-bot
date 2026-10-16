"""Configuracao do bot (config.json ao lado do .exe). O que nao estiver no arquivo usa o padrao daqui;
arquivo novo e' criado com os padroes."""
import copy
import json
import os

# cards da aba TRAINING do jogo (confirmado ao vivo; o 'Boneco de Treino' fica de fora)
ALL_SKILLS = ["Magic", "Fist", "Club", "Sword", "Axe", "Distance"]

DEFAULTS = {
    # onde o IdleDeck esta com a depuracao remota ligada (a mesma porta do bot do Huntera)
    "cdp_url": "http://127.0.0.1:9224",
    "poll_seconds": 3,
    # sai da caça pra vender quando QUALQUER conta do grupo chegar nisso (% da capacidade usada).
    # Em party o loot vai todo pra mochila do LIDER, entao na pratica e' a capacidade dele.
    "capacity_pct": 85,
    # stamina de CAÇA: quando QUALQUER conta chegar em 'stamina_minutes' o grupo vai pra cidade, vende e treina
    # (o treino usa a stamina de TREINO, separada); volta a caçar quando TODAS chegarem em 'resume_stamina_minutes'
    "training": {
        "enabled": True,
        "stamina_minutes": 15,
        "resume_stamina_minutes": 30,      # volta a caçar com isso (folga acima de stamina_minutes evita ir e voltar)
        "by_name": {},                    # nome (minusculas) -> card do treino (Magic/Fist/Club/Sword/Axe/Distance)
        "use_exercise": True,             # liga a arma de exercicio (recompensa diaria) quando a conta tem uma
        "skills": {"knight": "Axe", "paladin": "Distance", "druid": "Magic", "sorcerer": "Magic"},
    },
    # party: o lider convida os membros pela lista de AMIGOS (na cidade); cada membro aceita o convite.
    # O lider escolhe a caça e todos entram juntos; o lider saindo traz todos (a party continua).
    "party": {
        "enabled": False,
        "leader": "",                     # nome (minusculas)
        "members": [],                    # nomes (minusculas)
        "hunt": "",                       # caça da party de grupo (fase de party das tasks); vazio = caçada padrao
        # modo de cada conta (minusculas): "party" | "solo" (caça em tasks.solo_hunts) | "train" (so' treinar).
        # Sem modo: lider/membros = party, o resto = solo.
        "modes": {},
    },
    # tasks diarias (v2): cada conta faz 'per_day' tasks na dificuldade escolhida; contas com task na mesma caça caçam
    # juntas; quem termina ajuda quem falta (helpers); quando TODAS terminam, vai a party configurada pra party.hunt
    "tasks": {
        "enabled": True,
        # "xp" = LEVEL primeiro: party de 4 na caça mais forte que aguenta, tasks/Paw so' de carona (sem reroll);
        # "tasks" = a party vai pra caça que atende mais tasks (Paw and Fur primeiro)
        "priority": "xp",
        "per_day": 0,                     # 0 = sem cota (com party: as tasks seguem a caça da party)
        "difficulty": "Adepto",
        "helpers": True,
        "min_xp_per_kill": 0,             # ignora cartas que pagam menos XP por abate (ex.: ratos)
        "max_rerolls": 2,                 # rerolls seguidos procurando carta boa/que junte (cada um gasta 1 token)
        # caça da task: sozinho so' com level recomendado <= level; junto com outra conta na mesma caça ate +5
        "group_level_over": 5,
        "reset_hour": 0,                  # hora em que o dia das tasks vira
        "solo_hunts": {},                 # nome (minusculas) -> caça solo; vazio = a melhor pro level (hunts.json)
    },
    # pra onde o grupo vai quando o bot nao sabe a ultima caça (memory.json)
    "default_hunt": "",
    # conta parada na cidade por mais disso (sem o bot ter levado) -> o bot assume (vende e volta a caçar)
    "idle_city_seconds": 60,
    # membro que nao entrou na party (ex.: level fora dos 2/3 do lider) fica de fora por esse tempo
    "party_skip_seconds": 1800,
    "cooldown_fail_seconds": 300,
}


def skill_for(training_cfg, name, vocation):
    """Card de treino da conta: escolha por nome, senao o padrao da vocacao ('Elite Knight' -> knight)."""
    chosen = (training_cfg.get("by_name") or {}).get((name or "").casefold())
    if chosen:
        return chosen
    v = (vocation or "").casefold()
    for key, skill in training_cfg["skills"].items():
        if key in v:
            return skill
    return None


def account_mode(cfg, name):
    """'party' / 'solo' / 'train' da conta (escolhido na aba Party)."""
    key = (name or "").casefold()
    party = cfg.get("party") or {}
    mode = (party.get("modes") or {}).get(key)
    if mode:
        return mode
    if key == (party.get("leader") or "").casefold() or key in [m.casefold() for m in party.get("members") or []]:
        return "party"
    return "solo"


def _merge(base, extra):
    out = copy.deepcopy(base)
    for key, value in (extra or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load(path):
    data = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as file:
            data = json.load(file)
    else:
        save(path, DEFAULTS)
    return _merge(DEFAULTS, data)


def save(path, config):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(config, file, ensure_ascii=False, indent=2)
