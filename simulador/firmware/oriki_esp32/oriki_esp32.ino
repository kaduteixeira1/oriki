// =====================================================================
// Oriki - firmware do ESP32 (DS18B20 + DS3231 + LittleFS + Wi-Fi)
// OR-39: a versão do oriki_tinkercad.ino para o dispositivo real.
//
// Roda igual na placa (Arduino IDE, placa "ESP32 Dev Module") e no
// simulador do PC (simulador/bancada.py), sem mudar nada.
//
// ABAS
//   oriki_esp32.ino ..... esta: configuração, pinos, setup() e loop()
//   branqueamento.ino ... O ALGORITMO DO CICLO (80 C por 10 s). É a aba
//                         para trocar pelo código de vocês: veja o
//                         contrato no começo dela.
//   assinatura.ino ...... HMAC-SHA256 (seção 7.2 do plano)
//   fila.ino ............ fila local no LittleFS e contador
//   envio.ino ........... POST /api/ciclos a cada 5 min (seção 7)
//   relogio.ino ......... RTC DS3231 e datas ISO 8601 com -03:00
//   comandos.ino ........ comandos do Monitor serial
//
// BIBLIOTECAS (Gerenciador de Bibliotecas da IDE)
//   OneWire, DallasTemperature, RTClib (Adafruit), WiFiManager (tzapu)
// =====================================================================
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <WiFiManager.h>
#include <LittleFS.h>
#include <Preferences.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <RTClib.h>
#include <Wire.h>
#include "mbedtls/md.h"

// ---------- Identidade do dispositivo ----------
const char ID_DISPOSITIVO[] = "ORK01";
// Chave de DEMONSTRAÇÃO (a mesma do seed.py e do oriki_tinkercad.ino).
// Troque pela que o `flask criar-dispositivo` mostrar. Nunca publique a chave real.
const char CHAVE_DISPOSITIVO[] = "7f5f1804ca51c2c77b5371a984cc330aa45570a122f8319e66160fc41201666f";

// ---------- Servidor ----------
// No simulador, a bancada troca este endereço pelo da API local (campo "API" do painel).
const char URL_API[] = "https://oriki.exemplo/api/ciclos";
// Certificado raiz (PEM) da autoridade que emitiu o certificado do domínio (seção 7.6).
// Vazio = sem verificar o certificado: aceitável SÓ na bancada.
const char CA_RAIZ[] = "";
const unsigned long INTERVALO_ENVIO_MS = 5UL * 60UL * 1000UL;  // a cada 5 minutos
const unsigned long ENVIO_APOS_CICLO_MS = 10000UL;             // e 10 s depois de cada ciclo
const int MAX_POR_ENVIO = 50;                                   // limite da API

// Correção somada à leitura do sensor (resultado da calibração em bancada, OR-14).
const float CALIBRACAO_C = 0.0;

// ---------- Pinos (seção "Ligações" do documento do projeto) ----------
const int PINO_SENSOR       = 4;   // DS18B20 (dados), pull-up de 4,7 kOhm para 3V3
const int PINO_BOTAO        = 33;  // outro terminal no GND (pull-up interno)
const int PINO_LED_VERDE    = 26;
const int PINO_LED_VERMELHO = 27;
const int PINO_BUZZER       = 25;  // buzzer ativo pelo transistor BC337
// RTC DS3231: SDA no GPIO 21, SCL no GPIO 22 (padrão do Wire)

OneWire barramento(PINO_SENSOR);
DallasTemperature sensor(&barramento);
RTC_DS3231 rtc;
Preferences nvs;

bool rtcOk = false;

