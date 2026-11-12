// Implementação das bibliotecas de mentira (EEPROM, LittleFS, Preferences, mbedtls, ESP, hora).
#include "Arduino.h"
#include "EEPROM.h"
#include "SPI.h"
#include "Wire.h"
#include "sim.h"
#include "LittleFS.h"
#include "SPIFFS.h"

#include <fstream>
#include <functional>
#include <algorithm>
#include <sstream>
#include <vector>
#include <cstdio>
#include <sys/stat.h>
#ifdef _WIN32
#include <direct.h>
#include <io.h>
#define rmdir_ _rmdir
#else
#include <dirent.h>
#include <unistd.h>
#define rmdir_ ::rmdir
#endif

SPIClass SPI;
TwoWire Wire;

// =====================================================================
// EEPROM
// =====================================================================
EEPROMClass EEPROM;

void EEPROMClass::preparar() {
  if (pronto_) return;
  pronto_ = true;
#ifdef ORIKI_PLACA_UNO
  if (dados_.empty()) dados_.assign(1024, 0xFF);
#else
  if (dados_.empty()) dados_.assign(512, 0xFF);
#endif
  std::ifstream f(sim::caminhoDados("eeprom.bin"), std::ios::binary);
  std::vector<uint8_t> lido((std::istreambuf_iterator<char>(f)), std::istreambuf_iterator<char>());
  for (size_t i = 0; i < lido.size() && i < dados_.size(); i++) dados_[i] = lido[i];
}
bool EEPROMClass::begin(size_t tamanho) {
  if (!pronto_) dados_.assign(tamanho, 0xFF);
  else dados_.resize(tamanho, 0xFF);
  preparar();
  return true;
}
bool EEPROMClass::commit() {
  preparar();
  std::ofstream f(sim::caminhoDados("eeprom.bin"), std::ios::binary | std::ios::trunc);
  f.write((const char *)dados_.data(), (std::streamsize)dados_.size());
  return (bool)f;
}
uint8_t EEPROMClass::read(int e) {
  preparar();
  return e >= 0 && (size_t)e < dados_.size() ? dados_[e] : 0xFF;
}
void EEPROMClass::write(int e, uint8_t v) {
  preparar();
  if (e < 0 || (size_t)e >= dados_.size()) return;
  dados_[e] = v;
  if (gravarNaHora_) commit();
}
uint16_t EEPROMClass::length() {
  preparar();
  return (uint16_t)dados_.size();
}

// =====================================================================
// LittleFS / SPIFFS
// =====================================================================
fs::FS LittleFS("littlefs");
fs::FS SPIFFS("spiffs");

static bool ehPasta(const std::string &p) {
  struct stat s;
  return stat(p.c_str(), &s) == 0 && (s.st_mode & S_IFDIR);
}
static bool existe(const std::string &p) {
  struct stat s;
  return stat(p.c_str(), &s) == 0;
}
static std::vector<std::string> listar(const std::string &pasta) {
  std::vector<std::string> nomes;
#ifdef _WIN32
  struct _finddata_t d;
  intptr_t h = _findfirst((pasta + "/*").c_str(), &d);
  if (h != -1) {
    do {
      std::string n = d.name;
      if (n != "." && n != "..") nomes.push_back(n);
    } while (_findnext(h, &d) == 0);
    _findclose(h);
  }
#else
  if (DIR *dir = opendir(pasta.c_str())) {
    while (dirent *e = readdir(dir)) {
      std::string n = e->d_name;
      if (n != "." && n != "..") nomes.push_back(n);
    }
    closedir(dir);
  }
#endif
  std::sort(nomes.begin(), nomes.end());
  return nomes;
}

