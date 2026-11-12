// =====================================================================
// Assinatura HMAC-SHA256 (OR-12, seção 7.2 do plano)
// Chave: o texto de 64 caracteres usado como bytes ASCII. Saída em hex minúsculo.
// =====================================================================

void paraHex(const uint8_t *bytes, char *saida) {   // saida precisa de 65 posições
  static const char dig[] = "0123456789abcdef";
  for (int i = 0; i < 32; i++) {
    saida[2 * i] = dig[bytes[i] >> 4];
    saida[2 * i + 1] = dig[bytes[i] & 0x0F];
  }
  saida[64] = 0;
}

void hmacHex(const char *chave, const char *mensagem, char *saidaHex) {
  uint8_t dig[32];
  mbedtls_md_context_t ctx;
  mbedtls_md_init(&ctx);
  mbedtls_md_setup(&ctx, mbedtls_md_info_from_type(MBEDTLS_MD_SHA256), 1);
  mbedtls_md_hmac_starts(&ctx, (const unsigned char *)chave, strlen(chave));
  mbedtls_md_hmac_update(&ctx, (const unsigned char *)mensagem, strlen(mensagem));
  mbedtls_md_hmac_finish(&ctx, dig);
  mbedtls_md_free(&ctx);
  paraHex(dig, saidaHex);
}

// "81.20", "-0.05": duas casas e ponto, a partir de centésimos (sem erro de arredondamento do float)
void formatarTemp(int16_t c, char *saida) {
  int v = c < 0 ? -c : c;
  sprintf(saida, "%s%d.%02d", c < 0 ? "-" : "", v / 100, v % 100);
}

void codigoDe(uint32_t contador, char *saida) {   // "ORK01-000128"
  sprintf(saida, "%s-%06lu", ID_DISPOSITIVO, (unsigned long)contador);
}

// codigo|contador|inicio|fim|temp_min|temp_max|segundos_acima_80|status
void mensagemCiclo(uint32_t contador, const char *inicio, const char *fim, int16_t tMin, int16_t tMax,
                   uint16_t segundos, bool aprovado, char *saida, size_t tamanho) {
  char codigo[32], tmin[10], tmax[10];
  codigoDe(contador, codigo);
  formatarTemp(tMin, tmin);
  formatarTemp(tMax, tmax);
  snprintf(saida, tamanho, "%s|%lu|%s|%s|%s|%s|%u|%s", codigo, (unsigned long)contador, inicio, fim, tmin, tmax,
           segundos, aprovado ? "aprovado" : "reprovado");
}

// Vetores de teste da seção 7.2 (chave "chave-de-teste"): firmware e backend precisam bater.
bool autoteste() {
  char hex[65];
  hmacHex("chave-de-teste", "ORK01|2026-10-08T07:50:00-03:00", hex);
  bool envio = strcmp(hex, "74a7b50b829144a0b5e44210049c7b8ba941e9b1b927f8da2f8bc9aab33a2c71") == 0;
  hmacHex("chave-de-teste",
          "ORK01-000128|128|2026-10-08T07:42:10-03:00|2026-10-08T07:42:24-03:00|81.20|84.60|12|aprovado", hex);
  bool ciclo = strcmp(hex, "d7d02435af15a3b257a765d3e90b17687d780a7620d70b3c76350b9ff8f9d24d") == 0;
  Serial.printf("Autoteste HMAC (vetores da secao 7.2): envio %s | ciclo %s\n", envio ? "OK" : "FALHOU",
                ciclo ? "OK" : "FALHOU");
  return envio && ciclo;
}
