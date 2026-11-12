// =====================================================================
// Oriki - firmware de representação no Tinkercad (Arduino Uno + TMP36)
// Entrega de 22/10: OR-11 (ciclo de 80 C por 10 s), OR-12 (HMAC + contador)
//                   e OR-13 (fila local)
//
// No dispositivo real: ESP32 + DS18B20 + LittleFS + Wi-Fi.
// Aqui: Uno + TMP36 + EEPROM (1 KB, 19 ciclos) e o Monitor serial no lugar
// do Wi-Fi. A mensagem assinada e o JSON do envio seguem a seção 7 do
// plano-backend-oriki.md, byte a byte.
//
// BOTÃO
//   Parado ........ toque rápido = novo lote | segurar 5 s = modo termômetro
//   Preparando .... toque rápido = cesto na água (começa a contar)
//                   segurar 5 s = cancela o lote (nada é registrado)
//   Imersão ....... toque rápido = cesto fora (fecha o ciclo)
//   Termômetro .... dois toques rápidos = sai
//
// LEDS E PIEZO
//   vermelho fixo ....... água abaixo de 80 C
//   verde piscando ...... água pronta (bip curto quando chega a 80 C)
//   verde fixo .......... imersão em andamento (bip longo aos 10 s: pode tirar o cesto)
//   laranja ............. água acima de 90 C (só aviso, não reprova)
//   resultado (3 s) ..... verde = aprovado | vermelho + bip grave = reprovado
//
// MONITOR SERIAL (digite o comando e clique em Enviar)
//   ajuda | fila | enviar | ok todos | ok <n> | hora AAAA-MM-DD HH:MM:SS
//   adulterar <n> | teste | zerar
// =====================================================================

#include <EEPROM.h>
#include <avr/pgmspace.h>

// ---------- Identidade do dispositivo ----------
const char ID_DISPOSITIVO[] = "ORK01";
// Chave de DEMONSTRAÇÃO (64 caracteres hex, usada como texto).
// Troque pela chave que o `flask criar-dispositivo` mostrar.
// Não deixe a chave real num projeto público do Tinkercad.
const char CHAVE_DISPOSITIVO[] = "7f5f1804ca51c2c77b5371a984cc330aa45570a122f8319e66160fc41201666f";

// O Uno não tem RTC: o relógio começa nesta hora (Belém, -03:00) e anda com
// o millis(). Para acertar durante a simulação, use o comando "hora".
const char HORA_INICIAL[] = "2026-10-22 07:30:00";

// ---------- Pinos (os mesmos do circuito do OR-01) ----------
const int PINO_SENSOR       = A0;  // TMP36 (Vout)
const int PINO_BOTAO        = 2;   // o outro terminal do botão vai no GND
const int PINO_LED_VERDE    = 4;
const int PINO_LED_VERMELHO = 5;
const int PINO_LED_LARANJA  = 6;
const int PINO_BUZZER       = 8;   // piezo

// ---------- Regras do ciclo ----------
const float LIMIAR_C        = 80.0;     // Decreto 326/2012: água a 80 C...
const unsigned int TEMPO_MIN_S = 10;    // ...por 10 segundos
const float LIMITE_ALTO_C   = 90.0;     // acima disso acende o laranja
const float CALIBRACAO_C    = 0.0;      // correção somada à leitura (resultado da bancada, OR-14)
const unsigned long IMERSAO_MAX_MS = 60000UL;  // fecha sozinho se ninguém tocar o botão

const unsigned long INTERVALO_LEITURA_MS = 500;   // lê o sensor 2 vezes por segundo
const unsigned long INTERVALO_PRINT_MS   = 1000;  // escreve a temperatura 1 vez por segundo
const unsigned long TEMPO_SEGURAR_MS     = 5000;
const unsigned long JANELA_DUPLO_MS      = 700;
const unsigned long TEMPO_RESULTADO_MS   = 3000;
const int MAX_POR_ENVIO = 50;                     // limite da API

// ---------- Estados e eventos ----------
const uint8_t OCIOSO = 0, PREPARANDO = 1, IMERSAO = 2, RESULTADO = 3, TERMOMETRO = 4;
const uint8_t EV_NENHUM = 0, EV_TOQUE = 1, EV_SEGUROU = 2;
uint8_t estado = OCIOSO;

// ---------- Fila local na EEPROM ----------
// Cabeçalho: [0..1] marca, [2..5] último contador usado. Os ciclos vêm depois.
const uint16_t MARCA_EEPROM = 0x4F31;
const int END_MARCA = 0;
const int END_CONTADOR = 2;
const int INICIO_SLOTS = 8;
const uint8_t VAZIO = 0, PENDENTE = 1, ENVIADO = 2;

struct Registro {
  uint8_t  estado;          // VAZIO, PENDENTE ou ENVIADO
  uint32_t contador;        // sequencial por dispositivo, nunca se repete
  uint32_t inicio;          // segundos desde 1970, hora local de Belém
  uint32_t fim;
  int16_t  tMin;            // centésimos de grau (8120 = 81.20 C)
  int16_t  tMax;
  uint16_t segundos;        // segundos com água >= 80 C
  uint8_t  aprovado;        // 1 = aprovado, 0 = reprovado
  uint8_t  assinatura[32];  // HMAC-SHA256 da mensagem do ciclo
} __attribute__((packed));

