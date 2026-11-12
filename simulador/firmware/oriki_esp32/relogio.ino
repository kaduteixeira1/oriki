// =====================================================================
// Relógio: o RTC DS3231 guarda a hora de Belém (UTC-3, sem horário de verão).
// O servidor devolve a própria hora em cada envio e o firmware corrige o RTC
// quando a diferença passa de 2 minutos (seção 7.5).
// =====================================================================
const long FUSO_BELEM_S = -3L * 3600L;
const long TOLERANCIA_RELOGIO_S = 120;

// Segundos desde 1970 na hora local de Belém. Sem RTC, conta a partir do millis().
uint32_t relogioAgora() {
  if (rtcOk) return rtc.now().unixtime();
  return 1767225600UL + millis() / 1000UL;  // 01/01/2026: hora claramente errada, o servidor sinaliza
}

void formatarIso(uint32_t local, char *saida) {   // "2026-10-08T07:42:10-03:00" (saida: 26 posições)
  DateTime d(local);
  sprintf(saida, "%04u-%02u-%02uT%02u:%02u:%02u-03:00", d.year(), d.month(), d.day(), d.hour(), d.minute(),
          d.second());
}

String isoAgora() {
  char b[26];
  formatarIso(relogioAgora(), b);
  return String(b);
}

// "2026-10-08T10:50:02Z" -> segundos desde 1970 em UTC (0 se não entender)
uint32_t lerIsoUtc(const char *s) {
  int a, m, d, h, mi, se;
  if (sscanf(s, "%4d-%2d-%2dT%2d:%2d:%2d", &a, &m, &d, &h, &mi, &se) != 6) return 0;
  return DateTime(a, m, d, h, mi, se).unixtime();
}

// Chamada com a hora_servidor de cada resposta da API.
void conferirRelogio(const char *horaServidorUtc) {
  uint32_t utc = lerIsoUtc(horaServidorUtc);
  if (utc == 0) return;
  uint32_t localServidor = utc + FUSO_BELEM_S;
  long diferenca = (long)relogioAgora() - (long)localServidor;
  if (labs(diferenca) > TOLERANCIA_RELOGIO_S && rtcOk) {
    rtc.adjust(DateTime(localServidor));
    Serial.printf("Relogio corrigido pelo servidor (estava %+ld s fora): %s\n", diferenca, isoAgora().c_str());
  }
}

// "hora AAAA-MM-DD HH:MM:SS" no Monitor serial
bool acertarRelogioTexto(const char *s) {
  int a, m, d, h, mi, se;
  if (sscanf(s, "%4d-%2d-%2d %2d:%2d:%2d", &a, &m, &d, &h, &mi, &se) != 6) return false;
  rtc.adjust(DateTime(a, m, d, h, mi, se));
  return true;
}
