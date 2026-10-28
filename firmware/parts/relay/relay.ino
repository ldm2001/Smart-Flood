const int RLY = 26;  // 릴레이 IN. VCC 5V, GND 공통. 12 V 는 COM·NO 접점에만
int level = HIGH;  // active-LOW 모듈이면 HIGH 가 꺼짐

void setup() {
  Serial.begin(115200);
  pinMode(RLY, OUTPUT);
  digitalWrite(RLY, level);
  Serial.println("릴레이 시험. 3초마다 IN 반전. 딸깍 소리·LED 가 어느 레벨에서 켜지는지 기록");
}

void loop() {
  digitalWrite(RLY, level);
  Serial.printf("%lu ms IN=%s\n", millis(), level == HIGH ? "HIGH" : "LOW");
  level = !level;
  delay(3000);
}