Registro reg;               // registro em uso (lido ou gravado na EEPROM)
const int TAM_SLOT = sizeof(Registro);
int nSlots = 0;

// ---------- Variáveis do ciclo ----------
float tAtual = 0;
int16_t tMinC = 0, tMaxC = 0;
bool alertaAlto = false;
bool prontoAvisado = false;
bool dezAvisado = false;
uint32_t contadorAtual = 0;
int slotAtual = -1;
uint32_t inicioRelogio = 0;
unsigned long inicioImersaoMs = 0;
unsigned long inicioResultado = 0;
unsigned long ultimaLeitura = 0;
unsigned long ultimoPrint = 0;

// botão
int botaoAnterior = HIGH;
unsigned long ultimaMudanca = 0;
unsigned long inicioAperto = 0;
bool longoDisparado = false;
unsigned long ultimoToque = 0;

// relógio
uint32_t relogioBase = 0;
unsigned long relogioBaseMs = 0;

// comandos do Monitor serial
char cmd[48];
uint8_t cmdLen = 0;
unsigned long ultimoChar = 0;

// =====================================================================
// SHA-256 e HMAC-SHA256 (o Tinkercad não tem biblioteca de criptografia)
// =====================================================================
const uint32_t K256[64] PROGMEM = {
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2
};

uint32_t shaH[8];
uint8_t  shaBuf[64];
uint8_t  shaLen = 0;
uint32_t shaTotal = 0;      // bytes processados
uint8_t  hmacChave[64];

uint32_t rotr(uint32_t x, uint8_t n) {
  return (x >> n) | (x << (32 - n));
}

void shaBloco() {
  uint32_t w[16];
  for (uint8_t i = 0; i < 16; i++) {
    w[i] = ((uint32_t)shaBuf[4 * i] << 24) | ((uint32_t)shaBuf[4 * i + 1] << 16) |
           ((uint32_t)shaBuf[4 * i + 2] << 8) | (uint32_t)shaBuf[4 * i + 3];
  }
  uint32_t a = shaH[0], b = shaH[1], c = shaH[2], d = shaH[3];
  uint32_t e = shaH[4], f = shaH[5], g = shaH[6], h = shaH[7];
  for (uint8_t i = 0; i < 64; i++) {
    if (i >= 16) {
      uint32_t w15 = w[(i + 1) & 15], w2 = w[(i + 14) & 15];
      uint32_t s0 = rotr(w15, 7) ^ rotr(w15, 18) ^ (w15 >> 3);
      uint32_t s1 = rotr(w2, 17) ^ rotr(w2, 19) ^ (w2 >> 10);
      w[i & 15] += s0 + s1 + w[(i + 9) & 15];
    }
    uint32_t t1 = h + (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) + ((e & f) ^ (~e & g)) +
                  pgm_read_dword(&K256[i]) + w[i & 15];
    uint32_t t2 = (rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) + ((a & b) ^ (a & c) ^ (b & c));
    h = g; g = f; f = e; e = d + t1; d = c; c = b; b = a; a = t1 + t2;
  }
  shaH[0] += a; shaH[1] += b; shaH[2] += c; shaH[3] += d;
  shaH[4] += e; shaH[5] += f; shaH[6] += g; shaH[7] += h;
}

void shaInicio() {
  shaH[0] = 0x6a09e667; shaH[1] = 0xbb67ae85; shaH[2] = 0x3c6ef372; shaH[3] = 0xa54ff53a;
  shaH[4] = 0x510e527f; shaH[5] = 0x9b05688c; shaH[6] = 0x1f83d9ab; shaH[7] = 0x5be0cd19;
  shaLen = 0;
  shaTotal = 0;
}

void shaByte(uint8_t b) {
  shaBuf[shaLen++] = b;
  shaTotal++;
  if (shaLen == 64) {
    shaBloco();
    shaLen = 0;
  }
}

void shaTexto(const char *s) {
  while (*s) shaByte((uint8_t)*s++);
}

void shaTextoP(const char *s) {          // texto guardado na flash (PROGMEM)
  char c;
  while ((c = pgm_read_byte(s++)) != 0) shaByte((uint8_t)c);
}

void shaFim(uint8_t *saida) {
  uint32_t bitsAlto = shaTotal >> 29;
  uint32_t bitsBaixo = shaTotal << 3;
  shaBuf[shaLen++] = 0x80;
  if (shaLen > 56) {
    while (shaLen < 64) shaBuf[shaLen++] = 0;
    shaBloco();
    shaLen = 0;
  }
  while (shaLen < 56) shaBuf[shaLen++] = 0;
  for (int8_t i = 3; i >= 0; i--) shaBuf[shaLen++] = (uint8_t)(bitsAlto >> (8 * i));
  for (int8_t i = 3; i >= 0; i--) shaBuf[shaLen++] = (uint8_t)(bitsBaixo >> (8 * i));
  shaBloco();
  for (uint8_t i = 0; i < 8; i++) {
    saida[4 * i]     = (uint8_t)(shaH[i] >> 24);
    saida[4 * i + 1] = (uint8_t)(shaH[i] >> 16);
    saida[4 * i + 2] = (uint8_t)(shaH[i] >> 8);
    saida[4 * i + 3] = (uint8_t)shaH[i];
  }
}

