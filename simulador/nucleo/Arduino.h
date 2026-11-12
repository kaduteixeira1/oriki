// =====================================================================
// Oriki - simulador do ESP32 / Arduino no PC
// Núcleo "Arduino.h" de mentira: deixa o .ino do firmware compilar com
// g++/clang/zig e rodar como um programa comum, ligado à bancada virtual
// (bancada.py) pela entrada e saída padrão.
//
// Cobre o que o firmware do Oriki usa: tempo, pinos, Serial, String,
// EEPROM, PROGMEM, tone. As bibliotecas do ESP32 (WiFi, HTTPClient,
// LittleFS, DallasTemperature, RTClib, Preferences, mbedtls) estão nos
// outros arquivos desta pasta.
// =====================================================================
#pragma once

#include <cstdint>
#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdarg>
#include <cmath>
#include <math.h>
#include <cctype>
#include <string>
#include <algorithm>
#include <type_traits>

// ---------- placa ----------
#if !defined(ORIKI_PLACA_UNO) && !defined(ORIKI_PLACA_ESP32)
#define ORIKI_PLACA_ESP32
#endif
#ifdef ORIKI_PLACA_ESP32
#ifndef ESP32
#define ESP32 1
#endif
#define ARDUINO_ARCH_ESP32 1
#else
#define ARDUINO_ARCH_AVR 1
#define ARDUINO_AVR_UNO 1
#endif
#define ARDUINO 10819
#define ORIKI_SIMULADOR 1

// ---------- tipos e constantes ----------
typedef uint8_t byte;
typedef bool boolean;
typedef uint16_t word;

#define HIGH 0x1
#define LOW 0x0
#define INPUT 0x01
#define OUTPUT 0x03
#define INPUT_PULLUP 0x05
#define INPUT_PULLDOWN 0x09
#define CHANGE 1
#define FALLING 2
#define RISING 3
#define LSBFIRST 0
#define MSBFIRST 1
#define DEC 10
#define HEX 16
#define OCT 8
#define BIN 2
#define PI 3.1415926535897932384626433832795
#define HALF_PI 1.5707963267948966192313216916398
#define TWO_PI 6.283185307179586476925286766559
#define DEG_TO_RAD 0.017453292519943295769236907684886
#define RAD_TO_DEG 57.295779513082320876798154814105

#ifdef ORIKI_PLACA_UNO
static const uint8_t A0 = 14, A1 = 15, A2 = 16, A3 = 17, A4 = 18, A5 = 19;
#define LED_BUILTIN 13
#else
static const uint8_t A0 = 36, A3 = 39, A4 = 32, A5 = 33, A6 = 34, A7 = 35;
#define LED_BUILTIN 2
#endif

// ---------- PROGMEM (no PC é memória comum) ----------
#define PROGMEM
#define PGM_P const char *
#define PSTR(s) (s)
#define pgm_read_byte(a) (*(const uint8_t *)(a))
#define pgm_read_byte_near(a) pgm_read_byte(a)
#define pgm_read_word(a) (*(const uint16_t *)(a))
#define pgm_read_dword(a) (*(const uint32_t *)(a))
#define pgm_read_float(a) (*(const float *)(a))
#define pgm_read_ptr(a) (*(const void *const *)(a))
#define strcpy_P strcpy
#define strncpy_P strncpy
#define strcat_P strcat
#define strcmp_P strcmp
#define strncmp_P strncmp
#define strlen_P strlen
#define memcpy_P memcpy
#define sprintf_P sprintf
#define snprintf_P snprintf
#define vsnprintf_P vsnprintf

class __FlashStringHelper;
#define F(s) (reinterpret_cast<const __FlashStringHelper *>(s))
#define FPSTR(p) (reinterpret_cast<const __FlashStringHelper *>(p))

// ---------- utilidades ----------
using std::isinf;
using std::isnan;
#ifdef unix
#undef unix
#endif
template <class A, class B> inline auto min(A a, B b) -> decltype(a < b ? a : b) { return b < a ? b : a; }
template <class A, class B> inline auto max(A a, B b) -> decltype(a < b ? a : b) { return a < b ? b : a; }
template <class T, class L, class H> inline T constrain(T x, L lo, H hi) { return x < lo ? lo : (x > hi ? hi : x); }
inline long map(long x, long in_min, long in_max, long out_min, long out_max) {
  return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min;
}
#define sq(x) ((x) * (x))
#define radians(d) ((d) * DEG_TO_RAD)
#define degrees(r) ((r) * RAD_TO_DEG)
#define lowByte(w) ((uint8_t)((w) & 0xff))
#define highByte(w) ((uint8_t)((w) >> 8))
#define bitRead(v, b) (((v) >> (b)) & 0x01)
#define bitSet(v, b) ((v) |= (1UL << (b)))
#define bitClear(v, b) ((v) &= ~(1UL << (b)))
#define bitWrite(v, b, x) ((x) ? bitSet(v, b) : bitClear(v, b))
#define bit(b) (1UL << (b))
#define interrupts()
#define noInterrupts()
#define digitalPinToInterrupt(p) (p)

