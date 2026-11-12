// Sistema de arquivos de mentira (LittleFS/SPIFFS do ESP32) numa pasta do PC:
// dados/<dispositivo>/littlefs/. O caminho "/fila.jsonl" do firmware vira essa pasta + "fila.jsonl".
#pragma once
#include "Arduino.h"
#include <memory>

#define FILE_READ "r"
#define FILE_WRITE "w"
#define FILE_APPEND "a"

namespace fs {
enum SeekMode { SeekSet = 0, SeekCur = 1, SeekEnd = 2 };

class File : public Stream {
 public:
  File() {}
  File(const std::string &real, const std::string &nome, const char *modo);
  ~File() override;
  File(const File &) = default;
  File &operator=(const File &) = default;

  size_t write(uint8_t c) override;
  size_t write(const uint8_t *buf, size_t n) override;
  using Print::write;
  int available() override;
  int read() override;
  int peek() override;
  size_t read(uint8_t *buf, size_t n);
  void flush() override;
  bool seek(uint32_t pos, SeekMode modo = SeekSet);
  size_t position() const;
  size_t size() const;
  void close();
  operator bool() const { return (bool)estado_ && (estado_->arquivo || estado_->pasta); }
  const char *name() const;
  const char *path() const { return estado_ ? estado_->nome.c_str() : ""; }
  bool isDirectory() const { return estado_ && estado_->pasta; }
  File openNextFile(const char *modo = FILE_READ);
  void rewindDirectory() { if (estado_) estado_->proximo = 0; }
  time_t getLastWrite() { return 0; }

 private:
  struct Estado {
    std::FILE *arquivo = nullptr;
    bool pasta = false;
    std::string real, nome;
    size_t proximo = 0;
    ~Estado() { if (arquivo) std::fclose(arquivo); }
  };
  std::shared_ptr<Estado> estado_;
};

class FS {
 public:
  explicit FS(const char *pasta) : pasta_(pasta) {}
  bool begin(bool formatarSeFalhar = false, const char * = nullptr, uint8_t = 10, const char * = nullptr);
  void end() {}
  bool format();
  File open(const char *caminho, const char *modo = FILE_READ, bool criar = false);
  File open(const String &caminho, const char *modo = FILE_READ, bool criar = false) {
    return open(caminho.c_str(), modo, criar);
  }
  bool exists(const char *caminho);
  bool exists(const String &caminho) { return exists(caminho.c_str()); }
  bool remove(const char *caminho);
  bool remove(const String &caminho) { return remove(caminho.c_str()); }
  bool rename(const char *de, const char *para);
  bool rename(const String &de, const String &para) { return rename(de.c_str(), para.c_str()); }
  bool mkdir(const char *caminho);
  bool mkdir(const String &caminho) { return mkdir(caminho.c_str()); }
  bool rmdir(const char *caminho);
  size_t totalBytes() { return 1441792; }  // partição de 1,4 MB, como no ESP32 de 4 MB
  size_t usedBytes();

 private:
  std::string real(const char *caminho);
  std::string pasta_;
};
}  // namespace fs

using fs::File;
using fs::FS;
using fs::SeekCur;
using fs::SeekEnd;
using fs::SeekSet;