// A chave é o texto (bytes ASCII), como no plano: 64 caracteres hex = 64 bytes.
void hmacInicio(const char *chave) {
  size_t n = strlen(chave);
  memset(hmacChave, 0, sizeof(hmacChave));
  if (n > 64) {
    shaInicio();
    shaTexto(chave);
    shaFim(hmacChave);
  } else {
    memcpy(hmacChave, chave, n);
  }
  shaInicio();
  for (uint8_t i = 0; i < 64; i++) shaByte(hmacChave[i] ^ 0x36);
}

void hmacFim(uint8_t *saida) {
  uint8_t interno[32];
  shaFim(interno);
  shaInicio();
  for (uint8_t i = 0; i < 64; i++) shaByte(hmacChave[i] ^ 0x5c);
  for (uint8_t i = 0; i < 32; i++) shaByte(interno[i]);
  shaFim(saida);
}

void paraHex(const uint8_t *bytes, char *saida) {   // saida precisa de 65 posições
  const char digitos[] = "0123456789abcdef";
  for (uint8_t i = 0; i < 32; i++) {
    saida[2 * i]     = digitos[bytes[i] >> 4];
    saida[2 * i + 1] = digitos[bytes[i] & 0x0F];
  }
  saida[64] = 0;
}

// Vetores de teste da seção 7.2 do plano (chave "chave-de-teste")
const char VET_CHAVE[] PROGMEM = "chave-de-teste";
const char VET_MSG1[] PROGMEM = "ORK01|2026-10-08T07:50:00-03:00";
const char VET_HEX1[] PROGMEM = "74a7b50b829144a0b5e44210049c7b8ba941e9b1b927f8da2f8bc9aab33a2c71";
const char VET_MSG2[] PROGMEM =
  "ORK01-000128|128|2026-10-08T07:42:10-03:00|2026-10-08T07:42:24-03:00|81.20|84.60|12|aprovado";
const char VET_HEX2[] PROGMEM = "d7d02435af15a3b257a765d3e90b17687d780a7620d70b3c76350b9ff8f9d24d";

bool conferirVetor(const char *msgP, const char *hexP) {
  char chave[16];
  strcpy_P(chave, VET_CHAVE);
  hmacInicio(chave);
  shaTextoP(msgP);
  uint8_t dig[32];
  char hex[65];
  hmacFim(dig);
  paraHex(dig, hex);
  return strcmp_P(hex, hexP) == 0;
}

bool autoteste() {
  bool ok1 = conferirVetor(VET_MSG1, VET_HEX1);
  bool ok2 = conferirVetor(VET_MSG2, VET_HEX2);
  Serial.print(F("Autoteste HMAC (vetores da secao 7.2): "));
  Serial.print(ok1 ? F("envio OK") : F("envio FALHOU"));
  Serial.print(F(" | "));
  Serial.println(ok2 ? F("ciclo OK") : F("ciclo FALHOU"));
  return ok1 && ok2;
}

// =====================================================================
// Relógio (hora local de Belém, sem horário de verão)
// =====================================================================
long diasDesde1970(long a, long m, long d) {
  a -= (m <= 2) ? 1 : 0;
  long era = (a >= 0 ? a : a - 399) / 400;
  long ano = a - era * 400;
  long diaAno = (153L * (m + (m > 2 ? -3 : 9)) + 2) / 5 + d - 1;
  long diaEra = ano * 365L + ano / 4 - ano / 100 + diaAno;
  return era * 146097L + diaEra - 719468L;
}

uint32_t agoraRelogio() {
  return relogioBase + (millis() - relogioBaseMs) / 1000UL;
}

// "2026-10-22T07:42:10-03:00" (saida precisa de 26 posições)
void formatarIso(uint32_t t, char *saida) {
  long z = (long)(t / 86400UL) + 719468L;
  long seg = (long)(t % 86400UL);
  long era = z / 146097L;
  long diaEra = z - era * 146097L;
  long ano = (diaEra - diaEra / 1460 + diaEra / 36524 - diaEra / 146096) / 365;
  long diaAno = diaEra - (365L * ano + ano / 4 - ano / 100);
  long mp = (5 * diaAno + 2) / 153;
  long dia = diaAno - (153 * mp + 2) / 5 + 1;
  long mes = mp < 10 ? mp + 3 : mp - 9;
  ano += era * 400 + (mes <= 2 ? 1 : 0);
  snprintf(saida, 26, "%04ld-%02ld-%02ldT%02ld:%02ld:%02ld-03:00",
           ano, mes, dia, seg / 3600, (seg / 60) % 60, seg % 60);
}

long lerNumero(const char *s, uint8_t n) {
  long v = 0;
  for (uint8_t i = 0; i < n; i++) {
    if (s[i] < '0' || s[i] > '9') return -1;
    v = v * 10 + (s[i] - '0');
  }
  return v;
}

