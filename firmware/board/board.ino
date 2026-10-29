// SMART FLOOD ESP32 펌웨어(REV16 무납땜 구성). 설계서 10장의 v2 소스를 옮겨 고침
// 하는 일
//   1) KIT0139 수위센서로 어항 수위를 1초마다 재고 서버(POST /api/ingest)로 보냄
//   2) 릴레이로 펌프를 끊어서(ON/OFF 반복) 천천히 물을 넣어 강우를 흉내 냄
//   3) 최근 20초 상승 속도로 A·B·C 구역 침수 시각을 미리 예측해 주의·경계·침수로 알림
// 보드: ESP32 DevKitC V4. Arduino IDE 보드 "ESP32 Dev Module". 추가 라이브러리 없음
// 연결: GPIO34 <- KIT0139 변환보드 신호, GPIO26 -> 릴레이 IN, GPIO27 <- 플로트(다른 쪽 GND)
//       3V3 -> 변환보드 VCC, 5V -> 릴레이 VCC, GND 공통(12 V 어댑터 - 포함)
// 접속 정보(AP_PASS, STA_SSID, STA_PASS, SERVER_URL, NTFY_TOPIC)는 secrets.h 에만 둠
// secrets.h 는 저장소에 올리지 않음. 없거나 비어 있으면 그 기능이 꺼짐
#include <HTTPClient.h>
#include <Preferences.h>
#include <WebServer.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include "page.h"

#if __has_include("secrets.h")
#include "secrets.h"
#endif
#ifndef AP_PASS
#define AP_PASS ""  // 비어 있으면 관제 화면과 펌프 제어를 열지 않음
#endif
#ifndef STA_SSID
#define STA_SSID ""  // 비어 있으면 와이파이에 붙지 않음
#endif
#ifndef STA_PASS
#define STA_PASS ""
#endif
#ifndef SERVER_URL
#define SERVER_URL ""  // 비어 있으면 서버로 보내지 않음
#endif
#ifndef NTFY_TOPIC
#define NTFY_TOPIC ""  // 비어 있으면 휴대폰 푸시를 보내지 않음
#endif

// ===== 핀 =====
const int PIN_LEVEL = 34;  // ADC1 입력 전용. 와이파이를 써도 읽힘
const int PIN_RELAY = 26;
const int PIN_FLOAT = 27;

// ===== 하드웨어 옵션(조립 뒤 시험 결과에 맞춤) =====
const bool RELAY_ACTIVE_LOW = true;       // IN=LOW 에서 켜지는 모듈이면 true
const bool RELAY_OFF_HIGHZ = true;        // 3.3 V 로 안 꺼지는 5 V 모듈은 끌 때 입력 핀으로 둠
const bool FLOAT_LOW_WHEN_CLOSED = true;  // 물이 모자랄 때 접점이 닫히면 true

// ===== 네트워크 =====
const char* AP_SSID = "SMART_FLOOD";  // 보드가 여는 와이파이 이름. 암호는 secrets.h 의 AP_PASS
const char* DEVICE_ID = "esp32_1";    // backend/config.yaml devices.allowed 에 있는 이름
// backend/config.yaml sensors.A.install_height_mm 와 같은 값. 서버는 거리를 받으므로
// 거리 = 이 값 - 수위 로 바꿔 보냄
const float INSTALL_HEIGHT_MM = 600.0f;

// ===== 수위센서 =====
// 0~5000 mm 가 4~20 mA 이고 변환보드 120 Ω 에서 2.604 mm/mV, 0 mm 에서 480 mV
const float LEVEL_SLOPE_THEORY = 5000.0f / 16.0f / 120.0f;
const float LEVEL_MV_AT_ZERO = 480.0f;
const float FAULT_LOW_MV = 300.0f;    // 이 아래는 단선이나 전원 이상
const float FAULT_HIGH_MV = 2800.0f;  // 이 위는 단락이나 과전압

// ===== 구역 =====
const int NZ = 3;
const char* ZNAME[NZ] = {"A 낮은 도로", "B 주택 골목", "C 높은 광장"};

