// =====================================================================
// Fila local no LittleFS (OR-13, versão enxuta: sem MicroSD)
//   /pendentes/000128.json   ciclo assinado, esperando o servidor confirmar
//   /enviados/000128.json    confirmado em "recebidos" (guarda os 200 últimos)
//   /recusados/000128.json   veio em "recusados": não é reenviado em loop (seção 7.5)
// O contador fica na NVS (Preferences) e é reservado no início da imersão: nunca volta.
// =====================================================================
const int GUARDAR_ENVIADOS = 200;

void filaPreparar() {
  LittleFS.mkdir("/pendentes");
  LittleFS.mkdir("/enviados");
  LittleFS.mkdir("/recusados");
  nvs.begin("oriki", false);
}

uint32_t contadorAtual() { return nvs.getUInt("contador", 0); }

uint32_t reservarContador() {
  uint32_t c = contadorAtual() + 1;
  nvs.putUInt("contador", c);
  return c;
}

String caminhoFila(const char *pasta, uint32_t contador) {
  char b[40];
  sprintf(b, "%s/%06lu.json", pasta, (unsigned long)contador);
  return String(b);
}

uint32_t contadorDoNome(const char *nome) {
  const char *p = strrchr(nome, '/');
  return (uint32_t)strtoul(p ? p + 1 : nome, nullptr, 10);
}

// Assina na hora e grava antes de qualquer envio (o registro não depende de internet).
bool registrarCiclo(uint32_t contador, uint32_t inicio, uint32_t fim, int16_t tMin, int16_t tMax, uint16_t segundos,
                    bool aprovado) {
  char ini[26], fi[26], tmin[10], tmax[10], codigo[32], msg[200], assinatura[65];
  formatarIso(inicio, ini);
  formatarIso(fim, fi);
  formatarTemp(tMin, tmin);
  formatarTemp(tMax, tmax);
  codigoDe(contador, codigo);
  mensagemCiclo(contador, ini, fi, tMin, tMax, segundos, aprovado, msg, sizeof msg);
  hmacHex(CHAVE_DISPOSITIVO, msg, assinatura);

  File f = LittleFS.open(caminhoFila("/pendentes", contador), "w");
  if (!f) {
    Serial.println("ERRO: nao consegui gravar o ciclo no LittleFS.");
    return false;
  }
  f.printf("{\"codigo\":\"%s\",\"contador\":%lu,\"inicio\":\"%s\",\"fim\":\"%s\",\"temp_min\":%s,\"temp_max\":%s,"
           "\"segundos_acima_80\":%u,\"status\":\"%s\",\"assinatura\":\"%s\"}",
           codigo, (unsigned long)contador, ini, fi, tmin, tmax, segundos, aprovado ? "aprovado" : "reprovado",
           assinatura);
  f.close();
  return true;
}

int filaContar(const char *pasta) {
  File dir = LittleFS.open(pasta);
  if (!dir || !dir.isDirectory()) return 0;
  int n = 0;
  for (File f = dir.openNextFile(); f; f = dir.openNextFile()) n++;
  return n;
}

// Os `max` menores contadores da pasta, em ordem (o LittleFS não garante a ordem dos arquivos).
int filaMenores(const char *pasta, uint32_t *saida, int max) {
  File dir = LittleFS.open(pasta);
  if (!dir || !dir.isDirectory()) return 0;
  int n = 0;
  for (File f = dir.openNextFile(); f; f = dir.openNextFile()) {
    uint32_t c = contadorDoNome(f.name());
    if (c == 0) continue;
    int i = n < max ? n++ : max;
    if (i == max && c >= saida[max - 1]) continue;
    if (i == max) i = max - 1;
    while (i > 0 && saida[i - 1] > c) {
      saida[i] = saida[i - 1];
      i--;
    }
    saida[i] = c;
  }
  return n;
}

String filaLer(const char *pasta, uint32_t contador) {
  File f = LittleFS.open(caminhoFila(pasta, contador), "r");
  if (!f) return String();
  String s = f.readString();
  f.close();
  return s;
}

bool filaMover(uint32_t contador, const char *de, const char *para) {
  bool ok = LittleFS.rename(caminhoFila(de, contador), caminhoFila(para, contador));
  if (ok && strcmp(para, "/enviados") == 0 && filaContar("/enviados") > GUARDAR_ENVIADOS) {
    uint32_t velho[1];
    if (filaMenores("/enviados", velho, 1)) LittleFS.remove(caminhoFila("/enviados", velho[0]));
  }
  return ok;
}

// Teste de integridade (OR-25): muda o ciclo na memória SEM assinar de novo. O servidor tem de recusar.
void filaAdulterar(uint32_t contador) {
  String s = filaLer("/pendentes", contador);
  if (s.length() == 0) {
    Serial.println("Ciclo nao esta entre os pendentes. Ex.: adulterar 3");
    return;
  }
  // Troca o número de segundos (e, se reprovado, o status) mantendo o formato válido.
  const String campo = "\"segundos_acima_80\":";
  int p = s.indexOf(campo) + campo.length();
  int q = p;
  while (q < (int)s.length() && isdigit(s[q])) q++;
  long segundos = s.substring(p, q).toInt();
  if (s.indexOf("\"reprovado\"") >= 0) {
    s.replace("\"reprovado\"", "\"aprovado\"");
    if (segundos < 10) segundos = 12;
    Serial.println("Registro alterado: reprovado -> aprovado (sem nova assinatura).");
  } else {
    segundos += 5;
    Serial.println("Registro alterado: +5 s acima de 80 C (sem nova assinatura).");
  }
  s = s.substring(0, p) + String(segundos) + s.substring(q);
  File f = LittleFS.open(caminhoFila("/pendentes", contador), "w");
  f.print(s);
  f.close();
  Serial.println("No proximo envio o servidor deve responder assinatura_invalida.");
}

void filaZerar() {
  LittleFS.format();
  filaPreparar();
  nvs.putUInt("contador", 0);
}
