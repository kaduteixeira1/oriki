// RTC DS3231 de mentira. Conta a hora local de Belém (-03:00) a partir do relógio do PC, mais o ajuste
// feito pelo firmware (rtc.adjust) ou pela bancada (botões atrasar/adiantar). O ajuste fica salvo em
// dados/<dispositivo>/rtc.txt, como a bateria do DS3231 guardaria.
#pragma once
#include "Arduino.h"
#include "Wire.h"
#include "sim.h"
#include <ctime>

class TimeSpan {
 public:
  TimeSpan(int32_t segundos = 0) : s_(segundos) {}
  TimeSpan(int16_t dias, int8_t horas, int8_t minutos, int8_t segundos)
      : s_((int32_t)dias * 86400L + (int32_t)horas * 3600 + (int32_t)minutos * 60 + segundos) {}
  int16_t days() const { return s_ / 86400L; }
  int8_t hours() const { return s_ / 3600 % 24; }
  int8_t minutes() const { return s_ / 60 % 60; }
  int8_t seconds() const { return s_ % 60; }
  int32_t totalseconds() const { return s_; }
 private:
  int32_t s_;
};

class DateTime {
 public:
  DateTime(uint32_t segundos = 946684800UL) { definir((int64_t)segundos); }
  DateTime(uint16_t ano, uint8_t mes, uint8_t dia, uint8_t hora = 0, uint8_t minuto = 0, uint8_t segundo = 0) {
    definir(paraUnix(ano, mes, dia, hora, minuto, segundo));
  }
  // DateTime(F(__DATE__), F(__TIME__)), como no exemplo do RTClib
  DateTime(const char *data, const char *hora) {
    static const char meses[] = "JanFebMarAprMayJunJulAugSepOctNovDec";
    char m[4] = {data[0], data[1], data[2], 0};
    const char *p = strstr(meses, m);
    int mes = p ? (int)(p - meses) / 3 + 1 : 1;
    definir(paraUnix(atoi(data + 7), mes, atoi(data + 4), atoi(hora), atoi(hora + 3), atoi(hora + 6)));
  }
  DateTime(const __FlashStringHelper *d, const __FlashStringHelper *h)
      : DateTime(reinterpret_cast<const char *>(d), reinterpret_cast<const char *>(h)) {}

  uint16_t year() const { return tm_.tm_year + 1900; }
  uint8_t month() const { return tm_.tm_mon + 1; }
  uint8_t day() const { return tm_.tm_mday; }
  uint8_t hour() const { return tm_.tm_hour; }
  uint8_t minute() const { return tm_.tm_min; }
  uint8_t second() const { return tm_.tm_sec; }
  uint8_t dayOfTheWeek() const { return tm_.tm_wday; }
  uint32_t unixtime() const { return (uint32_t)seg_; }
  uint32_t secondstime() const { return (uint32_t)(seg_ - 946684800LL); }
  bool isValid() const { return year() >= 2000; }
  DateTime operator+(const TimeSpan &t) const { return DateTime((uint32_t)(seg_ + t.totalseconds())); }
  DateTime operator-(const TimeSpan &t) const { return DateTime((uint32_t)(seg_ - t.totalseconds())); }
  TimeSpan operator-(const DateTime &o) const { return TimeSpan((int32_t)(seg_ - o.seg_)); }
  bool operator<(const DateTime &o) const { return seg_ < o.seg_; }
  bool operator==(const DateTime &o) const { return seg_ == o.seg_; }
  // "YYYY-MM-DDThh:mm:ss" (os formatos do RTClib: YYYY MM DD hh mm ss)
  char *toString(char *formato) const {
    struct { const char *k; int v; int w; } campos[] = {
        {"YYYY", year(), 4}, {"YY", year() % 100, 2}, {"MM", month(), 2}, {"DD", day(), 2},
        {"hh", hour(), 2}, {"mm", minute(), 2}, {"ss", second(), 2}};
    for (auto &c : campos) {
      char *p = strstr(formato, c.k);
      if (p) {
        char b[8];
        snprintf(b, sizeof b, "%0*d", c.w, c.v);
        memcpy(p, b, strlen(c.k));
      }
    }
    return formato;
  }
  String timestamp() const {
    char b[24];
    snprintf(b, sizeof b, "%04u-%02u-%02uT%02u:%02u:%02u", year(), month(), day(), hour(), minute(), second());
    return String(b);
  }

 private:
  static int64_t paraUnix(int a, int m, int d, int h, int mi, int s) {
    // dias desde 1970 (algoritmo de Howard Hinnant), sem depender do fuso do PC
    a -= m <= 2;
    int64_t era = (a >= 0 ? a : a - 399) / 400;
    unsigned yoe = (unsigned)(a - era * 400);
    unsigned doy = (153 * (m + (m > 2 ? -3 : 9)) + 2) / 5 + d - 1;
    unsigned doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    int64_t dias = era * 146097 + (int64_t)doe - 719468;
    return dias * 86400 + h * 3600 + mi * 60 + s;
  }
  void definir(int64_t segundos) {
    seg_ = segundos;
    time_t t = (time_t)segundos;
#ifdef _WIN32
    gmtime_s(&tm_, &t);
#else
    gmtime_r(&t, &tm_);
#endif
  }
  int64_t seg_ = 0;
  struct tm tm_ {};
};

class RTC_DS3231 {
 public:
  bool begin(TwoWire * = &Wire) { return true; }
  DateTime now() { return DateTime((uint32_t)sim::rtcLocalAgora()); }
  void adjust(const DateTime &dt) { sim::rtcAjustarLocal(dt.unixtime()); }
  bool lostPower() { return sim::rtcPerdeuEnergia(); }
  float getTemperature() { return 31.25f; }
  void disable32K() {}
  void writeSqwPinMode(int) {}
  void disableAlarm(int) {}
  void clearAlarm(int) {}
};
typedef RTC_DS3231 RTC_DS1307;
typedef RTC_DS3231 RTC_PCF8523;
#define DS3231_OFF 0
