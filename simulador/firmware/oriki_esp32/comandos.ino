// =====================================================================
// Monitor serial (115200): os mesmos comandos do oriki_tinkercad.ino
// =====================================================================
char cmd[64];
uint8_t cmdLen = 0;

void imprimirAjuda() {
  Serial.println("Comandos:");
  Serial.println("  fila ............. pendentes, enviados e recusados");
  Serial.println("  enviar ........... tenta o envio agora (sem esperar os 5 min)");
  Serial.println("  adulterar N ...... altera o ciclo N sem assinar (teste de integridade)");
  Serial.println("  hora AAAA-MM-DD HH:MM:SS ... acerta o RTC (Belem)");
  Serial.println("  wifi ............. estado da conexao");
  Serial.println("  teste ............ autoteste do HMAC");
  Serial.println("  zerar ............ apaga a fila e o contador (so para testes)");
}

void imprimirFila() {
  Serial.printf("Pendentes: %d | enviados (guardados): %d | recusados: %d | ultimo contador: %lu\n",
                filaContar("/pendentes"), filaContar("/enviados"), filaContar("/recusados"),
                (unsigned long)contadorAtual());
  uint32_t lista[10];
  int n = filaMenores("/pendentes", lista, 10);
  for (int i = 0; i < n && i < 10; i++) Serial.println("  " + filaLer("/pendentes", lista[i]));
  if (n > 10) Serial.printf("  ... e mais %d\n", n - 10);
}

void processarComando() {
  cmd[cmdLen] = 0;
  cmdLen = 0;
  String c = String(cmd);
  c.trim();
  if (c.length() == 0) return;
  Serial.print("> ");
  Serial.println(c);
  if (c == "ajuda") imprimirAjuda();
  else if (c == "fila") imprimirFila();
  else if (c == "enviar") enviarAgora();
  else if (c == "teste") autoteste();
  else if (c == "wifi") Serial.printf("Wi-Fi: %s | IP %s\n", WiFi.isConnected() ? "conectado" : "desconectado",
                                       WiFi.localIP().toString().c_str());
  else if (c.startsWith("adulterar ")) filaAdulterar((uint32_t)c.substring(10).toInt());
  else if (c.startsWith("hora ")) {
    if (acertarRelogioTexto(c.substring(5).c_str())) Serial.println("Relogio acertado: " + isoAgora());
    else Serial.println("Formato: hora 2026-11-05 07:30:00");
  } else if (c == "zerar") {
    if (cicloEmAndamento()) Serial.println("Termine o ciclo antes de zerar.");
    else {
      filaZerar();
      Serial.println("Fila e contador zerados (so para testes: no real o contador nunca volta).");
    }
  } else {
    Serial.println("Comando desconhecido. Digite 'ajuda'.");
  }
}

void lerSerial(unsigned long) {
  while (Serial.available() > 0) {
    char ch = (char)Serial.read();
    if (ch == '\n' || ch == '\r') {
      if (cmdLen > 0) processarComando();
      continue;
    }
    if (cmdLen < sizeof(cmd) - 1) cmd[cmdLen++] = ch;
  }
}
