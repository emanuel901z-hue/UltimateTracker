// config.h – Tunables des Trackers.
//
// Diese Werte werden später zur Laufzeit aus dem NVS überschrieben
// (Provisioning, docs/optimizations.md B6); hier stehen die Defaults.
// Der Server kann Poll-Intervall und Suchmodus per /sync überschreiben (A5/B4).

#pragma once

#include <cstdint>

// Firmware-Version (geht im Sync an den Server, steuert OTA-Angebote)
static constexpr const char* FIRMWARE_VERSION = "0.1.0";

// Maximale Firmware-Größe für OTA-Downloads (Bytes)
static constexpr uint32_t OTA_MAX_SIZE_BYTES = 2u * 1024u * 1024u;

// --- Poll-Intervalle (Sekunden) ---
static constexpr uint32_t POLL_INTERVAL_S_DEFAULT = 900;   // 15 min
static constexpr uint32_t POLL_INTERVAL_S_SEARCH = 60;     // Suchmodus
static constexpr uint32_t POLL_INTERVAL_S_LOW_BATT = 1800; // < 15 % Akku

// --- Motion-Wake-Drossel (Vorgabe: maximal 3 Minuten, optimizations.md B2) ---
static constexpr uint32_t MOTION_MIN_SLEEP_S = 180;
static constexpr uint8_t MOTION_REQUIRED_SAMPLES = 2;  // aufeinanderfolgende Treffer
static constexpr uint16_t MOTION_THRESHOLD_MG = 200;   // LIS3DH-Schwellwert (Milli-g)

// --- Audio ---
static constexpr uint32_t AUDIO_MAX_RECORD_MS = 10000;  // 10 s ≈ 40 kB ADPCM
static constexpr uint8_t AUDIO_VOLUME_PERCENT = 80;     // Lautstärkegrenze (Kinderohren)

// --- Modem-Power-Strategie (optimizations.md B1): 0=aus, 1=PSM, 2=eDRX registriert ---
static constexpr uint8_t MODEM_POWER_MODE = 0;

// --- Akku ---
static constexpr uint8_t BATTERY_LOW_PERCENT = 15;
