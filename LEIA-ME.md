# OtxIdle Bot

Bot do **OtxIdle** (otxidle.com.br) que roda dentro do **IdleDeck** (Windows). Conecta pela depuração remota
(porta 9224, a mesma do bot do Huntera) e só mexe nas abas do OtxIdle.

## O que faz (v1)
- **Capacidade:** quando qualquer conta do grupo passa do limite (padrão 85%), o líder sai da caça (todos voltam),
  cada conta vende tudo na venda rápida e o líder volta pra mesma caça.
- **Party:** escolha o líder e quem pode ser chamado (aba Party). Na cidade o líder convida pela lista de amigos e
  cada membro aceita sozinho. Os membros precisam ser amigos do líder e ter level dentro de 2/3 do líder.
- **Stamina:** com a stamina de caça acabando, o grupo vende e treina (Knight = Axe, Paladin = Distance,
  Druid/Sorcerer = Magic, ou o que você escolher); volta a caçar quando todos recuperam (padrão 10h).
- **Cidade parada:** se uma conta fica na cidade sem o bot ter levado, ele espera 60s e assume.

O bot vende **tudo** do inventário: guarde no POUCH o que não pode ser vendido.

## Uso
1. Baixe `OtxIdleBot-windows.zip` na última release e rode `OtxIdleBot.exe`.
2. Abra as contas do OtxIdle no IdleDeck (se ele não estiver com a porta, o bot abre/pede pra reabrir).
3. Configure as abas Regras / Party / Treino e clique em **Iniciar**. **Atualizar** baixa a versão nova.

Desenvolvimento: `pip install -r requirements.txt`, `python -m otxidle_bot --status` (só lê),
testes `python -m unittest discover -s tests`, build `build.bat`.
