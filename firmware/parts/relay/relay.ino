const int RLY = 26;  // 릴레이 IN. VCC 5V, GND 공통. 12 V 는 COM·NO 접점에만
bool on = false;

// 릴레이 켬·끔. 켤 때 OUTPUT LOW, 끌 때 입력으로 풀어 모듈 풀업이 끄게 함(board.ino 와 같음)
void relay(bool v) {
  if (v) {
    digitalWrite(RLY, LOW);
    pinMode(RLY, OUTPUT);
    digitalWrite(RLY, LOW);
  } else {
    pinMode(RLY, INPUT);
  }
}

void setup() {
  Serial.begin(115200);
  relay(false);
  Serial.println("릴레이 시험. 3초마다 켬(OUTPUT LOW)·끔(입력) 반복. 딸깍 소리·LED 기록");
}

void loop() {
  relay(on);
  Serial.printf("%lu ms IN=%s\n", millis(), on ? "LOW" : "HIGHZ");
  on = !on;
  delay(3000);
}