// Aceita "AAAA-MM-DD HH:MM:SS" ou "AAAA-MM-DDTHH:MM:SS"
bool lerHora(const char *s, uint32_t *saida) {
  if (strlen(s) < 19 || s[4] != '-' || s[7] != '-' || (s[10] != ' ' && s[10] != 'T') ||
      s[13] != ':' || s[16] != ':') return false;
  long a = lerNumero(s, 4), m = lerNumero(s + 5, 2), d = lerNumero(s + 8, 2);
  long hh = lerNumero(s + 11, 2), mm = lerNumero(s + 14, 2), ss = lerNumero(s + 17, 2);
  if (a < 2020 || m < 1 || m > 12 || d < 1 || d > 31 || hh < 0 || hh > 23 ||
      mm < 0 || mm > 59 || ss < 0 || ss > 59) return false;
  *saida = (uint32_t)diasDesde1970(a, m, d) * 86400UL + (uint32_t)(hh * 3600L + mm * 60L + ss);
  return true;
}

void acertarRelogio(uint32_t t) {
  relogioBase = t;
  relogioBaseMs = millis();
}

// =====================================================================
// Formatação dos campos (a mesma usada na assinatura e no JSON)
// =====================================================================
int16_t paraCentesimos(float t) {
  return (int16_t)(t >= 0 ? t * 100.0 + 0.5 : t * 100.0 - 0.5);
}

void formatarTemp(int16_t centesimos, char *saida) {   // "81.20", "-0.05" (saida: 10 posições)
  long v = centesimos;
  bool negativo = v < 0;
  if (negativo) v = -v;
  snprintf(saida, 10, "%s%ld.%02ld", negativo ? "-" : "", v / 100, v % 100);
}

void codigoDe(uint32_t contador, char *saida) {        // "ORK01-000128" (saida: 32 posições)
  snprintf(saida, 32, "%s-%06lu", ID_DISPOSITIVO, (unsigned long)contador);
}

// codigo|contador|inicio|fim|temp_min|temp_max|segundos_acima_80|status
void montarMensagem(char *saida, size_t tamanho) {
  char codigo[32], ini[26], fim[26], tmin[10], tmax[10];
  codigoDe(reg.contador, codigo);
  formatarIso(reg.inicio, ini);
  formatarIso(reg.fim, fim);
  formatarTemp(reg.tMin, tmin);
  formatarTemp(reg.tMax, tmax);
  snprintf(saida, tamanho, "%s|%lu|%s|%s|%s|%s|%u|%s", codigo, (unsigned long)reg.contador,
           ini, fim, tmin, tmax, (unsigned int)reg.segundos, reg.aprovado ? "aprovado" : "reprovado");
}

void assinarRegistro() {
  char msg[160];
  montarMensagem(msg, sizeof(msg));
  hmacInicio(CHAVE_DISPOSITIVO);
  shaTexto(msg);
  hmacFim(reg.assinatura);
}

bool registroIntegro() {
  char msg[160];
  uint8_t dig[32];
  montarMensagem(msg, sizeof(msg));
  hmacInicio(CHAVE_DISPOSITIVO);
  shaTexto(msg);
  hmacFim(dig);
  return memcmp(dig, reg.assinatura, 32) == 0;
}

// =====================================================================
// Fila na EEPROM (no ESP32 real: arquivo no LittleFS)
// =====================================================================
uint32_t lerContador() {
  uint32_t c;
  EEPROM.get(END_CONTADOR, c);
  return c;
}

void gravarContador(uint32_t c) {
  EEPROM.put(END_CONTADOR, c);
}

void lerSlot(int i) {
  EEPROM.get(INICIO_SLOTS + i * TAM_SLOT, reg);
}

void gravarSlot(int i) {
  EEPROM.put(INICIO_SLOTS + i * TAM_SLOT, reg);
}

void formatarFila() {
  EEPROM.put(END_MARCA, MARCA_EEPROM);
  gravarContador(0);
  for (int i = 0; i < nSlots; i++) EEPROM.update(INICIO_SLOTS + i * TAM_SLOT, VAZIO);
}

// Primeiro um slot vazio; senão, o enviado mais antigo. -1 se tudo estiver pendente.
int slotLivre() {
  int escolhido = -1;
  uint32_t menor = 0xFFFFFFFFUL;
  for (int i = 0; i < nSlots; i++) {
    lerSlot(i);
    if (reg.estado == VAZIO) return i;
    if (reg.estado == ENVIADO && reg.contador < menor) {
      menor = reg.contador;
      escolhido = i;
    }
  }
  return escolhido;
}

// Próximo slot (em ordem de contador) com contador maior que "depoisDe".
// estadoBuscado = 255 aceita qualquer estado diferente de VAZIO.
int proximoSlot(uint32_t depoisDe, uint8_t estadoBuscado) {
  int escolhido = -1;
  uint32_t menor = 0xFFFFFFFFUL;
  for (int i = 0; i < nSlots; i++) {
    lerSlot(i);
    if (reg.estado == VAZIO) continue;
    if (estadoBuscado != 255 && reg.estado != estadoBuscado) continue;
    if (reg.contador > depoisDe && reg.contador < menor) {
      menor = reg.contador;
      escolhido = i;
    }
  }
  return escolhido;
}