// ===== 설정(웹에서 고치고 플래시에 저장) =====
struct Config {
  float z[NZ] = {40, 70, 110};  // 구역별 침수 기준 높이(mm, 어항 바닥 0). 자로 재서 입력
  float maxLevel = 100;         // 이 수위에서 펌프를 강제로 멈춤(C 보다 낮게)
  float cautionEta = 60;        // 침수까지 이 초 이내로 예측되면 주의
  float warningEta = 30;        // 이 초 이내면 경계
  float flowMlS = 0;            // 펌프 실측 유량(0 은 아직 모름)
  float areaCm2 = 1700;         // 유효 수면 면적(자동 추정값을 적용할 수 있음)
  float rainOnS = 2;            // 강우 흉내: 펌프 ON 초
  float rainOffS = 8;           // 강우 흉내: 펌프 OFF 초
  float pumpMaxOnS = 60;        // 한 번에 이어서 돌리는 최대 초(수동 포함)
  float runMaxS = 1800;         // 실험 한 회차의 최대 초
  float lvSlope = LEVEL_SLOPE_THEORY;
  float lvOffset = -LEVEL_SLOPE_THEORY * LEVEL_MV_AT_ZERO + 10.0f;  // 이론 영점 + 10 mm(설계서 값)
  float cal1mv = 0, cal1mm = 0;
  bool cal1 = false;
} cfg;

Preferences prefs;
WebServer server(80);
bool webOn = false;  // 관제 화면을 열었는지(AP 암호가 있을 때만)

// ===== 상태 =====
enum Mode { M_STOP = 0, M_MANUAL, M_RAIN, M_FLOWTEST };
Mode mode = M_STOP;
bool running = false;  // 실험 한 회차가 진행 중
unsigned long runStartMs = 0;
bool pumpOn = false;
unsigned long pumpOnSince = 0, phaseSince = 0, flowTestStart = 0;
bool phaseOn = false;
float pumpOnTotalS = 0;  // 이번 회차의 펌프 누적 가동(초)
float levelAtStart = 0;
String stopWhy = "";

float levelMv = 0, levelMm = 0;
bool fault = false;
bool floatLow = false;
float rateMeas = 0, rateModel = 0, rate = 0;  // mm/s
String rateSrc = "-";
float pred[3] = {0, 0, 0};     // +10, +20, +30 초 뒤의 예측 수위
float eta[NZ];                 // 침수까지 남은 초(-1 은 상승 없음, 0 은 이미 침수)
int stage[NZ];                 // 0 정상, 1 주의, 2 경계, 3 침수
float alertT[NZ], floodT[NZ];  // 첫 경보와 실제 침수 시각(회차 경과 초, -1 은 없음)
float areaEst = 0;

// 1초 이력
const int HN = 30, REG = 20;
float hist[HN];
int hN = 0, hI = 0;
// 실험 기록(1초 간격, 최대 30분)
const int LOGN = 1800;
int16_t logLv[LOGN];
uint8_t logPump[LOGN];
int logN = 0;

String pendingPush = "";
String bootId;
uint32_t seqNo = 0;

// ===== 릴레이 =====
// 릴레이를 켜거나 끔. 끌 때 RELAY_OFF_HIGHZ 면 핀을 입력으로 풀어 모듈의 풀업이 끄게 함
void relayWrite(bool on) {
  if (RELAY_ACTIVE_LOW) {
    if (on) {
      pinMode(PIN_RELAY, OUTPUT);
      digitalWrite(PIN_RELAY, LOW);
    } else if (RELAY_OFF_HIGHZ) {
      pinMode(PIN_RELAY, INPUT);
    } else {
      pinMode(PIN_RELAY, OUTPUT);
      digitalWrite(PIN_RELAY, HIGH);
    }
  } else {
    pinMode(PIN_RELAY, OUTPUT);
    digitalWrite(PIN_RELAY, on ? HIGH : LOW);
  }
}

// 펌프 상태를 바꾸고 가동 시간을 쌓음
void setPump(bool on) {
  if (on == pumpOn) return;
  if (on) pumpOnSince = millis();
  else pumpOnTotalS += (millis() - pumpOnSince) / 1000.0f;
  pumpOn = on;
  relayWrite(on);
}

// 펌프를 끄고 멈춘 까닭을 남김
void stopPump(const String& why) {
  mode = M_STOP;
  setPump(false);
  stopWhy = why;
  Serial.println("[STOP] " + why);
}

// ===== 저장 =====
// 설정을 플래시에 저장
void saveCfg() {
  prefs.begin("flood2", false);
  prefs.putBytes("cfg", &cfg, sizeof(cfg));
  prefs.end();
}

// 플래시의 설정을 읽음. 크기가 다르면(펌웨어가 바뀜) 기본값을 씀
void loadCfg() {
  prefs.begin("flood2", true);
  if (prefs.getBytesLength("cfg") == sizeof(cfg)) prefs.getBytes("cfg", &cfg, sizeof(cfg));
  prefs.end();
}

