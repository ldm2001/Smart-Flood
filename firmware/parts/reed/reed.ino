const int REED = 27;  // 플로트 스위치 한쪽 GPIO27, 다른쪽 GND. 내부 풀업
int last = -1;  // 첫 상태도 출력

void setup() {
  Serial.begin(115200);
  pinMode(REED, INPUT_PULLUP);
  Serial.println("플로트 시험. 플로트를 위아래로 돌려 어느 쪽이 '물 있음' 인지 기록");
}

void loop() {
  int v = digitalRead(REED);
  if (v != last) {
    delay(50);  // 리드 스위치 채터링 디바운스
    if (digitalRead(REED) == v) {
      last = v;
      Serial.printf("%lu ms %s\n", millis(), v == LOW ? "닫힘(LOW)" : "열림(HIGH)");
    }
  }
  delay(2);
}