int slotDoContador(uint32_t contador) {
  for (int i = 0; i < nSlots; i++) {
    lerSlot(i);
    if (reg.estado != VAZIO && reg.contador == contador) return i;
  }
  return -1;
}

int contarEstado(uint8_t e) {
  int n = 0;
  for (int i = 0; i < nSlots; i++) {
    lerSlot(i);
    if (reg.estado == e) n++;
  }
  return n;
}

// =====================================================================
// Sensor, LEDs e botão
// =====================================================================
float lerTemperatura() {
  int leitura = analogRead(PINO_SENSOR);       // 0 a 1023
  float tensao = leitura * (5.0 / 1024.0);     // em volts
  return (tensao - 0.5) * 100.0 + CALIBRACAO_C; // TMP36: 500 mV a 0 C, 10 mV/C
}

void leds(bool verde, bool vermelho) {
  digitalWrite(PINO_LED_VERDE, verde ? HIGH : LOW);
  digitalWrite(PINO_LED_VERMELHO, vermelho ? HIGH : LOW);
}

// Lê no máximo a cada INTERVALO_LEITURA_MS (ou na hora, se forcar) e cuida do laranja.
void medir(unsigned long agora, bool forcar) {
  if (!forcar && agora - ultimaLeitura < INTERVALO_LEITURA_MS) return;
  ultimaLeitura = agora;
  tAtual = lerTemperatura();
  if (!alertaAlto && tAtual > LIMITE_ALTO_C) {
    alertaAlto = true;
    Serial.print(F("ATENCAO: agua acima de "));
    Serial.print(LIMITE_ALTO_C, 0);
    Serial.println(F(" C"));
  } else if (alertaAlto && tAtual < LIMITE_ALTO_C - 1.0) {   // 1 C de folga
    alertaAlto = false;
  }
  digitalWrite(PINO_LED_LARANJA, alertaAlto ? HIGH : LOW);
}

