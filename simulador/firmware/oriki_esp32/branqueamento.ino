// =====================================================================
// ALGORITMO DO BRANQUEAMENTO (OR-11) — a aba para trocar pelo código de vocês
//
// CONTRATO COM AS OUTRAS ABAS
//   Esta aba precisa ter:
//     void branqueamentoSetup()                  chamada uma vez no setup()
//     void branqueamentoLoop(unsigned long agora) chamada a cada volta do loop()
//     bool cicloEmAndamento()                     true no meio de um ciclo (o envio espera)
//   E pode usar (estão nas outras abas):
//     float lerTemperatura()          °C da água, ou NAN se o sensor falhar
//     uint8_t lerBotao(agora)         EV_NENHUM, EV_TOQUE ou EV_SEGUROU (5 s)
//     void leds(bool verde, bool vermelho)
//     void bip(unsigned long ms)      buzzer ativo, sem travar
//     uint32_t reservarContador()     próximo contador, já gravado (nunca volta)
//     uint32_t relogioAgora()         hora do RTC (Belém), em segundos
//     bool registrarCiclo(contador, inicio, fim, tMinCentesimos, tMaxCentesimos, segundos, aprovado)
//                                     assina e põe na fila do LittleFS
//
// Regra (Decreto 326/2012): água a 80 °C ou mais por pelo menos 10 s.
// Mesmo fluxo do oriki_tinkercad.ino:
//   Parado ....... toque = novo lote | segurar 5 s = modo termômetro
//   Preparando ... toque = cesto na água (começa a contar) | segurar 5 s = cancela
//   Imersão ...... toque = cesto fora (fecha o ciclo)
//   Termômetro ... dois toques rápidos = sai
// LEDs: vermelho = água fria | verde piscando = pronta | verde fixo = imersão
//       resultado por 3 s: verde = aprovado, vermelho + bip longo = reprovado
// =====================================================================

const float LIMIAR_C = 80.0;
const unsigned int TEMPO_MIN_S = 10;
const unsigned long IMERSAO_MAX_MS = 60000UL;   // fecha sozinho se ninguém tocar o botão
const unsigned long TEMPO_RESULTADO_MS = 3000;
const unsigned long JANELA_DUPLO_MS = 700;
const unsigned long INTERVALO_PRINT_MS = 1000;

const uint8_t OCIOSO = 0, PREPARANDO = 1, IMERSAO = 2, RESULTADO = 3, TERMOMETRO = 4;
uint8_t estado = OCIOSO;

float tAtual = NAN;
int16_t tMinC = 0, tMaxC = 0;
uint32_t contadorCiclo = 0;
uint32_t inicioRelogio = 0;
unsigned long inicioImersaoMs = 0, inicioResultado = 0, ultimoPrint = 0, ultimoToque = 0;
bool prontoAvisado = false, dezAvisado = false;

int16_t centesimos(float t) { return (int16_t)lroundf(t * 100.0f); }

bool cicloEmAndamento() { return estado == PREPARANDO || estado == IMERSAO; }

void branqueamentoSetup() {
  estado = OCIOSO;
  leds(false, false);
}

void voltarOcioso() {
  leds(false, false);
  estado = OCIOSO;
}

void iniciarImersao(unsigned long agora) {
  contadorCiclo = reservarContador();
  inicioImersaoMs = agora;
  inicioRelogio = relogioAgora();
  tMinC = tMaxC = centesimos(tAtual);
  dezAvisado = false;
  char codigo[32];
  codigoDe(contadorCiclo, codigo);
  Serial.print("Imersao iniciada: ");
  Serial.println(codigo);
  leds(true, false);
  estado = IMERSAO;
}

void fecharCiclo(unsigned long agora, const char *motivo) {
  unsigned long segundos = (agora - inicioImersaoMs) / 1000UL;
  if (segundos > 32767UL) segundos = 32767UL;
  bool aprovado = segundos >= TEMPO_MIN_S && strcmp(motivo, "sensor sem leitura") != 0;
  registrarCiclo(contadorCiclo, inicioRelogio, inicioRelogio + segundos, tMinC, tMaxC, (uint16_t)segundos, aprovado);

  char codigo[32];
  codigoDe(contadorCiclo, codigo);
  Serial.printf("REGISTRO %s | %lu s >= 80 C | min %.2f C | max %.2f C | %s (%s) | salvo na fila\n", codigo, segundos,
                tMinC / 100.0, tMaxC / 100.0, aprovado ? "APROVADO" : "REPROVADO", motivo);
  if (aprovado) {
    leds(true, false);
  } else {
    leds(false, true);
    bip(800);
  }
  inicioResultado = agora;
  estado = RESULTADO;
  envioAgendar(ENVIO_APOS_CICLO_MS);   // aba envio.ino
}