// ===== 측정 =====
// 수위센서 전압(mV). 64번 읽은 평균
float readMv() {
  uint32_t s = 0;
  for (int i = 0; i < 64; i++) s += analogReadMilliVolts(PIN_LEVEL);
  return s / 64.0f;
}

// 100 ms 마다: 전압을 이동평균하고 수위(mm)와 플로트 상태를 갱신
void sample() {
  float mv = readMv();
  levelMv = (levelMv == 0) ? mv : levelMv * 0.85f + mv * 0.15f;
  fault = (levelMv < FAULT_LOW_MV || levelMv > FAULT_HIGH_MV);
  levelMm = cfg.lvSlope * levelMv + cfg.lvOffset;
  if (levelMm < 0) levelMm = 0;
  bool closed = digitalRead(PIN_FLOAT) == LOW;
  floatLow = FLOAT_LOW_WHEN_CLOSED ? closed : !closed;
}

// 회차가 시작된 뒤 지난 초
float elapsedS() { return running ? (millis() - runStartMs) / 1000.0f : 0; }

// 모드별 펌프 ON 비율
float duty() {
  if (mode == M_MANUAL || mode == M_FLOWTEST) return 1;
  if (mode == M_RAIN) return cfg.rainOnS / (cfg.rainOnS + cfg.rainOffS);
  return 0;
}

// 최근 REG 초의 선형회귀 기울기(mm/s)
float regression() {
  int n = hN < REG ? hN : REG;
  if (n < 5) return 0;
  float sx = 0, sy = 0, sxx = 0, sxy = 0;
  for (int k = 0; k < n; k++) {
    float y = hist[(hI - n + k + HN) % HN], x = k;
    sx += x;
    sy += y;
    sxx += x * x;
    sxy += x * y;
  }
  float d = n * sxx - sx * sx;
  return d == 0 ? 0 : (n * sxy - sx * sy) / d;
}

// 단계가 오른 구역의 알림 문구를 쌓음
void queuePush(int zi, int st) {
  static const char* SN[] = {"정상", "주의", "경계", "침수"};
  String msg = String("[") + SN[st] + "] " + ZNAME[zi];
  if (st < 3) msg += " " + String((int)eta[zi]) + "초 뒤 침수 예상.";
  else msg += " 침수 발생.";
  if (zi == 0) msg += " 경로 A를 피해 경로 B로 우회하세요.";
  else if (zi == 1) msg += " 고지대(C)로 대피하세요.";
  else msg += " 고지대도 위험합니다. 실험을 멈추세요.";
  if (pendingPush.length()) pendingPush += "\n";
  pendingPush += msg;
}

// 1초마다: 이력을 쌓고 상승 속도, 예측 수위, 구역별 침수까지 남은 초와 단계를 갱신
void predict() {
  hist[hI] = levelMm;
  hI = (hI + 1) % HN;
  if (hN < HN) hN++;
  rateMeas = regression();
  float flowMmS = (cfg.flowMlS > 0 && cfg.areaCm2 > 0) ? cfg.flowMlS / cfg.areaCm2 * 10.0f : 0;
  rateModel = flowMmS * duty();
  // 측정 이력이 충분하고 실제로 오르고 있으면 측정값, 아니면 펌프 유량 기반 모델값
  if (hN >= 15 && rateMeas > 0.01f) {
    rate = rateMeas;
    rateSrc = "실측 기울기";
  } else if (rateModel > 0) {
    rate = rateModel;
    rateSrc = "펌프 유량 모델";
  } else {
    rate = rateMeas;
    rateSrc = "실측 기울기";
  }

  for (int k = 0; k < 3; k++) pred[k] = levelMm + rate * 10 * (k + 1);

  float t = elapsedS();
  for (int i = 0; i < NZ; i++) {
    if (levelMm >= cfg.z[i]) eta[i] = 0;
    else if (rate > 0.005f) eta[i] = (cfg.z[i] - levelMm) / rate;
    else eta[i] = -1;
    int st = 0;
    if (eta[i] == 0) st = 3;
    else if (eta[i] > 0 && eta[i] <= cfg.warningEta) st = 2;
    else if (eta[i] > 0 && eta[i] <= cfg.cautionEta) st = 1;
    if (running && st > stage[i]) {  // 회차 중에는 단계가 올라가기만 함
      if (stage[i] == 0 && alertT[i] < 0) alertT[i] = t;
      if (st == 3 && floodT[i] < 0) floodT[i] = t;
      stage[i] = st;
      queuePush(i, st);
    }
    if (!running) stage[i] = st;
  }

  float rise = levelMm - levelAtStart;
  float pumpedMl = (pumpOnTotalS + (pumpOn ? (millis() - pumpOnSince) / 1000.0f : 0)) * cfg.flowMlS;
  areaEst = (running && rise > 5 && pumpedMl > 0) ? pumpedMl / (rise / 10.0f) : 0;

  if (running && logN < LOGN) {
    logLv[logN] = (int16_t)(levelMm * 10);
    logPump[logN] = pumpOn ? 1 : 0;
    logN++;
  }
}

