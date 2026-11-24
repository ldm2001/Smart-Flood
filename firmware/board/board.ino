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
const unsigned long REJOIN_MS = 10000;  // 와이파이가 끊긴 채면 이 간격으로 다시 붙어 봄

// ===== 제어 감시 =====
const unsigned long GUARD_MS = 100;   // 감시 태스크가 깨어나는 간격
const unsigned long STALL_MS = 1000;  // control() 이 이만큼 넘게 안 돌면 감시 태스크가 펌프를 끔

// ===== 수위센서 =====
// 0~5000 mm 가 4~20 mA 이고 변환보드 120 Ω 에서 2.604 mm/mV, 0 mm 에서 480 mV
const float LEVEL_SLOPE_THEORY = 5000.0f / 16.0f / 120.0f;
const float LEVEL_MV_AT_ZERO = 480.0f;
const float FAULT_LOW_MV = 300.0f;    // 이 아래는 단선이나 전원 이상
const float FAULT_HIGH_MV = 2800.0f;  // 이 위는 단락이나 과전압
const int GOOD_READS = 32;            // 64번 중 범위 안 읽기가 이보다 적은 묶음은 수위에 안 넣음

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
bool webOn = false;  // 관제 화면 열림 여부(AP 암호가 있을 때만)

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
float goodMv = 0;  // 300~2800 mV 안의 읽기만 이동평균한 전압. 수위와 보정에 씀
bool fault = false;
bool floatLow = false;
float rateMeas = 0, rateModel = 0, rate = 0;  // mm/s
String rateSrc = "-";
float pred[3] = {0, 0, 0};     // +10, +20, +30 초 뒤의 예측 수위
float eta[NZ];                 // 침수까지 남은 초(-1 은 상승 없음, 0 은 이미 침수)
int stage[NZ];                 // 0 정상, 1 주의, 2 경계, 3 침수
float alertT[NZ], floodT[NZ];  // 첫 경보와 실제 침수 시각(회차 경과 초, -1 은 없음)
float areaEst = 0;

const int HN = 30, REG = 20;
float hist[HN];  // 1초 이력. 센서 이상인 초는 빈 칸(NAN)
int hN = 0, hI = 0;
int regN = 0;  // 회귀 창 안의 유효 표본 수(빈 칸 뺌)
const int LOGN = 1800;  // 실험 기록(1초 간격, 최대 30분)
int16_t logLv[LOGN];
uint8_t logPump[LOGN];
int logN = 0;

String pendingPush = "";
String bootId;
uint32_t seqNo = 0;
int sendCode = 1;  // 마지막으로 찍은 전송 결과. HTTP 코드, 음수는 오류, 0 은 주소 틀림, 1 은 없음

volatile bool relayOn = false;    // relay() 가 마지막으로 건 상태(감시 태스크가 읽음)
volatile unsigned long beat = 0;  // control() 이 마지막으로 돈 시각(ms)
volatile bool stall = false;      // 감시 태스크가 릴레이를 끈 뒤 pump() 가 다시 걸 때까지 true

// ===== 릴레이 =====
// 릴레이를 켜거나 끔. 끌 때 RELAY_OFF_HIGHZ 면 핀을 입력으로 풀어 모듈의 풀업이 끄게 함
// 건 상태는 relayOn 에 남김(감시 태스크가 읽음)
void relay(bool on) {
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
  relayOn = on;
}

// 펌프 상태를 바꾸고 가동 시간을 쌓음. 감시 태스크가 릴레이를 꺼 두었으면 요청 상태로 다시 걸고
// 시리얼에 한 줄 찍음
void pump(bool on) {
  if (stall) {  // 감시 태스크가 꺼 둔 릴레이를 요청 상태로 다시 걺
    stall = false;
    relay(on);
    Serial.printf("[GUARD] 제어 루프가 %lu ms 넘게 늦어 그동안 펌프를 꺼 둠\n", STALL_MS);
  }
  if (on == pumpOn) return;
  if (on) pumpOnSince = millis();
  else pumpOnTotalS += (millis() - pumpOnSince) / 1000.0f;
  pumpOn = on;
  relay(on);
}

// 펌프를 끄고 멈춘 까닭을 남김
void cutoff(const String& why) {
  mode = M_STOP;
  pump(false);
  stopWhy = why;
  Serial.println("[STOP] " + why);
}

