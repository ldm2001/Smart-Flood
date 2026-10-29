const int BTN = 25;  // 한쪽 GPIO25, 다른쪽 GND. 내부 풀업, 누르면 LOW
int last = HIGH;

void setup() {
  Serial.begin(115200);
  pinMode(BTN, INPUT_PULLUP);
  Serial.println("버튼 시험. 누르면 LOW");
}

void loop() {
  int v = digitalRead(BTN);
  if (v != last) {
    delay(30);  // 디바운스
    if (digitalRead(BTN) == v) {
      last = v;
      Serial.printf("%lu ms %s\n", millis(), v == LOW ? "눌림(LOW)" : "뗌(HIGH)");
    }
  }
  delay(2);
}