// ===== 펌프 제어와 안전 =====
// 100 ms 마다: 안전 조건이 하나라도 걸리면 펌프를 끄고, 아니면 모드대로 돌림
void control() {
  if (mode == M_STOP) {
    setPump(false);
    return;
  }
  if (floatLow) {
    stopPump("급수통 물 부족(플로트)");
    return;
  }
  if (mode != M_MANUAL && mode != M_FLOWTEST && fault) {
    stopPump("수위센서 이상(12V·배선 확인)");
    return;
  }
  if (!fault && levelMm >= cfg.maxLevel && mode != M_FLOWTEST) {
    stopPump("안전 최대 수위 도달");
    return;
  }
  if (pumpOn && millis() - pumpOnSince > cfg.pumpMaxOnS * 1000UL) {
    stopPump("연속 가동 시간 초과");
    return;
  }
  if (running && elapsedS() > cfg.runMaxS) {
    stopPump("실험 최대 시간 초과");
    return;
  }

  if (mode == M_MANUAL) {
    setPump(true);
    return;
  }
  if (mode == M_FLOWTEST) {
    if (millis() - flowTestStart >= 30000UL) {
      stopPump("유량 측정 30초 완료");
      return;
    }
    setPump(true);
    return;
  }
  if (mode == M_RAIN) {
    unsigned long ph = (phaseOn ? cfg.rainOnS : cfg.rainOffS) * 1000UL;
    if (millis() - phaseSince >= ph) {
      phaseOn = !phaseOn;
      phaseSince = millis();
    }
    setPump(phaseOn);
  }
}

// 새 회차를 시작: 기록과 단계를 비움
void newRun() {
  running = true;
  runStartMs = millis();
  logN = 0;
  pumpOnTotalS = 0;
  levelAtStart = levelMm;
  stopWhy = "";
  for (int i = 0; i < NZ; i++) {
    stage[i] = 0;
    alertT[i] = -1;
    floodT[i] = -1;
  }
}

// ===== 네트워크 =====
// 1초마다: 수위를 서버 메시지 모양(distA_mm 는 설치 높이 - 수위)으로 보냄. 이상이면 null 과 fault
void sendIngest() {
  if (!*SERVER_URL || WiFi.status() != WL_CONNECTED) return;
  HTTPClient http;
  http.setTimeout(400);
  http.setConnectTimeout(400);  // 서버가 꺼져 있어도 안전 루프(100 ms)를 오래 막지 않음
  if (!http.begin(String(SERVER_URL) + "/api/ingest")) return;
  http.addHeader("Content-Type", "application/json");
  char body[320];
  snprintf(body, sizeof(body),
           "{\"deviceId\":\"%s\",\"bootId\":\"%s\",\"seq\":%lu,\"tMs\":%lu,"
           "\"readings\":{\"distA_mm\":%s,\"distB_mm\":null,\"weight_g\":null},"
           "\"sensorStatus\":{\"A\":\"%s\",\"B\":\"absent\",\"load\":\"absent\"}}",
           DEVICE_ID, bootId.c_str(), (unsigned long)seqNo++, (unsigned long)millis(),
           fault ? "null" : String(INSTALL_HEIGHT_MM - levelMm, 1).c_str(),
           fault ? "fault" : "ok");
  http.POST((uint8_t*)body, strlen(body));
  http.end();
}

// 쌓인 알림을 시리얼에 찍고, 주제가 있으면 ntfy 로 보냄
void sendPush() {
  if (pendingPush.length() == 0) return;
  String msg = pendingPush;
  pendingPush = "";
  Serial.println("[ALERT] " + msg);
  if (!*NTFY_TOPIC || WiFi.status() != WL_CONNECTED) return;
  WiFiClientSecure cli;
  cli.setInsecure();  // 인증서를 확인하지 않음(설계서 방식). 알림 글만 나감
  HTTPClient http;
  http.setTimeout(3000);
  if (!http.begin(cli, String("https://ntfy.sh/") + NTFY_TOPIC)) return;
  http.addHeader("Content-Type", "text/plain; charset=utf-8");
  http.POST((uint8_t*)msg.c_str(), msg.length());
  http.end();
}