// ===== 저장 =====
// 설정을 플래시에 저장
void commit() {
  prefs.begin("flood2", false);
  prefs.putBytes("cfg", &cfg, sizeof(cfg));
  prefs.end();
}

// 플래시의 설정을 읽음. 크기가 다르면(펌웨어가 바뀜) 기본값을 씀
void recall() {
  prefs.begin("flood2", true);
  if (prefs.getBytesLength("cfg") == sizeof(cfg)) prefs.getBytes("cfg", &cfg, sizeof(cfg));
  prefs.end();
}

// ===== 측정 =====
// 수위센서 전압(mV). 64번 읽은 평균
// good 에는 300~2800 mV 안의 읽기만의 평균. 그런 읽기가 GOOD_READS 번보다 적으면 NAN
float voltage(float& good) {
  uint32_t s = 0, gs = 0;
  int gn = 0;
  for (int i = 0; i < 64; i++) {
    uint32_t v = analogReadMilliVolts(PIN_LEVEL);
    s += v;
    if (v >= FAULT_LOW_MV && v <= FAULT_HIGH_MV) {  // 범위 안 읽기만 따로 모음
      gs += v;
      gn++;
    }
  }
  good = gn >= GOOD_READS ? (float)gs / gn : NAN;
  return s / 64.0f;
}

