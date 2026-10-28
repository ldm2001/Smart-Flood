const int TRIG = 5;   // 3.3 V 트리거로 동작
const int ECHO = 18;  // 5 V 출력. ECHO-1 kΩ-GPIO18-2 kΩ-GND 분압 뒤에 연결

// 거리 1회 측정(mm). 에코 없으면 0
float distance() {
  digitalWrite(TRIG, LOW);
  delayMicroseconds(5);
  digitalWrite(TRIG, HIGH);
  delayMicroseconds(20);  // 10 µs 이상
  digitalWrite(TRIG, LOW);
  unsigned long us = pulseIn(ECHO, HIGH, 40000UL);  // 40 ms 넘으면 0
  return us * 0.1715f;  // 음속 343 m/s, 왕복이라 0.1715 mm/µs
}

void setup() {
  Serial.begin(115200);
  pinMode(TRIG, OUTPUT);
  pinMode(ECHO, INPUT);
  digitalWrite(TRIG, LOW);
  Serial.println("초음파 시험. 자로 300·400·500 mm 와 150 mm 이하를 재어 기록");
}

void loop() {
  float d = distance();
  if (d == 0) Serial.printf("%lu ms 에코 없음\n", millis());
  else Serial.printf("%lu ms %.0f mm\n", millis(), d);
  delay(200);  // JSN-SR04T 측정 주기 60 ms 이상
}
