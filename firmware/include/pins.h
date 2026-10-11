// pins.h – verbindliche GPIO-Belegung für LilyGO T-SIM7080G-S3 V1.0
// Quelle der Wahrheit: docs/pinout.md (Änderungen dort zuerst eintragen!)
//
// Reservierte Pins (NICHT verwenden):
//   4/5   Modem RXD/TXD (UART)
//   6/7/15 PMU IRQ / I2C SCL / I2C SDA (AXP2101)
//   35-37 Octal-SPI-PSRAM
//   41/42 Modem PWRKEY / DTR
//   46    Board-PWRKEY
//   3     Modem RI (nur Eingang, Wake-Reserve)
//   38-40 TF-Kartenslot

#pragma once

// --- I2C (LIS3DH) ---
#define PIN_I2C_SDA          1
#define PIN_I2C_SCL          2
#define LIS3DH_I2C_ADDR      0x18  // SA0 = GND (prüfen!)

// --- Wake-Quellen ---
#define PIN_LIS3DH_INT1      14    // RTC-GPIO, EXT1-Wake
#define PIN_PTT_BUTTON       9     // RTC-GPIO, INPUT_PULLUP, EXT1-Wake
#define PIN_MODEM_RI         3     // Modem-RI (nur Eingang, optionaler Wake)

// --- I2S (geteilte BCLK/WS, Full-Duplex) ---
#define PIN_I2S_BCLK         16
#define PIN_I2S_WS           17
#define PIN_I2S_DOUT         47    // -> MAX98357A DIN
#define PIN_I2S_DIN          48    // <- INMP441 SD
#define PIN_AMP_SD           21    // HIGH = Verstärker aktiv (Left-Channel)
#define PIN_MIC_POWER        10    // Load-Switch: HIGH = Mikrofon versorgt

// --- Piezo (LEDC, gegenphasig) ---
#define PIN_PIEZO_A          11
#define PIN_PIEZO_B          13

// --- Reserve (nicht belegt) ---
// 12, 18, 45, 46

// --- Audio-Parameter (siehe docs/decisions.md D-002) ---
#define AUDIO_SAMPLE_RATE_HZ 8000
#define AUDIO_BITS           16
#define AUDIO_MAX_RECORD_MS  10000  // 10 s -> ~40 kB ADPCM