namespace fs {
File::File(const std::string &real, const std::string &nome, const char *modo) {
  estado_ = std::make_shared<Estado>();
  estado_->real = real;
  estado_->nome = nome;
  if (ehPasta(real)) {
    estado_->pasta = true;
    return;
  }
  std::string m = modo ? modo : "r";
  const char *modoC = m == "w" ? "wb+" : m == "a" ? "ab+" : m == "r+" ? "rb+" : m == "w+" ? "wb+" : m == "a+" ? "ab+" : "rb";
  estado_->arquivo = std::fopen(real.c_str(), modoC);
}
File::~File() {}
size_t File::write(uint8_t c) { return write(&c, 1); }
size_t File::write(const uint8_t *buf, size_t n) {
  if (!estado_ || !estado_->arquivo) return 0;
  return std::fwrite(buf, 1, n, estado_->arquivo);
}
int File::available() {
  if (!estado_ || !estado_->arquivo) return 0;
  long atual = std::ftell(estado_->arquivo);
  return (int)(size() - (size_t)atual);
}
int File::read() {
  if (!estado_ || !estado_->arquivo) return -1;
  int c = std::fgetc(estado_->arquivo);
  return c == EOF ? -1 : c;
}
int File::peek() {
  int c = read();
  if (c >= 0) std::fseek(estado_->arquivo, -1, SEEK_CUR);
  return c;
}
size_t File::read(uint8_t *buf, size_t n) {
  if (!estado_ || !estado_->arquivo) return 0;
  return std::fread(buf, 1, n, estado_->arquivo);
}
void File::flush() { if (estado_ && estado_->arquivo) std::fflush(estado_->arquivo); }
bool File::seek(uint32_t pos, SeekMode modo) {
  if (!estado_ || !estado_->arquivo) return false;
  return std::fseek(estado_->arquivo, (long)pos, modo == SeekSet ? SEEK_SET : modo == SeekCur ? SEEK_CUR : SEEK_END) == 0;
}
size_t File::position() const { return estado_ && estado_->arquivo ? (size_t)std::ftell(estado_->arquivo) : 0; }
size_t File::size() const {
  if (!estado_ || !estado_->arquivo) return 0;
  std::fflush(estado_->arquivo);
  struct stat s;
  return stat(estado_->real.c_str(), &s) == 0 ? (size_t)s.st_size : 0;
}
void File::close() {
  if (estado_ && estado_->arquivo) {
    std::fclose(estado_->arquivo);
    estado_->arquivo = nullptr;
  }
  estado_.reset();
}
const char *File::name() const {
  if (!estado_) return "";
  size_t b = estado_->nome.rfind('/');
  return b == std::string::npos ? estado_->nome.c_str() : estado_->nome.c_str() + b + 1;
}
File File::openNextFile(const char *modo) {
  if (!estado_ || !estado_->pasta) return File();
  auto nomes = listar(estado_->real);
  if (estado_->proximo >= nomes.size()) return File();
  std::string n = nomes[estado_->proximo++];
  std::string nome = estado_->nome == "/" ? "/" + n : estado_->nome + "/" + n;
  return File(estado_->real + "/" + n, nome, modo);
}

std::string FS::real(const char *caminho) {
  std::string c = caminho ? caminho : "/";
  while (!c.empty() && c[0] == '/') c.erase(0, 1);
  std::string base = sim::pastaDados() + "/" + pasta_;
  sim::criarPastas(base);
  return c.empty() ? base : base + "/" + c;
}
bool FS::begin(bool, const char *, uint8_t, const char *) {
  real("/");
  return true;
}
bool FS::format() {
  std::function<void(const std::string &)> apagar = [&](const std::string &p) {
    for (auto &n : listar(p)) {
      std::string f = p + "/" + n;
      if (ehPasta(f)) {
        apagar(f);
        rmdir_(f.c_str());
      } else {
        std::remove(f.c_str());
      }
    }
  };
  apagar(real("/"));
  return true;
}
File FS::open(const char *caminho, const char *modo, bool) {
  std::string r = real(caminho);
  std::string m = modo ? modo : "r";
  if (m == "r" && !existe(r)) return File();
  if (m != "r") {
    size_t b = r.rfind('/');
    if (b != std::string::npos) sim::criarPastas(r.substr(0, b));
  }
  return File(r, caminho && *caminho ? caminho : "/", modo);
}
bool FS::exists(const char *c) { return existe(real(c)); }
bool FS::remove(const char *c) { return std::remove(real(c).c_str()) == 0; }
bool FS::rename(const char *de, const char *para) {
  std::string destino = real(para);
  std::remove(destino.c_str());  // no Windows o rename não sobrescreve
  return std::rename(real(de).c_str(), destino.c_str()) == 0;
}
bool FS::mkdir(const char *c) {
  sim::criarPastas(real(c));
  return true;
}
bool FS::rmdir(const char *c) { return rmdir_(real(c).c_str()) == 0; }
size_t FS::usedBytes() {
  size_t total = 0;
  std::function<void(const std::string &)> somar = [&](const std::string &p) {
    for (auto &n : listar(p)) {
      std::string f = p + "/" + n;
      struct stat s;
      if (ehPasta(f)) somar(f);
      else if (stat(f.c_str(), &s) == 0) total += (size_t)s.st_size;
    }
  };
  somar(real("/"));
  return total;
}
}  // namespace fs

// =====================================================================
// Preferences
// =====================================================================
#include "Preferences.h"

