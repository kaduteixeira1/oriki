// Subconjunto do mbedtls usado para o HMAC-SHA256 no ESP32 (mbedtls_md_hmac_*).
#pragma once
#include <cstddef>
#include <cstdint>

typedef enum { MBEDTLS_MD_NONE = 0, MBEDTLS_MD_SHA256 = 6 } mbedtls_md_type_t;
struct mbedtls_md_info_t { mbedtls_md_type_t tipo; };
struct mbedtls_md_context_t {
  const mbedtls_md_info_t *info;
  void *estado;
};

const mbedtls_md_info_t *mbedtls_md_info_from_type(mbedtls_md_type_t tipo);
unsigned char mbedtls_md_get_size(const mbedtls_md_info_t *info);
void mbedtls_md_init(mbedtls_md_context_t *ctx);
void mbedtls_md_free(mbedtls_md_context_t *ctx);
int mbedtls_md_setup(mbedtls_md_context_t *ctx, const mbedtls_md_info_t *info, int hmac);
int mbedtls_md_starts(mbedtls_md_context_t *ctx);
int mbedtls_md_update(mbedtls_md_context_t *ctx, const unsigned char *dados, size_t n);
int mbedtls_md_finish(mbedtls_md_context_t *ctx, unsigned char *saida);
int mbedtls_md_hmac_starts(mbedtls_md_context_t *ctx, const unsigned char *chave, size_t n);
int mbedtls_md_hmac_update(mbedtls_md_context_t *ctx, const unsigned char *dados, size_t n);
int mbedtls_md_hmac_finish(mbedtls_md_context_t *ctx, unsigned char *saida);
int mbedtls_md_hmac_reset(mbedtls_md_context_t *ctx);
int mbedtls_md(const mbedtls_md_info_t *info, const unsigned char *dados, size_t n, unsigned char *saida);
int mbedtls_md_hmac(const mbedtls_md_info_t *info, const unsigned char *chave, size_t nchave,
                    const unsigned char *dados, size_t n, unsigned char *saida);
