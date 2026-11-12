# Integridade (OR-25)

- Data: 05/11/2026 22:43
- Firmware: `oriki_esp32` (esp32), bancada a 5.0x
- Meta: 100% das alterações recusadas ou sinalizadas
- Obtido: **100% (2 de 2)** — PASSOU

| caso | esperado | obtido | ok |
|---|---|---|---|
| ORK01-000039 alterado na memória | recusado (assinatura_invalida) | assinatura_invalida | ✔ |
| ORK01-000038 apagado antes do envio | lacuna de contador no painel do fiscal | ORK01: contadores 38 a 39 ausentes | ✔ |
| ciclos íntegros | ORK01-000037 e ORK01-000040 recebidos | ORK01-000036, ORK01-000037, ORK01-000040 | ✔ |