uint8_t lerBotao(unsigned long agora) {
  int leitura = digitalRead(PINO_BOTAO);       // INPUT_PULLUP: apertado = LOW
  if (leitura != botaoAnterior && agora - ultimaMudanca > 30) {   // debounce
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

// =====================================================================
// Ciclo de branqueamento (OR-11)
// =====================================================================
void voltarOcioso() {
  leds(false, false);
  alertaAlto = false;
  digitalWrite(PINO_LED_LARANJA, LOW);
  estado = OCIOSO;
}

void iniciarLote(unsigned long agora) {
  Serial.println(F("Novo lote: preparando. Aguarde a agua chegar a 80 C."));
  prontoAvisado = false;
  medir(agora, true);
  estado = PREPARANDO;
}

void iniciarImersao(unsigned long agora) {
  slotAtual = slotLivre();
  if (slotAtual < 0) {
    Serial.print(F("FILA CHEIA: "));
    Serial.print(nSlots);
    Serial.println(F(" ciclos pendentes. Use 'enviar' e depois 'ok todos'."));
    tone(PINO_BUZZER, 400, 300);
    return;
  }
  // O contador é reservado e gravado já no início: nunca volta, nem se a energia cair.
  contadorAtual = lerContador() + 1;
  gravarContador(contadorAtual);
  inicioImersaoMs = agora;
  inicioRelogio = agoraRelogio();
  medir(agora, true);
  tMinC = tMaxC = paraCentesimos(tAtual);
  dezAvisado = false;
  char codigo[32];
  codigoDe(contadorAtual, codigo);
  Serial.print(F("Imersao iniciada: "));
  Serial.println(codigo);
  leds(true, false);
  estado = IMERSAO;
}

void fecharCiclo(unsigned long agora, const __FlashStringHelper *motivo) {
  unsigned long decorrido = agora - inicioImersaoMs;
  unsigned long segundos = decorrido / 1000UL;
  if (segundos > 32767UL) segundos = 32767UL;

  reg.estado = PENDENTE;
  reg.contador = contadorAtual;
  reg.inicio = inicioRelogio;
  reg.fim = inicioRelogio + segundos;           // fim >= inicio sempre
  reg.tMin = tMinC;
  reg.tMax = tMaxC;
  reg.segundos = (uint16_t)segundos;
  reg.aprovado = segundos >= TEMPO_MIN_S ? 1 : 0;
  assinarRegistro();                            // OR-12: assinado no momento do registro
  gravarSlot(slotAtual);                        // OR-13: vai para a fila antes de qualquer envio

  char codigo[32], ini[26], fim[26], tmin[10], tmax[10];
  codigoDe(reg.contador, codigo);
  formatarIso(reg.inicio, ini);
  formatarIso(reg.fim, fim);
  formatarTemp(reg.tMin, tmin);
  formatarTemp(reg.tMax, tmax);
  Serial.print(F("REGISTRO "));
  Serial.print(codigo);
  Serial.print(F(" | inicio "));
  Serial.print(ini);
  Serial.print(F(" | fim "));
  Serial.print(fim);
  Serial.print(F(" | min "));
  Serial.print(tmin);
  Serial.print(F(" C | max "));
  Serial.print(tmax);
  Serial.print(F(" C | "));
  Serial.print(reg.segundos);
  Serial.print(F(" s >= 80 C | "));
  Serial.print(reg.aprovado ? F("APROVADO") : F("REPROVADO"));
  Serial.print(F(" ("));
  Serial.print(motivo);
  Serial.println(F(") | salvo na fila"));

  if (reg.aprovado) {
    leds(true, false);
  } else {
    leds(false, true);
    tone(PINO_BUZZER, 400, 800);                // bip grave: reprovado
  }
  inicioResultado = agora;
  estado = RESULTADO;
}

// =====================================================================
// Envio (no ESP32 real: POST /api/ciclos por Wi-Fi, OR-16)
// =====================================================================
void imprimirEnvio() {
  char enviadoEm[26], hex[65];
  uint8_t dig[32];
  formatarIso(agoraRelogio(), enviadoEm);
  hmacInicio(CHAVE_DISPOSITIVO);
  shaTexto(ID_DISPOSITIVO);
  shaTexto("|");
  shaTexto(enviadoEm);
  hmacFim(dig);
  paraHex(dig, hex);

  Serial.println(F("=== ENVIO: copie a linha abaixo ==="));
  Serial.print(F("{\"dispositivo\":\""));
  Serial.print(ID_DISPOSITIVO);
  Serial.print(F("\",\"enviado_em\":\""));
  Serial.print(enviadoEm);
  Serial.print(F("\",\"assinatura_envio\":\""));
  Serial.print(hex);
  Serial.print(F("\",\"ciclos\":["));

  int enviados = 0;
  uint32_t ultimo = 0;
  while (enviados < MAX_POR_ENVIO) {
    int i = proximoSlot(ultimo, PENDENTE);
    if (i < 0) break;
    lerSlot(i);
    ultimo = reg.contador;
    char codigo[32], ini[26], fim[26], tmin[10], tmax[10];
    codigoDe(reg.contador, codigo);
    formatarIso(reg.inicio, ini);
    formatarIso(reg.fim, fim);
    formatarTemp(reg.tMin, tmin);
    formatarTemp(reg.tMax, tmax);
    paraHex(reg.assinatura, hex);
    if (enviados > 0) Serial.print(',');
    Serial.print(F("{\"codigo\":\""));
    Serial.print(codigo);
    Serial.print(F("\",\"contador\":"));
    Serial.print((unsigned long)reg.contador);
    Serial.print(F(",\"inicio\":\""));
    Serial.print(ini);
    Serial.print(F("\",\"fim\":\""));
    Serial.print(fim);
    Serial.print(F("\",\"temp_min\":"));
    Serial.print(tmin);
    Serial.print(F(",\"temp_max\":"));
    Serial.print(tmax);
    Serial.print(F(",\"segundos_acima_80\":"));
    Serial.print(reg.segundos);
    Serial.print(F(",\"status\":\""));
    Serial.print(reg.aprovado ? F("aprovado") : F("reprovado"));
    Serial.print(F("\",\"assinatura\":\""));
    Serial.print(hex);
    Serial.print(F("\"}"));
    enviados++;
  }
  Serial.println(F("]}"));
  Serial.println(F("=== FIM DO ENVIO ==="));
  Serial.print(enviados);
  Serial.println(F(" ciclo(s) no envio. Quando o servidor confirmar, digite 'ok todos'."));
}

// =====================================================================
// Comandos do Monitor serial
// =====================================================================
void imprimirFila() {
  int n = 0;
  uint32_t ultimo = 0;
  Serial.println(F("--- Fila local ---"));
  while (true) {
    int i = proximoSlot(ultimo, 255);
    if (i < 0) break;
    lerSlot(i);
    ultimo = reg.contador;
    char codigo[32], ini[26], tmax[10];
    codigoDe(reg.contador, codigo);
    formatarIso(reg.inicio, ini);
    formatarTemp(reg.tMax, tmax);
    Serial.print(codigo);
    Serial.print(F(" | "));
    Serial.print(ini);
    Serial.print(F(" | max "));
    Serial.print(tmax);
    Serial.print(F(" C | "));
    Serial.print(reg.segundos);
    Serial.print(F(" s | "));
    Serial.print(reg.aprovado ? F("aprovado") : F("reprovado"));
    Serial.print(F(" | "));
    Serial.print(reg.estado == PENDENTE ? F("pendente") : F("enviado"));
    Serial.print(F(" | assinatura "));
    Serial.println(registroIntegro() ? F("OK") : F("NAO CONFERE (registro alterado)"));
    n++;
  }
  if (n == 0) Serial.println(F("(vazia)"));
  Serial.print(F("Pendentes: "));
  Serial.print(contarEstado(PENDENTE));
  Serial.print(F(" | enviados: "));
  Serial.print(contarEstado(ENVIADO));
  Serial.print(F(" | livres: "));
  Serial.print(contarEstado(VAZIO));
  Serial.print(F(" | ultimo contador: "));
  Serial.println((unsigned long)lerContador());
}

// Aceita "12" ou "ORK01-000012"
long numeroDoArgumento(const char *s) {
  const char *p = strrchr(s, '-');
  if (p) s = p + 1;
  if (*s == 0) return -1;
  long v = 0;
  while (*s) {
    if (*s < '0' || *s > '9') return -1;
    v = v * 10 + (*s - '0');
    s++;
  }
  return v;
}

void marcarEnviado(const char *arg) {
  if (strcmp(arg, "todos") == 0) {
    int n = 0;
    for (int i = 0; i < nSlots; i++) {
      lerSlot(i);
      if (reg.estado == PENDENTE) {
        reg.estado = ENVIADO;
        gravarSlot(i);
        n++;
      }
    }
    Serial.print(n);
    Serial.println(F(" ciclo(s) marcados como enviados."));
    return;
  }
  long c = numeroDoArgumento(arg);
  int i = c > 0 ? slotDoContador((uint32_t)c) : -1;
  if (i < 0) {
    Serial.println(F("Ciclo nao encontrado na fila. Ex.: ok 3  ou  ok todos"));
    return;
  }
  lerSlot(i);
  reg.estado = ENVIADO;
  gravarSlot(i);
  Serial.println(F("Ciclo marcado como enviado."));
}

// Demonstração de integridade: muda o registro na memória SEM assinar de novo.
void adulterar(const char *arg) {
  long c = numeroDoArgumento(arg);
  int i = c > 0 ? slotDoContador((uint32_t)c) : -1;
  if (i < 0) {
    Serial.println(F("Ciclo nao encontrado na fila. Ex.: adulterar 2"));
    return;
  }
  lerSlot(i);
  if (!reg.aprovado) {
    reg.aprovado = 1;
    if (reg.segundos < TEMPO_MIN_S) reg.segundos = TEMPO_MIN_S;
    Serial.println(F("Registro alterado: reprovado -> aprovado (sem nova assinatura)."));
  } else {
    reg.tMax += 500;
    Serial.println(F("Registro alterado: temp_max +5 C (sem nova assinatura)."));
  }
  gravarSlot(i);
  Serial.println(F("Digite 'fila' para ver a assinatura recusada; o servidor tambem recusa."));
}

void imprimirAjuda() {
  Serial.println(F("Comandos:"));
  Serial.println(F("  fila ............. lista os ciclos guardados e confere as assinaturas"));
  Serial.println(F("  enviar ........... mostra o JSON que o ESP32 mandaria para /api/ciclos"));
  Serial.println(F("  ok todos | ok N .. marca como enviados (simula a resposta 'recebidos')"));
  Serial.println(F("  hora AAAA-MM-DD HH:MM:SS ... acerta o relogio (Belem)"));
  Serial.println(F("  adulterar N ...... altera o ciclo N sem assinar (teste de integridade)"));
  Serial.println(F("  teste ............ roda o autoteste do HMAC"));
  Serial.println(F("  zerar ............ apaga a fila e o contador (so para testes)"));
}

void processarComando() {
  cmd[cmdLen] = 0;
  cmdLen = 0;
  char *s = cmd;
  while (*s == ' ') s++;
  char *fimTxt = s + strlen(s);
  while (fimTxt > s && fimTxt[-1] == ' ') *--fimTxt = 0;
  for (char *p = s; *p && *p != ' '; p++) {
    if (*p >= 'A' && *p <= 'Z') *p += 32;
  }
  char *arg = strchr(s, ' ');
  if (arg) {
    *arg++ = 0;
    while (*arg == ' ') arg++;
  } else {
    arg = fimTxt;                                 // texto vazio
  }
  for (char *p = arg; *p; p++) {
    if (*p >= 'A' && *p <= 'Z' && strcmp(s, "hora") != 0) *p += 32;
  }

  if (*s == 0) return;
  Serial.print(F("> "));
  Serial.print(s);
  if (*arg) {
    Serial.print(' ');
    Serial.print(arg);
  }
  Serial.println();

  if (strcmp(s, "ajuda") == 0) {
    imprimirAjuda();
  } else if (strcmp(s, "fila") == 0) {
    imprimirFila();
  } else if (strcmp(s, "enviar") == 0) {
    imprimirEnvio();
  } else if (strcmp(s, "ok") == 0) {
    marcarEnviado(arg);
  } else if (strcmp(s, "hora") == 0) {
    uint32_t t;
    if (lerHora(arg, &t)) {
      acertarRelogio(t);
      char iso[26];
      formatarIso(agoraRelogio(), iso);
      Serial.print(F("Relogio acertado: "));
      Serial.println(iso);
    } else {
      Serial.println(F("Formato: hora 2026-10-22 07:30:00"));
    }
  } else if (strcmp(s, "adulterar") == 0) {
    adulterar(arg);
  } else if (strcmp(s, "teste") == 0) {
    autoteste();
  } else if (strcmp(s, "zerar") == 0) {
    if (estado == IMERSAO) {
      Serial.println(F("Termine o ciclo antes de zerar."));
    } else {
      formatarFila();
      Serial.println(F("Fila e contador zerados (so para testes: no real o contador nunca volta)."));
    }
  } else {
    Serial.println(F("Comando desconhecido. Digite 'ajuda'."));
  }
}

void lerSerial(unsigned long agora) {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (cmdLen > 0) processarComando();
      continue;
    }
    if (cmdLen < sizeof(cmd) - 1) cmd[cmdLen++] = c;
    ultimoChar = agora;
  }
  // O Monitor do Tinkercad pode mandar o texto sem quebra de linha
  if (cmdLen > 0 && agora - ultimoChar > 150) processarComando();
}