bool Preferences::begin(const char *nome, bool somenteLeitura, const char *) {
  nome_ = nome ? nome : "padrao";
  somenteLeitura_ = somenteLeitura;
  valores_.clear();
  std::ifstream f(sim::caminhoDados("nvs/" + nome_ + ".txt"));
  std::string linha;
  while (std::getline(f, linha)) {
    size_t igual = linha.find('=');
    if (igual != std::string::npos) valores_[linha.substr(0, igual)] = linha.substr(igual + 1);
  }
  return true;
}
size_t Preferences::guardar(const char *k, const std::string &v) {
  if (somenteLeitura_ || nome_.empty()) return 0;
  valores_[k] = v;
  gravar();
  return v.size() ? v.size() : 1;
}
bool Preferences::gravar() {
  if (somenteLeitura_ || nome_.empty()) return false;
  std::ofstream f(sim::caminhoDados("nvs/" + nome_ + ".txt"), std::ios::trunc);
  for (auto &kv : valores_) f << kv.first << "=" << kv.second << "\n";
  return true;
}

// =====================================================================
// SHA-256 e HMAC (mbedtls_md_*)
// =====================================================================
#include "mbedtls/md.h"

namespace {
const uint32_t K[64] = {
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2};

struct Sha256 {
  uint32_t h[8];
  uint8_t bloco[64];
  size_t n = 0;
  uint64_t total = 0;
  void iniciar() {
    const uint32_t i[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
    memcpy(h, i, sizeof h);
    n = 0;
    total = 0;
  }
  static uint32_t r(uint32_t x, int k) { return (x >> k) | (x << (32 - k)); }
  void processar() {
    uint32_t w[64];
    for (int i = 0; i < 16; i++)
      w[i] = (uint32_t)bloco[i * 4] << 24 | (uint32_t)bloco[i * 4 + 1] << 16 | (uint32_t)bloco[i * 4 + 2] << 8 | bloco[i * 4 + 3];
    for (int i = 16; i < 64; i++) {
      uint32_t s0 = r(w[i - 15], 7) ^ r(w[i - 15], 18) ^ (w[i - 15] >> 3);
      uint32_t s1 = r(w[i - 2], 17) ^ r(w[i - 2], 19) ^ (w[i - 2] >> 10);
      w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }
    uint32_t a = h[0], b = h[1], c = h[2], d = h[3], e = h[4], f = h[5], g = h[6], hh = h[7];
    for (int i = 0; i < 64; i++) {
      uint32_t t1 = hh + (r(e, 6) ^ r(e, 11) ^ r(e, 25)) + ((e & f) ^ (~e & g)) + K[i] + w[i];
      uint32_t t2 = (r(a, 2) ^ r(a, 13) ^ r(a, 22)) + ((a & b) ^ (a & c) ^ (b & c));
      hh = g; g = f; f = e; e = d + t1; d = c; c = b; b = a; a = t1 + t2;
    }
    h[0] += a; h[1] += b; h[2] += c; h[3] += d; h[4] += e; h[5] += f; h[6] += g; h[7] += hh;
  }
  void atualizar(const uint8_t *d, size_t k) {
    total += k;
    while (k--) {
      bloco[n++] = *d++;
      if (n == 64) { processar(); n = 0; }
    }
  }
  void terminar(uint8_t *saida) {
    uint64_t bits = total * 8;
    uint8_t um = 0x80, zero = 0;
    atualizar(&um, 1);
    while (n != 56) atualizar(&zero, 1);
    for (int i = 7; i >= 0; i--) { uint8_t b = (uint8_t)(bits >> (i * 8)); atualizar(&b, 1); }
    for (int i = 0; i < 8; i++)
      for (int j = 0; j < 4; j++) saida[i * 4 + j] = (uint8_t)(h[i] >> (24 - j * 8));
  }
};
struct EstadoMd {
  Sha256 sha;
  uint8_t ipad[64], opad[64];
  bool hmac = false;
};
const mbedtls_md_info_t INFO_SHA256 = {MBEDTLS_MD_SHA256};
}  // namespace

const mbedtls_md_info_t *mbedtls_md_info_from_type(mbedtls_md_type_t t) { return t == MBEDTLS_MD_SHA256 ? &INFO_SHA256 : nullptr; }
unsigned char mbedtls_md_get_size(const mbedtls_md_info_t *) { return 32; }
void mbedtls_md_init(mbedtls_md_context_t *c) { c->info = nullptr; c->estado = nullptr; }
void mbedtls_md_free(mbedtls_md_context_t *c) { delete (EstadoMd *)c->estado; c->estado = nullptr; }
int mbedtls_md_setup(mbedtls_md_context_t *c, const mbedtls_md_info_t *info, int hmac) {
  if (!info) return -1;
  c->info = info;
  auto *e = new EstadoMd();
  e->hmac = hmac != 0;
  c->estado = e;
  return 0;
}
int mbedtls_md_starts(mbedtls_md_context_t *c) { ((EstadoMd *)c->estado)->sha.iniciar(); return 0; }
int mbedtls_md_update(mbedtls_md_context_t *c, const unsigned char *d, size_t n) {
  ((EstadoMd *)c->estado)->sha.atualizar(d, n);
  return 0;
}
int mbedtls_md_finish(mbedtls_md_context_t *c, unsigned char *s) { ((EstadoMd *)c->estado)->sha.terminar(s); return 0; }
int mbedtls_md_hmac_starts(mbedtls_md_context_t *c, const unsigned char *k, size_t n) {
  auto *e = (EstadoMd *)c->estado;
  uint8_t chave[64] = {0};
  if (n > 64) {
    Sha256 s;
    s.iniciar();
    s.atualizar(k, n);
    s.terminar(chave);
  } else {
    memcpy(chave, k, n);
  }
  for (int i = 0; i < 64; i++) {
    e->ipad[i] = chave[i] ^ 0x36;
    e->opad[i] = chave[i] ^ 0x5c;
  }
  e->sha.iniciar();
  e->sha.atualizar(e->ipad, 64);
  return 0;
}
int mbedtls_md_hmac_update(mbedtls_md_context_t *c, const unsigned char *d, size_t n) { return mbedtls_md_update(c, d, n); }
int mbedtls_md_hmac_finish(mbedtls_md_context_t *c, unsigned char *s) {
  auto *e = (EstadoMd *)c->estado;
  uint8_t interno[32];
  e->sha.terminar(interno);
  e->sha.iniciar();
  e->sha.atualizar(e->opad, 64);
  e->sha.atualizar(interno, 32);
  e->sha.terminar(s);
  return 0;
}
int mbedtls_md_hmac_reset(mbedtls_md_context_t *c) {
  auto *e = (EstadoMd *)c->estado;
  e->sha.iniciar();
  e->sha.atualizar(e->ipad, 64);
  return 0;
}
int mbedtls_md(const mbedtls_md_info_t *, const unsigned char *d, size_t n, unsigned char *s) {
  Sha256 sha;
  sha.iniciar();
  sha.atualizar(d, n);
  sha.terminar(s);
  return 0;
}
int mbedtls_md_hmac(const mbedtls_md_info_t *info, const unsigned char *k, size_t nk, const unsigned char *d, size_t n,
                    unsigned char *s) {
  mbedtls_md_context_t c;
  mbedtls_md_init(&c);
  mbedtls_md_setup(&c, info, 1);
  mbedtls_md_hmac_starts(&c, k, nk);
  mbedtls_md_hmac_update(&c, d, n);
  mbedtls_md_hmac_finish(&c, s);
  mbedtls_md_free(&c);
  return 0;
}

// =====================================================================
// ESP32: objeto ESP e hora pela internet
// =====================================================================
#ifdef ORIKI_PLACA_ESP32
#include "WiFi.h"
WiFiClass WiFi;
EspClass ESP;
void EspClass::restart() {
  sim::evento("\"t\":\"reinicio\"");
  std::fflush(stdout);
  std::exit(3);  // a bancada religa o "dispositivo"
}
void esp_restart() { ESP.restart(); }
uint32_t esp_random() { return (uint32_t)random(0x7FFFFFFF) ^ ((uint32_t)random(0xFFFF) << 16); }

static long fusoSegundos = 0;
static bool horaConfigurada = false;
void configTime(long gmtOffset, int verao, const char *, const char *, const char *) {
  fusoSegundos = gmtOffset + verao;
  horaConfigurada = true;
}
void configTzTime(const char *tz, const char *, const char *, const char *) {
  // Aceita o formato POSIX simples "<-03>3" / "BRT3": o número é o fuso a oeste de Greenwich.
  fusoSegundos = 0;
  if (tz) {
    const char *p = tz;
    while (*p && !(isdigit((unsigned char)*p) || ((*p == '-' || *p == '+') && isdigit((unsigned char)p[1])) )) p++;
    if (*p == '<') p++;
    fusoSegundos = -atol(p) * 3600;
    const char *fecha = strchr(tz, '>');
    if (fecha) fusoSegundos = -atol(fecha + 1) * 3600;
  }
  horaConfigurada = true;
}
bool getLocalTime(struct tm *info, uint32_t esperaMs) {
  unsigned long inicio = millis();
  while (!(horaConfigurada && WiFi.isConnected())) {
    if (millis() - inicio >= esperaMs) return false;
    delay(10);
  }
  time_t t = (time_t)(sim::utcAgora() + fusoSegundos);
#ifdef _WIN32
  gmtime_s(info, &t);
#else
  gmtime_r(&t, info);
#endif
  return true;
}
#endif