// ---------- tempo e pinos (implementados em nucleo.cpp) ----------
unsigned long millis();
unsigned long micros();
void delay(unsigned long ms);
void delayMicroseconds(unsigned int us);
void yield();
void pinMode(uint8_t pino, uint8_t modo);
void digitalWrite(uint8_t pino, uint8_t valor);
int digitalRead(uint8_t pino);
int analogRead(uint8_t pino);
void analogWrite(uint8_t pino, int valor);
void analogReadResolution(int bits);
void tone(uint8_t pino, unsigned int frequencia, unsigned long duracao = 0);
void noTone(uint8_t pino);
void attachInterrupt(uint8_t, void (*)(void), int);
void detachInterrupt(uint8_t);
long random(long max);
long random(long min, long max);
void randomSeed(unsigned long semente);
char *dtostrf(double valor, signed char largura, unsigned char decimais, char *saida);
char *itoa(int valor, char *saida, int base);
char *ltoa(long valor, char *saida, int base);
char *utoa(unsigned valor, char *saida, int base);
char *ultoa(unsigned long valor, char *saida, int base);

// ---------- String ----------
class String {
 public:
  String() {}
  String(const char *s) : s_(s ? s : "") {}
  String(const std::string &s) : s_(s) {}
  String(const __FlashStringHelper *s) : s_(reinterpret_cast<const char *>(s)) {}
  String(char c) : s_(1, c) {}
  String(unsigned char v, unsigned char base = 10);
  String(int v, unsigned char base = 10);
  String(unsigned int v, unsigned char base = 10);
  String(long v, unsigned char base = 10);
  String(unsigned long v, unsigned char base = 10);
  String(long long v, unsigned char base = 10);
  String(unsigned long long v, unsigned char base = 10);
  String(float v, unsigned char decimais = 2);
  String(double v, unsigned char decimais = 2);

  const char *c_str() const { return s_.c_str(); }
  unsigned int length() const { return (unsigned int)s_.size(); }
  bool isEmpty() const { return s_.empty(); }
  bool reserve(unsigned int n) { s_.reserve(n); return true; }
  char charAt(unsigned int i) const { return i < s_.size() ? s_[i] : 0; }
  void setCharAt(unsigned int i, char c) { if (i < s_.size()) s_[i] = c; }
  char operator[](unsigned int i) const { return charAt(i); }
  char &operator[](unsigned int i) { return s_[i]; }
  int indexOf(char c, unsigned int de = 0) const { auto p = s_.find(c, de); return p == std::string::npos ? -1 : (int)p; }
  int indexOf(const String &t, unsigned int de = 0) const { auto p = s_.find(t.s_, de); return p == std::string::npos ? -1 : (int)p; }
  int lastIndexOf(char c) const { auto p = s_.rfind(c); return p == std::string::npos ? -1 : (int)p; }
  int lastIndexOf(const String &t) const { auto p = s_.rfind(t.s_); return p == std::string::npos ? -1 : (int)p; }
  String substring(unsigned int de) const { return de >= s_.size() ? String() : String(s_.substr(de)); }
  String substring(unsigned int de, unsigned int ate) const {
    if (de > ate) std::swap(de, ate);
    if (de >= s_.size()) return String();
    return String(s_.substr(de, std::min<size_t>(ate, s_.size()) - de));
  }
  bool startsWith(const String &p) const { return s_.compare(0, p.s_.size(), p.s_) == 0; }
  bool endsWith(const String &p) const {
    return s_.size() >= p.s_.size() && s_.compare(s_.size() - p.s_.size(), p.s_.size(), p.s_) == 0;
  }
  bool equals(const String &o) const { return s_ == o.s_; }
  bool equalsIgnoreCase(const String &o) const;
  int compareTo(const String &o) const { return s_.compare(o.s_); }
  long toInt() const { return atol(s_.c_str()); }
  float toFloat() const { return (float)atof(s_.c_str()); }
  double toDouble() const { return atof(s_.c_str()); }
  void trim();
  void toLowerCase() { for (auto &c : s_) c = (char)tolower((unsigned char)c); }
  void toUpperCase() { for (auto &c : s_) c = (char)toupper((unsigned char)c); }
  void replace(const String &de, const String &para);
  void replace(char de, char para) { for (auto &c : s_) if (c == de) c = para; }
  void remove(unsigned int i) { if (i < s_.size()) s_.erase(i); }
  void remove(unsigned int i, unsigned int n) { if (i < s_.size()) s_.erase(i, n); }
  void toCharArray(char *buf, unsigned int n, unsigned int de = 0) const {
    if (!n) return;
    size_t k = de < s_.size() ? std::min<size_t>(n - 1, s_.size() - de) : 0;
    if (k) memcpy(buf, s_.data() + de, k);
    buf[k] = 0;
  }
  void getBytes(unsigned char *buf, unsigned int n, unsigned int de = 0) const { toCharArray((char *)buf, n, de); }
  template <class T> bool concat(const T &v) { *this += v; return true; }

