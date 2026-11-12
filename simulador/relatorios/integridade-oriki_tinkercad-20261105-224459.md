# Integridade (OR-25)

- Data: 05/11/2026 22:44
- Firmware: `oriki_tinkercad` (uno), bancada a 4.0x
- Meta: 100% das alterações recusadas ou sinalizadas
- Obtido: **100% (2 de 2)** — PASSOU

| caso | esperado | obtido | ok |
|---|---|---|---|
| ORK01-000043 alterado na memória | recusado (assinatura_invalida) | assinatura_invalida | ✔ |
| ORK01-000042 apagado antes do envio | lacuna de contador no painel do fiscal | ORK01: contadores 38 a 39 ausentes; ORK01: contadores 42 a 43 ausentes | ✔ |
| ciclos íntegros | ORK01-000041 e ORK01-000044 recebidos | ORK01-000041, ORK01-000044 | ✔ |
