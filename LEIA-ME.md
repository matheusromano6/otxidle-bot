# OtxIdle Bot

Bot do **OtxIdle** (otxidle.com.br) que roda dentro do **IdleDeck** (Windows). Conecta pela depuração remota
(porta 9224, a mesma do bot do Huntera) e só mexe nas abas do OtxIdle.

## O que faz (v2)
- **Tasks diárias:** cada conta faz 2 tasks por dia (configurável) na dificuldade escolhida (padrão Adepto): entrega,
  rerola e escolhe a carta sozinha (só cartas com caça possível no level; prefere a que cai na mesma caça de outra conta,
  depois a de mais XP por abate). Contas com task na mesma caça caçam juntas em party.
- **Quem termina ajuda:** a conta que bateu a cota entra na party de quem ainda está em task (se o level permitir);
  quando TODAS terminam, a party configurada vai pra **caça da party** até o dia virar (0h).

- **Capacidade:** quando qualquer conta do grupo passa do limite (padrão 85%), o líder sai da caça (todos voltam),
  cada conta vende tudo na venda rápida e o líder volta pra mesma caça.
- **Party:** escolha o líder, quem pode ser chamado e a caça da party (aba Party). Na cidade o líder convida pelo
  nome e cada membro aceita sozinho (não precisa ser amigo). Os levels precisam estar dentro de 2/3 do líder.
- **Stamina:** com a stamina de caça acabando, a conta vende e treina (Knight = Axe, Paladin = Distance,
  Druid/Sorcerer = Magic, ou o que você escolher); volta a caçar quando recupera (padrão 10h).
- **Cidade parada:** se uma conta fica na cidade sem o bot ter levado, ele espera 60s e assume.

O bot vende **tudo** do inventário: guarde no POUCH o que não pode ser vendido.

## Uso
1. Baixe `OtxIdleBot-windows.zip` na última release e rode `OtxIdleBot.exe`.
2. Abra as contas do OtxIdle no IdleDeck (se ele não estiver com a porta, o bot abre/pede pra reabrir).
3. Configure as abas Regras / Tasks / Party / Treino e clique em **Iniciar**. **Atualizar** baixa a versão nova.

Desenvolvimento: `pip install -r requirements.txt`, `python -m otxidle_bot --status` (só lê),
testes `python -m unittest discover -s tests`, build `build.bat`.
