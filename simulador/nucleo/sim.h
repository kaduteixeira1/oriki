// Ligação entre as bibliotecas de mentira e a bancada virtual (uso interno do simulador).
#pragma once
#include <string>
#include <vector>
#include <utility>
#include <cstdint>

namespace sim {
// Ambiente
std::string pastaDados();                 // onde ficam EEPROM, LittleFS e Preferences deste dispositivo
std::string caminhoDados(const std::string &relativo);
void criarPastas(const std::string &caminho);

// Sensores (valores mandados pela bancada)
float temperaturaAgua();                  // °C que o sensor está lendo agora
bool sensorConectado();

// Wi-Fi
bool wifiDisponivel();                    // a bancada liga/desliga o roteador
void wifiPedirConexao();                  // WiFi.begin / WiFiManager
bool wifiConectado();
void wifiDesconectar();

// HTTP pela bancada. Devolve o status HTTP ou um código negativo de erro (como o HTTPClient).
int http(const std::string &metodo, const std::string &url,
         const std::vector<std::pair<std::string, std::string>> &cabecalhos,
         const std::string &corpo, std::string &resposta, unsigned long timeoutMs);

// Relógio de parede (segundos desde 1970). O RTC conta em hora de Belém (-03:00), como o firmware.
int64_t utcAgora();                       // relógio do PC (tempo real, mesmo com a bancada acelerada)
int64_t rtcLocalAgora();                  // hora local de Belém + ajuste do RTC
void rtcAjustarLocal(int64_t localSegundos);
bool rtcPerdeuEnergia();

// Avisos para o painel
void evento(const std::string &jsonSemChaves);   // ex.: "\"t\":\"log\",\"d\":\"...\""
std::string json(const std::string &texto);      // texto como string JSON (com aspas)
}  // namespace sim