void imprimirTemperatura(unsigned long agora) {
  if (estado != PREPARANDO && estado != IMERSAO && estado != TERMOMETRO) return;
  if (agora - ultimoPrint < INTERVALO_PRINT_MS) return;
  ultimoPrint = agora;
  if (estado == IMERSAO) {
    Serial.print(F("Imersao "));
    Serial.print((agora - inicioImersaoMs) / 1000UL);
    Serial.print(F(" s | "));
  }
  Serial.print(F("Temperatura: "));
  Serial.print(tAtual, 1);
  Serial.println(F(" C"));
}

// =====================================================================
void setup() {
  Serial.begin(9600);
  pinMode(PINO_BOTAO, INPUT_PULLUP);
  pinMode(PINO_LED_VERDE, OUTPUT);
  pinMode(PINO_LED_VERMELHO, OUTPUT);
  pinMode(PINO_LED_LARANJA, OUTPUT);
  pinMode(PINO_BUZZER, OUTPUT);

  nSlots = (EEPROM.length() - INICIO_SLOTS) / TAM_SLOT;
  uint16_t marca;
  EEPROM.get(END_MARCA, marca);
  if (marca != MARCA_EEPROM) {
    formatarFila();
    Serial.println(F("Memoria preparada (primeiro uso)."));
  }

  uint32_t t;
  if (lerHora(HORA_INICIAL, &t)) acertarRelogio(t);

  Serial.print(F("Oriki "));
  Serial.print(ID_DISPOSITIVO);
  Serial.print(F(" pronto | fila: "));
  Serial.print(nSlots);
  Serial.print(F(" lugares, "));
  Serial.print(contarEstado(PENDENTE));
  Serial.print(F(" pendentes | ultimo contador: "));
  Serial.println((unsigned long)lerContador());
  if (!autoteste()) {
    Serial.println(F("ERRO: HMAC diferente do backend. Nao use este firmware."));
  }
  Serial.println(F("Toque o botao para um novo lote. Digite 'ajuda' para os comandos."));
}

