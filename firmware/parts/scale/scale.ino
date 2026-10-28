const int DOUT = 32;  // HX711 DT. 모듈 전원은 3V3(DT 레벨이 전원을 따름)
const int CLK = 33;   // HX711 SCK
const long NC = 0x7FFFFFFF;  // 응답 없음 표시
long zero = 0;        // 영점 원시값
float perGram = 1;    // 1 g 당 원시값. 보정 전 1

// HX711 원시값 1회(24비트 부호 있음, 채널 A 이득 128). 0.5초 안에 준비 안 되면 NC
long raw() {
  unsigned long t0 = millis();
  while (digitalRead(DOUT) == HIGH) {
    if (millis() - t0 > 500) return NC;  // 배선 불량이면 DOUT 가 HIGH 로 고정
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
  digitalWrite(CLK, HIGH);  // 25번째 펄스: 다음 변환 채널 A, 이득 128
  delayMicroseconds(1);
  digitalWrite(CLK, LOW);
  interrupts();
  return (v ^ 0x800000L) - 0x800000L;  // 24비트 부호 확장
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

void setup() {
  Serial.begin(115200);
  pinMode(DOUT, INPUT);
  pinMode(CLK, OUTPUT);
  digitalWrite(CLK, LOW);
  Serial.println("HX711 시험. t: 영점, c500: 500 g(물 500 mL) 올린 뒤 보정. 숫자는 실제 무게");
}

void loop() {
  if (Serial.available()) {
    String s = Serial.readStringUntil('\n');
    s.trim();
    if (s == "t") {
      long z = mean(10);
      if (z != NC) zero = z;
      Serial.printf("영점 %ld\n", zero);
    } else if (s.startsWith("c")) {
      float g = s.substring(1).toFloat();
      long v = mean(10);
      if (g > 0 && v != NC) {
        perGram = (v - zero) / g;
        Serial.printf("보정 %.3f /g (%.0f g 기준)\n", perGram, g);
      }
    }
  }
  long v = mean(5);
  if (v == NC) Serial.printf("%lu ms HX711 응답 없음(DOUT HIGH 고정)\n", millis());
  else Serial.printf("%lu ms raw %ld  %.1f g\n", millis(), v, (v - zero) / perGram);
  delay(500);
}
