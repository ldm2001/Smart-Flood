const int AIN = 34;  // 입력 전용. 변환보드 출력이 3.3 V 를 넘지 않는지 멀티미터로 먼저 확인

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);
  analogSetPinAttenuation(AIN, ADC_11db);  // 약 0~3.1 V
  Serial.println("수위 변환보드 시험. 물 깊이 두 점에서 mV 기록");
}

void loop() {
  long raw = 0, mv = 0;
  for (int i = 0; i < 32; i++) {
    raw += analogRead(AIN);
    mv += analogReadMilliVolts(AIN);
  }
  Serial.printf("%lu ms raw %ld  %ld mV\n", millis(), raw / 32, mv / 32);
  delay(500);
}