void loop() {
  unsigned long agora = millis();
  lerSerial(agora);
  uint8_t ev = lerBotao(agora);

  switch (estado) {
    case OCIOSO:
      if (ev == EV_TOQUE) {
        iniciarLote(agora);
      } else if (ev == EV_SEGUROU) {
        Serial.println(F("Modo termometro (dois toques rapidos para sair)."));
        medir(agora, true);
        ultimoToque = 0;
        estado = TERMOMETRO;
      }
      break;

    case PREPARANDO:
      medir(agora, false);
      if (tAtual < LIMIAR_C) {
        leds(false, true);                      // vermelho: água fria
        prontoAvisado = false;
      } else {
        leds((agora / 250) % 2 == 0, false);    // verde piscando: pode mergulhar
        if (!prontoAvisado) {
          prontoAvisado = true;
          tone(PINO_BUZZER, 2000, 150);         // bip curto: água pronta
          Serial.println(F("Agua pronta (>= 80 C). Mergulhe o cesto e toque o botao."));
        }
      }
      if (ev == EV_TOQUE) {
        if (tAtual < LIMIAR_C) Serial.println(F("Agua abaixo de 80 C. Aguarde aquecer."));
        else iniciarImersao(agora);
      } else if (ev == EV_SEGUROU) {
        Serial.println(F("Lote cancelado (nada foi registrado)."));
        voltarOcioso();
      }
      break;

    case IMERSAO: {
      medir(agora, false);
      int16_t c = paraCentesimos(tAtual);
      if (c < tMinC) tMinC = c;
      if (c > tMaxC) tMaxC = c;
      unsigned long decorrido = agora - inicioImersaoMs;
      if (!dezAvisado && decorrido >= TEMPO_MIN_S * 1000UL) {
        dezAvisado = true;
        tone(PINO_BUZZER, 2000, 600);           // bip longo: pode tirar o cesto
        Serial.println(F("10 s acima de 80 C: pode tirar o cesto e tocar o botao."));
      }
      if (tAtual < LIMIAR_C) fecharCiclo(agora, F("agua abaixo de 80 C"));
      else if (ev == EV_TOQUE) fecharCiclo(agora, F("cesto retirado"));
      else if (decorrido >= IMERSAO_MAX_MS) fecharCiclo(agora, F("tempo maximo"));
      break;
    }

    case RESULTADO:
      if (agora - inicioResultado >= TEMPO_RESULTADO_MS) {
        voltarOcioso();
        Serial.println(F("Pronto para o proximo lote."));
      }
      break;

    case TERMOMETRO:
      medir(agora, false);
      if (alertaAlto) leds(false, false);       // laranja sozinho acima de 90 C
      else leds(tAtual >= LIMIAR_C, tAtual < LIMIAR_C);
      if (ev == EV_TOQUE) {
        if (ultimoToque != 0 && agora - ultimoToque <= JANELA_DUPLO_MS) {
          Serial.println(F("Saindo do modo termometro."));
          voltarOcioso();
        } else {
          ultimoToque = agora;
        }
      }
      break;
  }

  imprimirTemperatura(agora);
  delay(20);
}
