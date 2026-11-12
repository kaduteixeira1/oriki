// =====================================================================
// Oriki - bancada do sensor (OR-14): ESP32 + DS18B20 real
// Teste "Precisão do sensor": diferença média <= 1 C em 20 medições,
// comparando com um termômetro de referência.
//
// IDE do Arduino
//   Placa: "ESP32 Dev Module" (pacote esp32 da Espressif)
//   Bibliotecas: OneWire (Paul Stoffregen) e DallasTemperature (Miles Burton)
//   Monitor serial: 115200, final de linha "Nova linha"
//
// Ligação do DS18B20 à prova d'água
//   vermelho -> 3V3 | preto -> GND | amarelo (dados) -> GPIO 4
//   resistor de 4,7 kOhm entre o amarelo e o 3V3 (sem ele o sensor não responde)
//
// Comandos no Monitor serial
//   r 82.4 ...... registra uma medição: 82.4 é o que o termômetro de referência mostra
//   lista ....... mostra as medições em CSV (para colar na planilha)
//   resultado ... média das diferenças, maior diferença e a correção sugerida
//   desfazer .... apaga a última medição
//   limpar ...... apaga todas
// =====================================================================

#include <OneWire.h>
#include <DallasTemperature.h>

const int PINO_DADOS = 4;
const int MAX_MEDICOES = 30;
const int MEDIA_DE = 5;               // média das últimas 5 leituras (1 por segundo)
const float META_C = 1.0;

OneWire umFio(PINO_DADOS);
DallasTemperature sensores(&umFio);

float ultimas[MEDIA_DE];
int nUltimas = 0, posUltimas = 0;
float refs[MAX_MEDICOES], lidas[MAX_MEDICOES];
int nMedicoes = 0;
unsigned long ultimaLeitura = 0;
char linha[40];
int tamLinha = 0;

float mediaAtual() {
  if (nUltimas == 0) return NAN;
  float s = 0;
  for (int i = 0; i < nUltimas; i++) s += ultimas[i];
  return s / nUltimas;
}

void lerSensor() {
  sensores.requestTemperatures();              // 12 bits: ~750 ms por leitura
  float t = sensores.getTempCByIndex(0);
  if (t == DEVICE_DISCONNECTED_C) {
    Serial.println("Sensor nao encontrado: confira o fio amarelo no GPIO 4 e o resistor de 4,7 kOhm.");
    return;
  }
  ultimas[posUltimas] = t;
  posUltimas = (posUltimas + 1) % MEDIA_DE;
  if (nUltimas < MEDIA_DE) nUltimas++;
  Serial.print("Sensor: ");
  Serial.print(t, 2);
  Serial.print(" C | media 5 s: ");
  Serial.print(mediaAtual(), 2);
  Serial.println(" C");
}

void registrar(const char *arg) {
  float ref = atof(arg);
  if (*arg == 0 || ref < -10 || ref > 110) {
    Serial.println("Uso: r 82.4  (temperatura do termometro de referencia)");
    return;
  }
  if (nUltimas < MEDIA_DE) {
    Serial.println("Aguarde 5 leituras do sensor antes de registrar.");
    return;
  }
  if (nMedicoes >= MAX_MEDICOES) {
    Serial.println("Limite de medicoes atingido. Use 'resultado' ou 'limpar'.");
    return;
  }
  refs[nMedicoes] = ref;
  lidas[nMedicoes] = mediaAtual();
  nMedicoes++;
  Serial.print("Medicao ");
  Serial.print(nMedicoes);
  Serial.print(": referencia ");
  Serial.print(ref, 2);
  Serial.print(" C | sensor ");
  Serial.print(lidas[nMedicoes - 1], 2);
  Serial.print(" C | diferenca ");
  Serial.print(lidas[nMedicoes - 1] - ref, 2);
  Serial.println(" C");
}

void listar() {
  Serial.println("n;referencia_C;sensor_C;diferenca_C");
  for (int i = 0; i < nMedicoes; i++) {
    Serial.print(i + 1);
    Serial.print(';');
    Serial.print(refs[i], 2);
    Serial.print(';');
    Serial.print(lidas[i], 2);
    Serial.print(';');
    Serial.println(lidas[i] - refs[i], 2);
  }
}

void resultado() {
  if (nMedicoes == 0) {
    Serial.println("Nenhuma medicao registrada.");
    return;
  }
  float somaDif = 0, somaAbs = 0, maior = 0;
  for (int i = 0; i < nMedicoes; i++) {
    float d = lidas[i] - refs[i];
    somaDif += d;
    somaAbs += fabs(d);
    if (fabs(d) > maior) maior = fabs(d);
  }
  float vies = somaDif / nMedicoes;
  float mediaAbs = somaAbs / nMedicoes;
  float somaAbsCorrigida = 0;
  for (int i = 0; i < nMedicoes; i++) somaAbsCorrigida += fabs(lidas[i] - vies - refs[i]);

  Serial.println("--- Resultado da bancada ---");
  Serial.print("Medicoes: ");
  Serial.print(nMedicoes);
  Serial.println(nMedicoes < 20 ? " (a meta pede 20)" : "");
  Serial.print("Diferenca media (sem correcao): ");
  Serial.print(mediaAbs, 2);
  Serial.print(" C -> meta de ");
  Serial.print(META_C, 1);
  Serial.println(mediaAbs <= META_C ? " C ATINGIDA" : " C NAO atingida");
  Serial.print("Maior diferenca: ");
  Serial.print(maior, 2);
  Serial.println(" C");
  Serial.print("Vies medio (sensor - referencia): ");
  Serial.print(vies, 2);
  Serial.println(" C");
  Serial.print("Correcao sugerida para CALIBRACAO_C no firmware: ");
  Serial.print(-vies, 2);
  Serial.println(" C");
  Serial.print("Diferenca media com a correcao: ");
  Serial.print(somaAbsCorrigida / nMedicoes, 2);
  Serial.println(" C");
}

void processar() {
  linha[tamLinha] = 0;
  tamLinha = 0;
  char *s = linha;
  while (*s == ' ') s++;
  if (*s == 0) return;
  if ((s[0] == 'r' || s[0] == 'R') && (s[1] == ' ' || s[1] == 0)) {
    registrar(s[1] ? s + 2 : s + 1);
  } else if (strcmp(s, "lista") == 0) {
    listar();
  } else if (strcmp(s, "resultado") == 0) {
    resultado();
  } else if (strcmp(s, "desfazer") == 0) {
    if (nMedicoes > 0) nMedicoes--;
    Serial.print("Medicoes: ");
    Serial.println(nMedicoes);
  } else if (strcmp(s, "limpar") == 0) {
    nMedicoes = 0;
    Serial.println("Medicoes apagadas.");
  } else {
    Serial.println("Comandos: r <referencia> | lista | resultado | desfazer | limpar");
  }
}

void setup() {
  Serial.begin(115200);
  sensores.begin();
  sensores.setResolution(12);
  Serial.print("Sensores DS18B20 encontrados: ");
  Serial.println(sensores.getDeviceCount());
  Serial.println("Coloque o sensor e o termometro de referencia juntos na agua, espere estabilizar");
  Serial.println("e digite: r <temperatura da referencia>. Ex.: r 82.4");
}

void loop() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (tamLinha > 0) processar();
    } else if (tamLinha < (int)sizeof(linha) - 1) {
      linha[tamLinha++] = c;
    }
  }
  if (millis() - ultimaLeitura >= 1000) {
    ultimaLeitura = millis();
    lerSensor();
  }
}