void imprimirTemperatura(unsigned long agora) {
  if (estado != PREPARANDO && estado != IMERSAO && estado != TERMOMETRO) return;
  if (agora - ultimoPrint < INTERVALO_PRINT_MS) return;
  ultimoPrint = agora;
  if (estado == IMERSAO) Serial.printf("Imersao %lu s | ", (agora - inicioImersaoMs) / 1000UL);
  if (isnan(tAtual)) Serial.println("Temperatura: sensor sem leitura");
  else Serial.printf("Temperatura: %.1f C\n", tAtual);
}

void branqueamentoLoop(unsigned long agora) {
  uint8_t ev = lerBotao(agora);
  tAtual = lerTemperatura();
  bool semSensor = isnan(tAtual);

  switch (estado) {
    case OCIOSO:
      if (ev == EV_TOQUE) {
        Serial.println("Novo lote: preparando. Aguarde a agua chegar a 80 C.");
        prontoAvisado = false;
        estado = PREPARANDO;
      } else if (ev == EV_SEGUROU) {
        Serial.println("Modo termometro (dois toques rapidos para sair).");
        ultimoToque = 0;
        estado = TERMOMETRO;
      }
      break;

    case PREPARANDO:
      if (semSensor) {
        leds(false, (agora / 125) % 2 == 0);    // vermelho piscando rápido: sensor com falha
      } else if (tAtual < LIMIAR_C) {
        leds(false, true);
        prontoAvisado = false;
      } else {
        leds((agora / 250) % 2 == 0, false);    // verde piscando: pode mergulhar
        if (!prontoAvisado) {
          prontoAvisado = true;
          bip(150);
          Serial.println("Agua pronta (>= 80 C). Mergulhe o cesto e toque o botao.");
        }
      }
      if (ev == EV_TOQUE) {
        if (semSensor) Serial.println("Sensor sem leitura: confira o DS18B20.");
        else if (tAtual < LIMIAR_C) Serial.println("Agua abaixo de 80 C. Aguarde aquecer.");
        else iniciarImersao(agora);
      } else if (ev == EV_SEGUROU) {
        Serial.println("Lote cancelado (nada foi registrado).");
        voltarOcioso();
      }
      break;

    case IMERSAO: {
      if (semSensor) {
        fecharCiclo(agora, "sensor sem leitura");
        break;
      }
      int16_t c = centesimos(tAtual);
      if (c < tMinC) tMinC = c;
      if (c > tMaxC) tMaxC = c;
      unsigned long decorrido = agora - inicioImersaoMs;
      if (!dezAvisado && decorrido >= TEMPO_MIN_S * 1000UL) {
        dezAvisado = true;
        bip(600);
        Serial.println("10 s acima de 80 C: pode tirar o cesto e tocar o botao.");
      }
      if (tAtual < LIMIAR_C) fecharCiclo(agora, "agua abaixo de 80 C");
      else if (ev == EV_TOQUE) fecharCiclo(agora, "cesto retirado");
      else if (decorrido >= IMERSAO_MAX_MS) fecharCiclo(agora, "tempo maximo");
      break;
    }

    case RESULTADO:
      if (agora - inicioResultado >= TEMPO_RESULTADO_MS) {
        voltarOcioso();
        Serial.println("Pronto para o proximo lote.");
      }
      break;

    case TERMOMETRO:
      if (semSensor) leds(false, (agora / 125) % 2 == 0);
      else leds(tAtual >= LIMIAR_C, tAtual < LIMIAR_C);
      if (ev == EV_TOQUE) {
        if (ultimoToque != 0 && agora - ultimoToque <= JANELA_DUPLO_MS) {
          Serial.println("Saindo do modo termometro.");
          voltarOcioso();
        } else {
          ultimoToque = agora;
        }
      }
      break;
  }
  imprimirTemperatura(agora);
}