void setup() {
  Serial.begin(115200);
  delay(200);
  pinMode(PINO_BOTAO, INPUT_PULLUP);
  pinMode(PINO_LED_VERDE, OUTPUT);
  pinMode(PINO_LED_VERMELHO, OUTPUT);
  pinMode(PINO_BUZZER, OUTPUT);
  leds(false, false);

  if (!LittleFS.begin(true)) Serial.println("ERRO: LittleFS nao montou. A fila nao vai funcionar.");
  filaPreparar();

  Wire.begin();
  rtcOk = rtc.begin();
  if (!rtcOk) Serial.println("ERRO: RTC DS3231 nao encontrado (SDA 21, SCL 22). Os ciclos ficam sem hora certa.");
  else if (rtc.lostPower()) Serial.println("Aviso: o RTC perdeu a hora. Ela sera corrigida no primeiro envio.");

  sensor.begin();
  sensor.setResolution(11);          // 0,125 C, conversão em ~375 ms
  sensor.setWaitForConversion(false);
  sensor.requestTemperatures();

  Serial.print("Oriki ");
  Serial.print(ID_DISPOSITIVO);
  Serial.print(" (ESP32) pronto | pendentes: ");
  Serial.print(filaContar("/pendentes"));
  Serial.print(" | ultimo contador: ");
  Serial.println((unsigned long)contadorAtual());
  Serial.print("Relogio: ");
  Serial.println(isoAgora());
  if (!autoteste()) Serial.println("ERRO: HMAC diferente do backend. Nao use este firmware.");

  envioSetup();
  branqueamentoSetup();
  Serial.println("Toque o botao para um novo lote. Digite 'ajuda' para os comandos.");
}

void loop() {
  unsigned long agora = millis();
  lerSerial(agora);
  branqueamentoLoop(agora);   // aba branqueamento.ino
  envioLoop(agora);           // aba envio.ino (não envia no meio de um ciclo)
  delay(10);
}

// =====================================================================
// Hardware usado pela aba do branqueamento
// =====================================================================
float ultimaTemperatura = NAN;
unsigned long ultimaLeituraMs = 0;

// Temperatura da água em °C, ou NAN se o sensor falhar. Lê no máximo a cada 500 ms.
float lerTemperatura() {
  unsigned long agora = millis();
  if (ultimaLeituraMs != 0 && agora - ultimaLeituraMs < 500) return ultimaTemperatura;
  ultimaLeituraMs = agora;
  float t = sensor.getTempCByIndex(0);
  sensor.requestTemperatures();     // já pede a próxima (não bloqueia)
  ultimaTemperatura = (t <= DEVICE_DISCONNECTED_C + 1 || t > 125) ? NAN : t + CALIBRACAO_C;
  return ultimaTemperatura;
}

void leds(bool verde, bool vermelho) {
  digitalWrite(PINO_LED_VERDE, verde ? HIGH : LOW);
  digitalWrite(PINO_LED_VERMELHO, vermelho ? HIGH : LOW);
}

// Buzzer ativo: liga e desliga sozinho depois de `ms` (sem travar o loop).
unsigned long bipAte = 0;
void bip(unsigned long ms) {
  digitalWrite(PINO_BUZZER, HIGH);
  bipAte = millis() + ms;
}
void atualizarBuzzer(unsigned long agora) {
  if (bipAte && (long)(agora - bipAte) >= 0) {
    digitalWrite(PINO_BUZZER, LOW);
    bipAte = 0;
  }
}

// Botão: EV_TOQUE (toque rápido) ou EV_SEGUROU (segurou 5 s). Com debounce.
const uint8_t EV_NENHUM = 0, EV_TOQUE = 1, EV_SEGUROU = 2;
const unsigned long TEMPO_SEGURAR_MS = 5000;
int botaoAnterior = HIGH;
unsigned long ultimaMudanca = 0, inicioAperto = 0;
bool longoDisparado = false;

uint8_t lerBotao(unsigned long agora) {
  atualizarBuzzer(agora);
  int leitura = digitalRead(PINO_BOTAO);   // apertado = LOW
  if (leitura != botaoAnterior && agora - ultimaMudanca > 30) {
    ultimaMudanca = agora;
    botaoAnterior = leitura;
    if (leitura == LOW) {
      inicioAperto = agora;
      longoDisparado = false;
      return EV_NENHUM;
    }
    return longoDisparado ? EV_NENHUM : EV_TOQUE;
  }
  if (botaoAnterior == LOW && !longoDisparado && agora - inicioAperto >= TEMPO_SEGURAR_MS) {
    longoDisparado = true;
    return EV_SEGUROU;
  }
  return EV_NENHUM;
}
