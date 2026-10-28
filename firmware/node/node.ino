const int BTN = 25;   // 펌프 요청 반전
const int REED = 27;  // 플로트
const int RLY = 26;   // 릴레이 IN
const int TRIG = 5;
const int ECHO = 18;  // 분압 뒤
const int DOUT = 32;
const int CLK = 33;
const int RLY_ON = LOW;    // 릴레이가 켜지는 레벨. parts/relay 결과대로
const int WET = LOW;       // 플로트 '물 있음' 레벨. parts/reed 결과대로
const long NC = 0x7FFFFFFF;
const long ZERO = 0;       // parts/scale 의 영점
const float PER_GRAM = 1;  // parts/scale 의 보정값(원시값/g)

char bootId[9];
unsigned long seq = 0;
unsigned long next = 0;  // 다음 발행 시각(ms)
bool want = false;       // 버튼으로 바꾸는 펌프 요청
int lastBtn = HIGH;

// 거리 1회 측정(mm). 에코 없으면 0
float distance() {
  digitalWrite(TRIG, LOW);
  delayMicroseconds(5);
  digitalWrite(TRIG, HIGH);
  delayMicroseconds(20);
  digitalWrite(TRIG, LOW);
  unsigned long us = pulseIn(ECHO, HIGH, 40000UL);
  return us * 0.1715f;
}

// HX711 원시값 1회. 0.5초 안에 준비 안 되면 NC
long raw() {
  unsigned long t0 = millis();
  while (digitalRead(DOUT) == HIGH) {
    if (millis() - t0 > 500) return NC;
  }
  long v = 0;
  noInterrupts();
  for (int i = 0; i < 24; i++) {
    digitalWrite(CLK, HIGH);
    delayMicroseconds(1);
    v = (v << 1) | digitalRead(DOUT);
    digitalWrite(CLK, LOW);
    delayMicroseconds(1);
  }
  digitalWrite(CLK, HIGH);  // 25번째 펄스: 채널 A 이득 128
  delayMicroseconds(1);
  digitalWrite(CLK, LOW);
  interrupts();
  return (v ^ 0x800000L) - 0x800000L;
}

// n회 평균. 한 번이라도 NC 면 NC
long mean(int n) {
  long s = 0;
  for (int i = 0; i < n; i++) {
    long v = raw();
    if (v == NC) return NC;
    s += v;
  }
  return s / n;
}

// JSON 숫자 또는 null
String num(float v) {
  return isnan(v) ? String("null") : String(v, 1);
}

// 버튼 눌림 1회마다 펌프 요청 반전
void button() {
  int v = digitalRead(BTN);
  if (v == lastBtn) return;
  delay(30);  // 디바운스
  if (digitalRead(BTN) != v) return;
  lastBtn = v;
  if (v == LOW) want = !want;
}

// 서버 메시지 모양(docs/api-contract.md 장치 입력)으로 한 줄. B 는 센서가 없어 null
void publish(bool wet, bool run) {
  float d = distance();
  float dist = d > 0 ? d : NAN;
  long w = mean(3);
  float grams = w == NC ? NAN : (w - ZERO) / PER_GRAM;
  Serial.printf("{\"deviceId\":\"esp32_1\",\"bootId\":\"%s\",\"seq\":%lu,\"tMs\":%lu,"
                "\"readings\":{\"distA_mm\":%s,\"distB_mm\":null,\"weight_g\":%s},"
                "\"sensorStatus\":{\"A\":\"%s\",\"B\":\"none\",\"load\":\"%s\"},"
                "\"pump\":%s,\"floatSwitch\":\"%s\"}\n",
                bootId, seq, millis(), num(dist).c_str(), num(grams).c_str(),
                d > 0 ? "ok" : "no_echo", w == NC ? "nc" : "ok", run ? "true" : "false",
                wet ? "wet" : "dry");
  seq++;
}

void setup() {
  Serial.begin(115200);
  pinMode(BTN, INPUT_PULLUP);
  pinMode(REED, INPUT_PULLUP);
  pinMode(RLY, OUTPUT);
  digitalWrite(RLY, !RLY_ON);
  pinMode(TRIG, OUTPUT);
  digitalWrite(TRIG, LOW);
  pinMode(ECHO, INPUT);
  pinMode(DOUT, INPUT);
  pinMode(CLK, OUTPUT);
  digitalWrite(CLK, LOW);
  snprintf(bootId, sizeof bootId, "%08x", esp_random());
  next = millis() + 1000;
}

void loop() {
  button();
  bool wet = digitalRead(REED) == WET;
  bool run = want && wet;  // 급수통에 물이 있을 때만 펌프
  digitalWrite(RLY, run ? RLY_ON : !RLY_ON);
  if ((long)(millis() - next) >= 0) {
    next += 1000;
    publish(wet, run);
  }
  delay(2);
}
