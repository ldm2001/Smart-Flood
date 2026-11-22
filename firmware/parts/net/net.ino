#include <WiFi.h>
#include <HTTPClient.h>

// 시리얼 모니터에서 한 줄 입력(줄 끝 New Line) 받음
String line(const char* ask) {
  Serial.print(ask);
  while (!Serial.available()) delay(10);
  String s = Serial.readStringUntil('\n');
  s.trim();
  Serial.println(s.length() ? "(입력됨)" : "(빈 줄)");
  return s;
}

void setup() {
  Serial.begin(115200);
  Serial.setTimeout(2000);
  delay(500);
  String ssid = line("SSID? ");
  String pass = line("암호? ");
  String url = line("서버 URL? (예 http://192.168.0.10:8000/api/state) ");
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid.c_str(), pass.c_str());
  Serial.print("연결 중");
  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 20000) {
    delay(500);
    Serial.print('.');
  }
  if (WiFi.status() != WL_CONNECTED) {
    Serial.printf("\n20초 안에 못 붙음. status %d. SSID·암호 다시 확인\n", WiFi.status());
    return;
  }
  Serial.printf("\nIP %s, RSSI %d dBm\n", WiFi.localIP().toString().c_str(), WiFi.RSSI());
  HTTPClient http;
  http.begin(url);
  int code = http.GET();  // 서버는 --host 0.0.0.0 으로 띄워야 닿음
  Serial.printf("GET %s -> %d\n", url.c_str(), code);
  if (code > 0) Serial.println(http.getString().substring(0, 200));
  http.end();
}

void loop() {
  delay(5000);
  Serial.printf("%lu ms WiFi %s, RSSI %d dBm\n", millis(),
                WiFi.status() == WL_CONNECTED ? "연결" : "끊김", WiFi.RSSI());
}
