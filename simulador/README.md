# Oriki — simulador do ESP32 (bancada virtual)

Roda o **código do firmware de verdade** (`.ino`) no PC, ligado a um tanque, botão, LEDs, buzzer, RTC e Wi-Fi
de mentira, e manda os ciclos assinados para a API do Oriki. O mesmo `.ino` abre na IDE do Arduino e grava no
ESP32 sem mudar nada.

```
simulador/
├── bancada.py            painel + tanque + ponte para a API (só biblioteca padrão do Python)
├── compilar.py           junta as abas do sketch, gera os protótipos e compila (como a IDE do Arduino)
├── cenarios.py           testes do documento: critério do ciclo, integridade e sincronização offline
├── painel/index.html     o painel (http://localhost:8090)
├── nucleo/               Arduino.h e bibliotecas de mentira (WiFi, HTTPClient, LittleFS, DallasTemperature,
│                         RTClib, Preferences, EEPROM, mbedtls, WiFiManager)
├── firmware/
│   ├── oriki_esp32/      firmware do ESP32 (OR-39): DS18B20, DS3231, LittleFS e envio a cada 5 min
│   │   └── branqueamento.ino   ← o algoritmo do ciclo, a aba para trocar pelo código de vocês
│   └── oriki_tinkercad/  o sketch do Tinkercad (Uno + TMP36), sem nenhuma alteração
├── iniciar_bancada.bat   atalho do Windows
├── dados/                memória de cada dispositivo simulado (criada sozinha; fora do Git)
└── relatorios/           relatórios dos testes em Markdown (criados sozinhos)
```

## Rodar

Requisitos: Python 3.10+ e um compilador C++. No Windows o mais fácil é o zig, que vem pelo pip:

```bash
pip install ziglang          # Windows sem g++ (o iniciar_bancada.bat já faz isso)
```

No Linux/macOS serve o g++ ou o clang que já vêm no sistema.

Com a API rodando (`backend/iniciar.bat` ou `flask run`):

```bash
python bancada.py --contador-inicial 31          # firmware/oriki_esp32; abre o painel no navegador
python bancada.py firmware/oriki_tinkercad --contador-inicial 31
python bancada.py --api https://oriki.exemplo    # outra API (o firmware usa o caminho /api/ciclos)
python bancada.py --velocidade 5                 # tempo 5x mais rápido (bom para os testes)
```

`--contador-inicial 31` só vale para uma memória nova: o primeiro ciclo sai como `ORK01-000031`, continuando os
30 ciclos que o `seed.py` grava com a mesma chave de demonstração. Sem isso, os contadores 1 a 30 voltam como
`conflito` (a API está certa: o mesmo código com outra assinatura).

## O painel

- **Bancada**: tanque com aquecedor e termostato, "Mergulhar o cesto" (a água cai alguns graus, como com o fruto
  frio), temperatura fixa, sensor desconectado, o **botão físico** (clique = toque, segurar = 5 s, tecla espaço),
  LEDs e buzzer (com som opcional), Monitor serial com os comandos do firmware, roteador Wi-Fi liga/desliga,
  cada envio para a API (corpo e resposta) e o relógio do dispositivo (atrasar/adiantar 10 min para testar o
  "relógio divergente").
- **Código do firmware**: abre as abas do sketch, edita, salva e compila. Erros de compilação aparecem no painel
  com a linha do `.ino`. "Novo sketch" copia o `oriki_esp32` para vocês colarem o código de vocês.
- **Testes**: roda os testes do documento do projeto e grava o relatório em `relatorios/`.

## Colocar o código de branqueamento de vocês

**Opção 1 — só o algoritmo**: troque o conteúdo de `firmware/oriki_esp32/branqueamento.ino` (pelo painel ou no
editor). A aba precisa ter três funções e pode usar as das outras abas:

| A aba fornece | Para quê |
|---|---|
| `void branqueamentoSetup()` | chamada uma vez no `setup()` |
| `void branqueamentoLoop(unsigned long agora)` | chamada a cada volta do `loop()` |
| `bool cicloEmAndamento()` | o envio por Wi-Fi espera o ciclo terminar |

| A aba pode usar | O que faz |
|---|---|
| `float lerTemperatura()` | °C da água (DS18B20), ou `NAN` se o sensor falhar |
| `uint8_t lerBotao(agora)` | `EV_NENHUM`, `EV_TOQUE` ou `EV_SEGUROU` (5 s), com debounce |
| `leds(verde, vermelho)` e `bip(ms)` | avisos ao operador, sem travar o `loop()` |
| `uint32_t reservarContador()` | próximo contador, já gravado na NVS (nunca volta) |
| `uint32_t relogioAgora()` | hora do RTC (Belém) em segundos |
| `registrarCiclo(contador, inicio, fim, tMinCent, tMaxCent, segundos, aprovado)` | assina (HMAC) e grava na fila do LittleFS |