  String &operator+=(const String &o) { s_ += o.s_; return *this; }
  String &operator+=(const char *o) { s_ += (o ? o : ""); return *this; }
  String &operator+=(char c) { s_ += c; return *this; }
  String &operator+=(const __FlashStringHelper *o) { s_ += reinterpret_cast<const char *>(o); return *this; }
  template <class T> String &operator+=(T v) { return *this += String(v); }

  bool operator==(const String &o) const { return s_ == o.s_; }
  bool operator==(const char *o) const { return s_ == (o ? o : ""); }
  bool operator!=(const String &o) const { return s_ != o.s_; }
  bool operator!=(const char *o) const { return !(*this == o); }
  bool operator<(const String &o) const { return s_ < o.s_; }
  bool operator>(const String &o) const { return s_ > o.s_; }
  explicit operator bool() const { return true; }

  const std::string &std() const { return s_; }

 private:
  std::string s_;
};

inline String operator+(const String &a, const String &b) { String r(a); r += b; return r; }
inline String operator+(const String &a, const char *b) { String r(a); r += b; return r; }
inline String operator+(const char *a, const String &b) { String r(a); r += b; return r; }
inline String operator+(const String &a, char b) { String r(a); r += b; return r; }
inline String operator+(const String &a, const __FlashStringHelper *b) { String r(a); r += b; return r; }
template <class T, class = typename std::enable_if<std::is_arithmetic<T>::value>::type>
inline String operator+(const String &a, T b) { String r(a); r += String(b); return r; }

// ---------- Print / Stream / Serial ----------
class Print {
 public:
  virtual ~Print() {}
  virtual size_t write(uint8_t c) = 0;
  virtual size_t write(const uint8_t *buf, size_t n) { size_t k = 0; while (n--) k += write(*buf++); return k; }
  size_t write(const char *s) { return s ? write((const uint8_t *)s, strlen(s)) : 0; }
  size_t write(const char *buf, size_t n) { return write((const uint8_t *)buf, n); }
  virtual void flush() {}

  size_t print(const char *s) { return write(s); }
  size_t print(const String &s) { return write(s.c_str()); }
  size_t print(const __FlashStringHelper *s) { return write(reinterpret_cast<const char *>(s)); }
  size_t print(char c) { return write((uint8_t)c); }
  size_t print(unsigned char v, int base = DEC) { return imprimirNumero((unsigned long long)v, base); }
  size_t print(int v, int base = DEC) { return imprimirSinal((long long)v, base); }
  size_t print(unsigned int v, int base = DEC) { return imprimirNumero((unsigned long long)v, base); }
  size_t print(long v, int base = DEC) { return imprimirSinal((long long)v, base); }
  size_t print(unsigned long v, int base = DEC) { return imprimirNumero((unsigned long long)v, base); }
  size_t print(long long v, int base = DEC) { return imprimirSinal(v, base); }
  size_t print(unsigned long long v, int base = DEC) { return imprimirNumero(v, base); }
  size_t print(double v, int decimais = 2);
  size_t println() { return write("\r\n"); }
  template <class T> size_t println(const T &v) { size_t n = print(v); return n + println(); }
  template <class T> size_t println(const T &v, int b) { size_t n = print(v, b); return n + println(); }
  size_t printf(const char *fmt, ...);

 private:
  size_t imprimirNumero(unsigned long long v, int base);
  size_t imprimirSinal(long long v, int base);
};

class Stream : public Print {
 public:
  virtual int available() = 0;
  virtual int read() = 0;
  virtual int peek() = 0;
  void setTimeout(unsigned long ms) { timeout_ = ms; }
  size_t readBytes(char *buf, size_t n);
  size_t readBytes(uint8_t *buf, size_t n) { return readBytes((char *)buf, n); }
  size_t readBytesUntil(char fim, char *buf, size_t n);
  String readString();
  String readStringUntil(char fim);
  long parseInt();
  float parseFloat();
  bool find(const char *alvo);

 protected:
  int lerComEspera();
  unsigned long timeout_ = 1000;
};

class HardwareSerial : public Stream {
 public:
  void begin(unsigned long, ...) {}
  void end() {}
  int available() override;
  int read() override;
  int peek() override;
  size_t write(uint8_t c) override;
  using Print::write;
  void flush() override;
  operator bool() const { return true; }
  void setDebugOutput(bool) {}
};
extern HardwareSerial Serial;

// Funções do firmware
void setup();
void loop();

#ifdef ORIKI_PLACA_ESP32
#include "esp32_extras.h"
#endif