// ===== 관제 화면 =====
// 가장 위험한 구역 기준의 대피 안내 문구
String routeText() {
  if (stage[2] >= 1) return "고지대(C)도 위험: 실험을 멈추세요";
  if (stage[1] >= 1) return "주택 골목(B) 침수 예상: 고지대 대피 공간(C)으로 대피";
  if (stage[0] >= 1) return "낮은 도로(A) 침수 예상: 경로 A를 피해 높은 경로 B로 우회";
  return "정상: 경로 A 이용 가능";
}

// GET /api/status: 화면이 1초마다 읽는 현재 상태
void handleStatus() {
  String s;
  s.reserve(900);
  s += "{\"level\":" + String(levelMm, 1) + ",\"mv\":" + String(levelMv, 0);
  s += ",\"fault\":" + String(fault ? "true" : "false");
  s += ",\"rate\":" + String(rate, 4) + ",\"rsrc\":\"" + rateSrc + "\"";
  s += ",\"pred\":[" + String(pred[0], 1) + "," + String(pred[1], 1) + "," + String(pred[2], 1) + "]";
  s += ",\"zones\":[";
  for (int i = 0; i < NZ; i++) {
    if (i) s += ",";
    s += "{\"stage\":" + String(stage[i]) + ",\"eta\":" + String(eta[i], 0) +
         ",\"alertT\":" + String(alertT[i], 0) + ",\"floodT\":" + String(floodT[i], 0) + "}";
  }
  s += "],\"route\":\"" + routeText() + "\",\"why\":\"" + stopWhy + "\"";
  s += ",\"pump\":" + String(pumpOn ? "true" : "false") + ",\"mode\":" + String((int)mode);
  s += ",\"elapsed\":" + String(elapsedS(), 0) + ",\"floatLow\":" + String(floatLow ? "true" : "false");
  s += ",\"areaEst\":" + String(areaEst, 0);
  s += ",\"cfg\":{\"zs\":[" + String(cfg.z[0], 0) + "," + String(cfg.z[1], 0) + "," +
       String(cfg.z[2], 0) + "]";
  s += ",\"maxLevel\":" + String(cfg.maxLevel, 0) + ",\"cautionEta\":" + String(cfg.cautionEta, 0);
  s += ",\"warningEta\":" + String(cfg.warningEta, 0) + ",\"rainOnS\":" + String(cfg.rainOnS, 1);
  s += ",\"rainOffS\":" + String(cfg.rainOffS, 1) + ",\"flow\":" + String(cfg.flowMlS, 2);
  s += ",\"area\":" + String(cfg.areaCm2, 0) + "}}";
  server.send(200, "application/json", s);
}

// GET /api/hist: 최근 120초 수위. 회차 밖이면 1초 이력
void handleHist() {
  String s = "[";
  int n = logN < 120 ? logN : 120;
  if (!running && n == 0) {
    for (int k = 0; k < hN; k++) {
      if (k) s += ",";
      s += String(hist[(hI - hN + k + HN) % HN], 1);
    }
  } else {
    for (int k = logN - n; k < logN; k++) {
      if (k > logN - n) s += ",";
      s += String(logLv[k] / 10.0f, 1);
    }
  }
  s += "]";
  server.send(200, "application/json", s);
}

// GET /log.csv: 이번 회차 기록
void handleLog() {
  String s = "t_s,level_mm,pump\n";
  for (int k = 0; k < logN; k++) {
    s += String(k) + "," + String(logLv[k] / 10.0f, 1) + "," + String(logPump[k]) + "\n";
  }
  server.sendHeader("Content-Disposition", "attachment; filename=smartflood_log.csv");
  server.send(200, "text/csv", s);
}