A assinatura, a fila, o envio e o relógio continuam iguais, então o contrato da seção 7 do plano não muda.

**Opção 2 — o sketch inteiro**: crie uma pasta em `firmware/` (ex.: `firmware/meu_sketch/meu_sketch.ino`) e cole o
`.ino`. A placa é detectada pelos `#include` (Wi-Fi/HTTP/LittleFS = ESP32; EEPROM sem nada do ESP32 = Uno), ou
use `--placa esp32|uno`. Funciona com o que o firmware do Oriki usa:

| Recurso | No simulador |
|---|---|
| `millis`, `delay`, `pinMode`, `digitalRead/Write`, `analogRead`, `tone` | tempo do PC (acelerável); `analogRead` lê um TMP36 na água |
| `Serial` (print, println, printf, available, read, readStringUntil) | Monitor serial do painel |
| `String`, `F()`, `PROGMEM`, `pgm_read_*`, `dtostrf` | como no Arduino |
| `EEPROM` | arquivo `dados/<sketch>/eeprom.bin` |
| `LittleFS` / `SPIFFS` / `File` | pasta `dados/<sketch>/littlefs/` |
| `Preferences` | `dados/<sketch>/nvs/` |
| `OneWire` + `DallasTemperature` | temperatura da água do painel (degraus de 0,0625 °C) |
| `RTClib` (`RTC_DS3231`, `DateTime`) | hora de Belém do PC + ajuste guardado (como a bateria do DS3231) |
| `WiFi`, `WiFiManager`, `WiFiClientSecure` | roteador do painel |
| `HTTPClient` (`POST`, `GET`, `getString`) | repassado para a API de verdade pelo `--api` |
| `mbedtls/md.h` (HMAC-SHA256) | implementação própria, conferida com os vetores da seção 7.2 |
| `configTime`, `getLocalTime`, `ESP.restart()` | hora do PC; o restart religa o dispositivo |

Uma biblioteca só de cabeçalhos (ex.: ArduinoJson) funciona se for copiada para `simulador/bibliotecas/<nome>/`.
O que depende do hardware de verdade (interrupções, PWM, Bluetooth, sono profundo) não é simulado.

**Sketch sem Wi-Fi (Tinkercad)**: a bancada lê o JSON que o comando `enviar` imprime no Serial, manda para a API
e responde `ok <código>` para cada ciclo recebido (a "ponte serial", o papel do `conferir_envio.py`). O envio
automático a cada 5 min e o acerto do relógio (`hora ...`) ao ligar já vêm ligados para o Uno.

## Testes do documento do projeto

Pelo painel (aba Testes) ou direto no terminal, com a API rodando:

```bash
python bancada.py --cenario criterio --velocidade 5                 # OR-26: 30 ciclos, meta 30 de 30
python bancada.py --cenario integridade --velocidade 5              # OR-25: alterar e apagar, meta 100%
python bancada.py --cenario offline --velocidade 6                  # OR-24: 50 ciclos sem Wi-Fi
python bancada.py firmware/oriki_tinkercad --cenario integridade    # os mesmos testes no sketch do Tinkercad
```

O código de saída é 0 se o teste passou, e o relatório (com a tabela caso a caso) fica em `relatorios/`.
Integridade e offline conferem no servidor com o login do fiscal do `seed.py`.

Resultados na bancada (05/11/2026): critério 30 de 30, integridade 100% no ESP32 e no Tinkercad
(o ciclo alterado volta `assinatura_invalida` e o apagado aparece como lacuna no painel do fiscal), offline 8 de 8
sem duplicados.

Observações:

- Os dois sketches de exemplo usam o mesmo identificador (`ORK01`). Na API eles são o mesmo dispositivo: se os
  dois gravarem o mesmo contador, o segundo volta como `conflito`. Para usar os dois, dê a cada um uma faixa de
  contador (`--contador-inicial`) ou crie outro dispositivo com `flask criar-dispositivo`.
- Com `--velocidade` maior que 1, o `millis()` acelera, mas o relógio do dispositivo segue a hora real (para o
  servidor não marcar todos os ciclos como relógio divergente). O sketch do Tinkercad, que conta a hora pelo
  `millis()`, adianta na mesma proporção.
- O documento pede 48 h sem Wi-Fi no teste offline; na bancada o tempo offline é o de gravar os ciclos.