// 100 ms 마다: 전압을 이동평균하고 수위(mm)와 플로트 상태를 갱신
// levelMv 는 모든 읽기의 평균(센서 이상 판정), goodMv 는 300~2800 mV 안의 읽기만의 평균(수위)
void sample() {
  float good;
  float mv = voltage(good);
  levelMv = (levelMv == 0) ? mv : levelMv * 0.85f + mv * 0.15f;
  fault = (levelMv < FAULT_LOW_MV || levelMv > FAULT_HIGH_MV);
  if (!isnan(good)) {  // 범위 안 읽기가 모자란 묶음은 수위를 움직이지 않음
    goodMv = (goodMv == 0) ? good : goodMv * 0.85f + good * 0.15f;
  }
  levelMm = cfg.lvSlope * goodMv + cfg.lvOffset;
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

// 최근 REG 초의 선형회귀 기울기(mm/s). 빈 칸은 건너뛰고 x 는 칸 번호 그대로 씀
// 유효 표본 수를 regN 에 남김. 5개 미만이면 0
float regression() {
  int n = hN < REG ? hN : REG;
  regN = 0;
  float sx = 0, sy = 0, sxx = 0, sxy = 0;
  for (int k = 0; k < n; k++) {
    float y = hist[(hI - n + k + HN) % HN], x = k;
    if (isnan(y)) continue;
    regN++;
    sx += x;
    sy += y;
    sxx += x * x;
    sxy += x * y;
  }
  if (regN < 5) return 0;
  float d = regN * sxx - sx * sx;
  return d == 0 ? 0 : (regN * sxy - sx * sy) / d;
}

// 단계가 오른 구역의 알림 문구를 쌓음
void alert(int zi, int st) {
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
// 센서 이상인 초는 이력에 빈 칸(NAN)을 두고 기록 한 줄만 남김. 속도·예측·단계는 그대로 둠
void forecast() {
  hist[hI] = fault ? NAN : levelMm;
  hI = (hI + 1) % HN;
  if (hN < HN) hN++;
  if (running && logN < LOGN) {  // 센서 이상인 초에도 붙잡아 둔 수위로 한 줄
    logLv[logN] = (int16_t)(levelMm * 10);
    logPump[logN] = pumpOn ? 1 : 0;
    logN++;
  }
  if (fault) return;  // 속도·예측 수위·남은 초·단계·면적 추정을 지난 값 그대로 둠
  rateMeas = regression();
  float flowMmS = (cfg.flowMlS > 0 && cfg.areaCm2 > 0) ? cfg.flowMlS / cfg.areaCm2 * 10.0f : 0;
  rateModel = flowMmS * duty();
  // 측정 이력이 충분하고 실제로 오르고 있으면 측정값, 아니면 펌프 유량 기반 모델값
  if (regN >= 15 && rateMeas > 0.01f) {
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
    if (running && st > stage[i]) {  // 회차 중에는 단계를 내리지 않음
      if (stage[i] == 0 && alertT[i] < 0) alertT[i] = t;
      if (st == 3 && floodT[i] < 0) floodT[i] = t;
      stage[i] = st;
      alert(i, st);
    }
    if (!running) stage[i] = st;
  }

  float rise = levelMm - levelAtStart;
  float pumpedMl = (pumpOnTotalS + (pumpOn ? (millis() - pumpOnSince) / 1000.0f : 0)) * cfg.flowMlS;
  areaEst = (running && rise > 5 && pumpedMl > 0) ? pumpedMl / (rise / 10.0f) : 0;
}

// ===== 펌프 제어와 안전 =====
// 100 ms 마다: 안전 조건이 하나라도 걸리면 펌프를 끄고, 아니면 모드대로 돌림
void control() {
  beat = millis();  // 감시 태스크가 보는 마지막으로 돈 시각
  if (mode == M_STOP) {
    pump(false);
    return;
  }
  if (floatLow) {
    cutoff("급수통 물 부족(플로트)");
    return;
  }
  if (mode != M_MANUAL && mode != M_FLOWTEST && fault) {
    cutoff("수위센서 이상(12V·배선 확인)");
    return;
  }
  if (!fault && levelMm >= cfg.maxLevel && mode != M_FLOWTEST) {
    cutoff("안전 최대 수위 도달");
    return;
  }
  if (pumpOn && millis() - pumpOnSince > cfg.pumpMaxOnS * 1000UL) {
    cutoff("연속 가동 시간 초과");
    return;
  }
  if (running && elapsedS() > cfg.runMaxS) {
    cutoff("실험 최대 시간 초과");
    return;
  }

  if (mode == M_MANUAL) {
    pump(true);
    return;
  }
  if (mode == M_FLOWTEST) {
    if (millis() - flowTestStart >= 30000UL) {
      cutoff("유량 측정 30초 완료");
      return;
    }
    pump(true);
    return;
  }
  if (mode == M_RAIN) {
    unsigned long ph = (phaseOn ? cfg.rainOnS : cfg.rainOffS) * 1000UL;
    if (millis() - phaseSince >= ph) {
      phaseOn = !phaseOn;
      phaseSince = millis();
    }
    pump(phaseOn);
  }
}

// 제어 감시 태스크(코어 0, loop 보다 높은 우선순위). 릴레이가 켜진 채 control() 이 STALL_MS
// 넘게 안 돌면 릴레이를 끄고 stall 을 세움. 보드 리셋이나 회차 끝냄은 없음
void guard(void*) {
  for (;;) {
    if (relayOn) {
      unsigned long b = beat;  // millis() 보다 먼저 읽어 b 가 지금보다 늦지 않음
      if (millis() - b > STALL_MS) {
        relay(false);  // 릴레이를 먼저 끄고 표시는 나중
        stall = true;
      }
    }
    vTaskDelay(pdMS_TO_TICKS(GUARD_MS));
  }
}

// 새 회차를 시작: 기록과 단계를 비움
void run() {
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
// 1초마다: 와이파이 연결이 바뀌면 시리얼에 찍음(SSID 는 찍지 않음). 끊긴 뒤 10초는 코어의 자동
// 재접속에 맡기고, 그 뒤로는 REJOIN_MS 마다 다시 붙어 봄. 부팅 때 공유기가 없던 경우도 같음
void wifi() {
  if (!*STA_SSID) return;
  static int was = -1;             // 지난번 연결 여부. -1 은 아직 모름
  static unsigned long tried = 0;  // 끊김을 보거나 다시 붙어 본 시각
  bool up = WiFi.status() == WL_CONNECTED;
  if (up != was) {
    was = up;
    tried = millis();
    sendCode = 1;  // 다시 붙은 뒤 첫 전송 결과를 다시 찍음
    if (up) Serial.println("와이파이 연결: " + WiFi.localIP().toString());
    else Serial.println("와이파이 연결 안 됨. 10초마다 다시 붙어 봄");
  }
  if (!up && millis() - tried >= REJOIN_MS) {
    tried = millis();
    WiFi.reconnect();
  }
}

// 전송 결과가 지난번과 다를 때만 시리얼에 찍음
void outcome(int code) {
  if (code == sendCode) return;
  sendCode = code;
  if (code > 0) Serial.printf("서버 전송 HTTP %d\n", code);
  else if (code == 0) Serial.println("서버 주소를 읽지 못함. SERVER_URL 은 http://IP:8000 꼴");
  else Serial.println("서버 전송 실패: " + HTTPClient::errorToString(code));
}

// 서버로 보낼 본문 하나(대기열 칸). 포인터 없이 통째로 복사됨
struct Packet {
  char body[320];  // 가장 긴 본문 234 B(센서 이상, seq·tMs 10자리, running false)
};
QueueHandle_t bodyQ = nullptr;  // 서버 전송 대기열(길이 1, 새 본문이 옛 본문을 덮음)
volatile int replyCode = 1;     // 전송 태스크가 남긴 마지막 결과
volatile uint32_t replyN = 0;   // 전송 태스크가 결과를 남길 때마다 1 늚

// 서버 전송 태스크. 대기열의 본문을 POST /api/ingest 로 보내고 결과만 남김(시리얼에 찍지 않음)
void sender(void*) {
  size_t n = strlen(SERVER_URL);
  while (n > 0 && SERVER_URL[n - 1] == '/') n--;  // 끝의 / 를 빼고 붙여 //api 가 되지 않음
  char url[200];
  snprintf(url, sizeof(url), "%.*s/api/ingest", (int)n, SERVER_URL);
  for (;;) {
    Packet p;
    if (xQueueReceive(bodyQ, &p, portMAX_DELAY) != pdTRUE) continue;
    HTTPClient http;
    http.setTimeout(400);
    http.setConnectTimeout(400);  // 서버가 꺼져 있어도 다음 본문을 오래 미루지 않음
    int code = 0;                 // 주소를 읽지 못하면 0
    if (http.begin(String(url))) {
      http.addHeader("Content-Type", "application/json");
      code = http.POST((uint8_t*)p.body, strlen(p.body));
      http.end();
    }
    replyCode = code;
    replyN = replyN + 1;  // 결과를 먼저 쓰고 번호를 나중에 올림
  }
}

// 1초마다: 수위를 서버 메시지 모양(distA_mm 는 설치 높이 - 수위)으로 만들어 전송 대기열에 넣음
// 이상이면 null 과 fault. floatSwitch 는 급수통 물 부족이면 low, 아니면 normal
// running 은 회차가 열려 있으면 true(안전 정지 중에도), 정지 명령 뒤 false
// 서버가 보드 회차를 따라가는 데 씀. 보내기는 sender 태스크 몫이라 loop 는 서버를 기다리지 않음
void ingest() {
  if (!*SERVER_URL || WiFi.status() != WL_CONNECTED) return;
  if (!bodyQ) {
    bodyQ = xQueueCreate(1, sizeof(Packet));
    if (!bodyQ) return;
    xTaskCreatePinnedToCore(sender, "sender", 8192, nullptr, 1, nullptr, 0);
  }
  Packet p;
  snprintf(p.body, sizeof(p.body),
           "{\"deviceId\":\"%s\",\"bootId\":\"%s\",\"seq\":%lu,\"tMs\":%lu,"
           "\"readings\":{\"distA_mm\":%s,\"distB_mm\":null,\"weight_g\":null},"
           "\"sensorStatus\":{\"A\":\"%s\",\"B\":\"absent\",\"load\":\"absent\"},"
           "\"floatSwitch\":\"%s\",\"running\":%s}",
           DEVICE_ID, bootId.c_str(), (unsigned long)seqNo++, (unsigned long)millis(),
           fault ? "null" : String(INSTALL_HEIGHT_MM - levelMm, 1).c_str(),
           fault ? "fault" : "ok", floatLow ? "low" : "normal", running ? "true" : "false");
  xQueueOverwrite(bodyQ, &p);  // 앞 본문이 아직 안 나갔으면 새 본문으로 덮음
}

// 1초마다: 전송 태스크가 새 결과를 남겼으면 outcome 으로 넘김
void result() {
  static uint32_t last = 0;  // 마지막으로 넘긴 결과 번호
  uint32_t n = replyN;
  if (n == last) return;
  last = n;
  outcome(replyCode);
}

QueueHandle_t pushQ = nullptr;  // ntfy 전송 대기열(글 사본 포인터)
bool pushDrop = false;          // 대기열 가득 참 안내 1회 여부

// ntfy 전송 태스크. 대기열의 글을 HTTPS 로 보냄(loop·control 과 따로 돎)
void ntfy(void*) {
  for (;;) {
    char* msg = nullptr;
    if (xQueueReceive(pushQ, &msg, portMAX_DELAY) != pdTRUE || !msg) continue;
    if (WiFi.status() == WL_CONNECTED) {
      WiFiClientSecure cli;
      cli.setInsecure();  // 인증서를 확인하지 않음(설계서 방식). 알림 글만 나감
      HTTPClient http;
      http.setTimeout(3000);
      if (http.begin(cli, String("https://ntfy.sh/") + NTFY_TOPIC)) {
        http.addHeader("Content-Type", "text/plain; charset=utf-8");
        http.POST((uint8_t*)msg, strlen(msg));
        http.end();
      }
    }
    free(msg);
  }
}

// 쌓인 알림을 시리얼에 찍고, 주제가 있으면 ntfy 대기열에 넣음(가득 차면 버림)
void push() {
  if (pendingPush.length() == 0) return;
  String msg = pendingPush;
  pendingPush = "";
  Serial.println("[ALERT] " + msg);
  if (!*NTFY_TOPIC || WiFi.status() != WL_CONNECTED) return;
  if (!pushQ) {
    pushQ = xQueueCreate(4, sizeof(char*));
    if (!pushQ) return;
    xTaskCreatePinnedToCore(ntfy, "push", 8192, nullptr, 1, nullptr, 0);
  }
  char* copy = strdup(msg.c_str());
  if (!copy) return;
  if (xQueueSend(pushQ, &copy, 0) != pdTRUE) {
    free(copy);
    if (!pushDrop) Serial.println("[ALERT] ntfy 대기열 가득 참: 알림 버림");
    pushDrop = true;
  }
}

// ===== 관제 화면 =====
// 가장 위험한 구역 기준의 대피 안내 문구
String guidance() {
  if (stage[2] >= 1) return "고지대(C)도 위험: 실험을 멈추세요";
  if (stage[1] >= 1) return "주택 골목(B) 침수 예상: 고지대 대피 공간(C)으로 대피";
  if (stage[0] >= 1) return "낮은 도로(A) 침수 예상: 경로 A를 피해 높은 경로 B로 우회";
  return "정상: 경로 A 이용 가능";
}

// GET /api/status: 화면이 1초마다 읽는 현재 상태
void status() {
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
  s += "],\"route\":\"" + guidance() + "\",\"why\":\"" + stopWhy + "\"";
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

// GET /api/hist: 최근 120초 수위. 회차 밖이면 1초 이력(빈 칸은 뺌)
void history() {
  String s = "[";
  int n = logN < 120 ? logN : 120;
  if (!running && n == 0) {
    for (int k = 0; k < hN; k++) {
      float y = hist[(hI - hN + k + HN) % HN];
      if (isnan(y)) continue;  // JSON 에 nan 이 들어가지 않음
      if (s.length() > 1) s += ",";
      s += String(y, 1);
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
void csv() {
  String s = "t_s,level_mm,pump\n";
  for (int k = 0; k < logN; k++) {
    s += String(k) + "," + String(logLv[k] / 10.0f, 1) + "," + String(logPump[k]) + "\n";
  }
  server.sendHeader("Content-Disposition", "attachment; filename=smartflood_log.csv");
  server.send(200, "text/csv", s);
}

// GET /api/cmd?c=명령&v=값: 시작·정지·수동·유량 측정·보정
void cmd() {
  String c = server.arg("c");
  float v = server.arg("v").toFloat();
  if (c == "stop") {
    cutoff("사용자 정지");
    running = false;
  } else if (c == "start") {
    run();
    mode = M_RAIN;
    phaseOn = true;
    phaseSince = millis();
  } else if (c == "rain") {
    if (!running) run();
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
    commit();
  } else if (c == "areaapply" && areaEst > 0) {
    cfg.areaCm2 = areaEst;
    commit();
  } else if (c == "cal1") {
    cfg.cal1mv = goodMv;
    cfg.cal1mm = v;
    cfg.cal1 = true;
    cfg.lvSlope = LEVEL_SLOPE_THEORY;
    cfg.lvOffset = v - cfg.lvSlope * goodMv;
    commit();
  } else if (c == "cal2" && cfg.cal1 && fabs(goodMv - cfg.cal1mv) > 5) {
    cfg.lvSlope = (v - cfg.cal1mm) / (goodMv - cfg.cal1mv);
    cfg.lvOffset = v - cfg.lvSlope * goodMv;
    commit();
  } else if (c == "calreset") {
    Config d;
    cfg.lvSlope = d.lvSlope;
    cfg.lvOffset = d.lvOffset;
    cfg.cal1 = false;
    commit();
  }
  server.send(200, "text/plain", "ok");
}

// GET /api/set?키=값: 기준 높이와 경보 설정 저장
void settings() {
  auto param = [](const char* k, float& dst) {
    if (server.hasArg(k)) dst = server.arg(k).toFloat();
  };
  param("z0", cfg.z[0]);
  param("z1", cfg.z[1]);
  param("z2", cfg.z[2]);
  param("maxLevel", cfg.maxLevel);
  param("cautionEta", cfg.cautionEta);
  param("warningEta", cfg.warningEta);
  param("rainOnS", cfg.rainOnS);
  param("rainOffS", cfg.rainOffS);
  if (cfg.rainOnS < 0.5f) cfg.rainOnS = 0.5f;
  if (cfg.rainOffS < 0) cfg.rainOffS = 0;
  commit();
  server.send(200, "text/plain", "ok");
}

// 관제 화면 요청 거르기. 보드 AP 주소로 들어왔고 AP 대역에서 보낸 요청만 받음
// lwIP 는 공유기 쪽으로 들어온 AP 주소 요청도 받으므로 두 조건을 다 봄
bool gate(WebServer& web) {
  NetworkClient& c = web.client();
  IPAddress ap = WiFi.softAPIP(), local = c.localIP(), peer = c.remoteIP();
  if (ap.type() != IPv4 || local.type() != IPv4 || peer.type() != IPv4) return false;
  uint32_t mask = WiFi.softAPSubnetMask();
  return local == ap && (uint32_t(peer) & mask) == (uint32_t(ap) & mask);
}

// ===== setup / loop =====
void setup() {
  relay(false);  // 부팅 직후 펌프 OFF
  Serial.begin(115200);
  pinMode(PIN_FLOAT, INPUT_PULLUP);
  analogSetPinAttenuation(PIN_LEVEL, ADC_11db);
  recall();
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
    Serial.println("AP_PASS 가 없거나 8자 미만이라 SMART_FLOOD 와이파이와 관제 화면을 열지 않음");
    Serial.println("같은 폴더의 secrets.h.example 을 secrets.h 로 복사해 다시 올리면 열림");
    xTaskCreatePinnedToCore(guard, "guard", 4096, nullptr, 2, nullptr, 0);  // 제어 감시
    return;
  }
  WiFi.softAP(AP_SSID, AP_PASS);
  Serial.print("관제 화면: http://");
  Serial.println(WiFi.softAPIP().toString());

  // 경로마다 gate 로 걸러 SMART_FLOOD 쪽 요청만 받음
  server.on("/", []() { server.send_P(200, "text/html; charset=utf-8", PAGE); }).setFilter(gate);
  server.on("/api/status", status).setFilter(gate);
  server.on("/api/hist", history).setFilter(gate);
  server.on("/api/cmd", cmd).setFilter(gate);
  server.on("/api/set", settings).setFilter(gate);
  server.on("/log.csv", csv).setFilter(gate);
  server.onNotFound([]() {  // 거른 요청과 없는 경로. 화면을 여는 곳만 알려 줌
    server.send(404, "text/plain; charset=utf-8",
                "관제 화면: http://" + WiFi.softAPIP().toString() + " (와이파이 " + AP_SSID +
                    " 에 붙은 기기에서만 열림)");
  });
  server.begin();
  xTaskCreatePinnedToCore(guard, "guard", 4096, nullptr, 2, nullptr, 0);  // 제어 감시
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
    forecast();
    Serial.printf("t=%.0f lv=%.1fmm rate=%.2fmm/min eta A=%.0f B=%.0f C=%.0f pump=%d\n",
                  elapsedS(), levelMm, rate * 60, eta[0], eta[1], eta[2], pumpOn);
    result();  // 지난 초에 끝난 전송 결과를 wifi() 가 sendCode 를 지우기 전에 찍음
    wifi();
    ingest();
    push();
  }
}
