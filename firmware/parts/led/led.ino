const int LED = 2;  // 보드 LED. 없으면 GPIO2-330 Ω-LED-GND
unsigned long n = 0;

void setup() {
  Serial.begin(115200);
  pinMode(LED, OUTPUT);
  delay(500);
  Serial.printf("chip %s, cpu %u MHz, heap %u B\n", ESP.getChipModel(), ESP.getCpuFreqMHz(),
                ESP.getFreeHeap());
}

void loop() {
  digitalWrite(LED, n % 2);
  Serial.printf("%lu ms tick %lu\n", millis(), n);
  n++;
  delay(500);
}