// GET /api/cmd?c=명령&v=값: 시작·정지·수동·유량 측정·보정
void handleCmd() {
  String c = server.arg("c");
  float v = server.arg("v").toFloat();
  if (c == "stop") {
    stopPump("사용자 정지");
    running = false;
  } else if (c == "start") {
    newRun();
    mode = M_RAIN;
    phaseOn = true;
    phaseSince = millis();
  } else if (c == "rain") {
    if (!running) newRun();
    stopWhy = "";
    mode = M_RAIN;
    phaseOn = true;
    phaseSince = millis();
  } else if (c == "manual") {
    stopWhy = "";
    mode = M_MANUAL;
  } else if (c == "flowtest") {
    stopWhy = "";
    mode = M_FLOWTEST;
    flowTestStart = millis();
  } else if (c == "flowset" && v > 0) {
    cfg.flowMlS = v / 30.0f;
    saveCfg();
  } else if (c == "areaapply" && areaEst > 0) {
    cfg.areaCm2 = areaEst;
    saveCfg();
  } else if (c == "cal1") {
    cfg.cal1mv = levelMv;
    cfg.cal1mm = v;
    cfg.cal1 = true;
    cfg.lvSlope = LEVEL_SLOPE_THEORY;
    cfg.lvOffset = v - cfg.lvSlope * levelMv;
    saveCfg();
  } else if (c == "cal2" && cfg.cal1 && fabs(levelMv - cfg.cal1mv) > 5) {
    cfg.lvSlope = (v - cfg.cal1mm) / (levelMv - cfg.cal1mv);
    cfg.lvOffset = v - cfg.lvSlope * levelMv;
    saveCfg();
  } else if (c == "calreset") {
    Config d;
    cfg.lvSlope = d.lvSlope;
    cfg.lvOffset = d.lvOffset;
    cfg.cal1 = false;
    saveCfg();
  }
  server.send(200, "text/plain", "ok");
}

// GET /api/set?키=값: 기준 높이와 경보 설정 저장
void handleSet() {
  auto get = [](const char* k, float& dst) {
    if (server.hasArg(k)) dst = server.arg(k).toFloat();
  };
  get("z0", cfg.z[0]);
  get("z1", cfg.z[1]);
  get("z2", cfg.z[2]);
  get("maxLevel", cfg.maxLevel);
  get("cautionEta", cfg.cautionEta);
  get("warningEta", cfg.warningEta);
  get("rainOnS", cfg.rainOnS);
  get("rainOffS", cfg.rainOffS);
  if (cfg.rainOnS < 0.5f) cfg.rainOnS = 0.5f;
  if (cfg.rainOffS < 0) cfg.rainOffS = 0;
  saveCfg();
  server.send(200, "text/plain", "ok");
}

// ===== setup / loop =====
void setup() {
  relayWrite(false);  // 부팅 직후 펌프 OFF
  Serial.begin(115200);
  pinMode(PIN_FLOAT, INPUT_PULLUP);
  analogSetPinAttenuation(PIN_LEVEL, ADC_11db);
  loadCfg();
  for (int i = 0; i < NZ; i++) {
    stage[i] = 0;
    alertT[i] = -1;
    floodT[i] = -1;
    eta[i] = -1;
  }
  bootId = String((uint32_t)esp_random(), HEX);

  webOn = strlen(AP_PASS) >= 8;  // WPA2 암호는 8자 이상
  if (*STA_SSID) {
    WiFi.mode(webOn ? WIFI_AP_STA : WIFI_STA);
    WiFi.begin(STA_SSID, STA_PASS);
  } else {
    WiFi.mode(webOn ? WIFI_AP : WIFI_OFF);
  }
  if (!webOn) {
    Serial.println("AP_PASS(secrets.h)가 없어 관제 화면과 펌프 제어를 열지 않음");
    return;
  }
  WiFi.softAP(AP_SSID, AP_PASS);
  Serial.print("관제 화면: http://");
  Serial.println(WiFi.softAPIP().toString());

  server.on("/", []() { server.send_P(200, "text/html; charset=utf-8", PAGE); });
  server.on("/api/status", handleStatus);
  server.on("/api/hist", handleHist);
  server.on("/api/cmd", handleCmd);
  server.on("/api/set", handleSet);
  server.on("/log.csv", handleLog);
  server.begin();
}

void loop() {
  static unsigned long t100 = 0, t1000 = 0;
  if (webOn) server.handleClient();
  if (millis() - t100 >= 100) {
    t100 = millis();
    sample();
    control();
  }
  if (millis() - t1000 >= 1000) {
    t1000 = millis();
    predict();
    Serial.printf("t=%.0f lv=%.1fmm rate=%.2fmm/min eta A=%.0f B=%.0f C=%.0f pump=%d\n",
                  elapsedS(), levelMm, rate * 60, eta[0], eta[1], eta[2], pumpOn);
    sendIngest();
    sendPush();
  }
}
