// =====================================================================
// Envio para a API (OR-16/OR-39, seção 7 do plano)
//   - a cada 5 min (e 10 s depois de cada ciclo), se houver Wi-Fi;
//   - até 50 pendentes por vez; lista vazia funciona como heartbeat;
//   - só marca como enviado o que voltar em "recebidos";
//   - corrige o RTC com a "hora_servidor" da resposta.
// O Wi-Fi é configurado uma vez pelo portal "Oriki-Config" (WiFiManager).
// =====================================================================
unsigned long proximoEnvio = 0;
unsigned long ultimoAvisoSemWifi = 0;

void envioSetup() {
  WiFi.mode(WIFI_STA);
  WiFiManager wm;
  wm.setConfigPortalTimeout(120);   // sem configurar em 2 min, segue sem Wi-Fi (a fila guarda tudo)
  if (wm.autoConnect("Oriki-Config")) {
    Serial.print("Wi-Fi conectado: ");
    Serial.println(WiFi.localIP().toString());
  } else {
    Serial.println("Sem Wi-Fi por enquanto: os ciclos ficam na fila e sobem quando a rede voltar.");
  }
  WiFi.setAutoReconnect(true);
  proximoEnvio = millis() + 3000;
}

void envioAgendar(unsigned long daquiMs) {
  unsigned long alvo = millis() + daquiMs;
  if ((long)(alvo - proximoEnvio) < 0) proximoEnvio = alvo;
}

void envioLoop(unsigned long agora) {
  // A rede voltou com ciclos na fila: envia em 2 s, sem esperar o próximo intervalo de 5 min.
  static bool estavaConectado = false;
  bool conectado = WiFi.status() == WL_CONNECTED;
  if (conectado && !estavaConectado && filaContar("/pendentes") > 0) {
    Serial.println("Wi-Fi de volta: enviando a fila.");
    envioAgendar(2000);
  }
  estavaConectado = conectado;
  if (cicloEmAndamento()) return;             // o HTTP trava o loop: nunca no meio da imersão
  if ((long)(agora - proximoEnvio) < 0) return;
  proximoEnvio = agora + INTERVALO_ENVIO_MS;
  enviarAgora();
}

// Próximo "texto" entre aspas a partir de `de`; devolve a posição depois dele (ou -1).
int proximoTexto(const String &s, int de, int ate, String &saida) {
  int a = s.indexOf('"', de);
  if (a < 0 || a >= ate) return -1;
  int b = s.indexOf('"', a + 1);
  if (b < 0 || b > ate) return -1;
  saida = s.substring(a + 1, b);
  return b + 1;
}

String campoTexto(const String &s, const char *nome, int de = 0, int ate = -1) {
  String chave = String("\"") + nome + "\":\"";
  int p = s.indexOf(chave, de);
  if (p < 0 || (ate >= 0 && p > ate)) return String();
  p += chave.length();
  return s.substring(p, s.indexOf('"', p));
}

void tratarResposta(const String &r, int enviados) {
  int nRecebidos = 0, nRecusados = 0;
  int ini = r.indexOf("\"recebidos\":[");
  if (ini >= 0) {
    int fim = r.indexOf(']', ini);
    String codigo;
    for (int p = ini + 12; (p = proximoTexto(r, p, fim, codigo)) > 0;) {
      if (filaMover(contadorDoNome(codigo.substring(codigo.lastIndexOf('-') + 1).c_str()), "/pendentes", "/enviados"))
        nRecebidos++;
    }
  }
  ini = r.indexOf("\"recusados\":[");
  if (ini >= 0) {
    int fim = r.indexOf(']', ini);
    for (int p = r.indexOf('{', ini); p >= 0 && p < fim; p = r.indexOf('{', p + 1)) {
      int fecha = r.indexOf('}', p);
      String codigo = campoTexto(r, "codigo", p, fecha);
      String motivo = campoTexto(r, "motivo", p, fecha);
      Serial.printf("RECUSADO pelo servidor: %s (%s)\n", codigo.c_str(), motivo.c_str());
      if (codigo.length()) filaMover(contadorDoNome(codigo.substring(codigo.lastIndexOf('-') + 1).c_str()),
                                     "/pendentes", "/recusados");
      nRecusados++;
    }
  }
  String hora = campoTexto(r, "hora_servidor");
  if (hora.length()) conferirRelogio(hora.c_str());
  Serial.printf("Envio: %d ciclo(s) | %d recebidos | %d recusados | %d ainda pendentes\n", enviados, nRecebidos,
                nRecusados, filaContar("/pendentes"));
  if (nRecusados) bip(300);
}

void enviarAgora() {
  int pendentes = filaContar("/pendentes");
  if (WiFi.status() != WL_CONNECTED) {
    WiFi.reconnect();
    if (millis() - ultimoAvisoSemWifi > 60000UL || ultimoAvisoSemWifi == 0) {
      ultimoAvisoSemWifi = millis();
      Serial.printf("Sem Wi-Fi: %d ciclo(s) seguem na fila.\n", pendentes);
    }
    return;
  }

  static uint32_t lote[MAX_POR_ENVIO];
  int n = filaMenores("/pendentes", lote, MAX_POR_ENVIO);
  if (n > MAX_POR_ENVIO) n = MAX_POR_ENVIO;

  char enviadoEm[26], assinatura[65], msg[64];
  formatarIso(relogioAgora(), enviadoEm);
  snprintf(msg, sizeof msg, "%s|%s", ID_DISPOSITIVO, enviadoEm);
  hmacHex(CHAVE_DISPOSITIVO, msg, assinatura);

  String corpo;
  corpo.reserve(120 + n * 330);
  corpo += "{\"dispositivo\":\"";
  corpo += ID_DISPOSITIVO;
  corpo += "\",\"enviado_em\":\"";
  corpo += enviadoEm;
  corpo += "\",\"assinatura_envio\":\"";
  corpo += assinatura;
  corpo += "\",\"ciclos\":[";
  for (int i = 0; i < n; i++) {
    if (i) corpo += ",";
    corpo += filaLer("/pendentes", lote[i]);
  }
  corpo += "]}";

  WiFiClientSecure tls;
  if (strlen(CA_RAIZ) > 0) tls.setCACert(CA_RAIZ);
  else tls.setInsecure();               // só na bancada: grave o CA_RAIZ antes de ir para o tanque
  HTTPClient http;
  http.setTimeout(10000);
  http.begin(tls, URL_API);
  http.addHeader("Content-Type", "application/json");
  int status = http.POST(corpo);
  String resposta = http.getString();
  http.end();

  if (status == 200) {
    tratarResposta(resposta, n);
    if (filaContar("/pendentes") > 0 && n == MAX_POR_ENVIO) envioAgendar(2000);   // ainda tem mais
  } else if (status == 401) {
    Serial.println("Envio recusado (401): identificador ou chave do dispositivo nao conferem com o servidor.");
  } else if (status == 429) {
    Serial.println("Servidor pediu para esperar (429). Tento de novo no proximo intervalo.");
  } else if (status < 0) {
    Serial.printf("Falha de rede no envio (%s). Os ciclos seguem na fila.\n", HTTPClient::errorToString(status).c_str());
  } else {
    Serial.printf("Envio falhou: HTTP %d %s\n", status, resposta.c_str());
  }
}
