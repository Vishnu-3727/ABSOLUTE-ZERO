---
tags: [research, drone, navigation, localization, ardupilot]
project: ASUNAMA
status: active
confidence: high
date: 2026-07-09
summary: ArduPilot non-GPS vision-positioning params — EK3_SRC1, VISO_TYPE, VISION_POSITION_ESTIMATE, EKF origin.
---

# ArduPilot non-GPS vision positioning — parameters

For ASUNAMA's vision-anchored EKF fix (feeds `deployment/fc_setup.py`).

## Core params (EKF source set 1)
- `GPS1_TYPE = 0` — disable GPS.
- `VISO_TYPE = 1` — enable visual odometry (**1, not 3**; 3 = VOXL — confirms the
  fc_setup fix). See [[gps-denied-localization]].
- `EK3_SRC1_POSXY = 6` (ExternalNav), `EK3_SRC1_POSZ = 6` or `1` (Baro).
- `EK3_SRC1_VELXY = 6` (ExternalNav) or `0`; `= 5` (OpticalFlow) if a flow
  sensor also feeds velocity — ASUNAMA uses flow for velocity, ExternalNav for
  position.
- `EK3_SRC1_YAW = 6` (ExternalNav) or `1` (Compass).
- `VISO_POS_X/Y/Z` — camera offset on the airframe.

## Quality gating
- `VISO_QUAL_MIN` — messages below this quality are ignored.
- Position error clamped to `[VISO_POS_M_NSE, 100]`, angle error to
  `[VISO_YAW_M_NSE, 1.5]`. Mirrors our inlier-confidence gate on the ORB fix.

## Gotcha
- **EKF origin must be set** before the EKF estimates position when no GPS is
  attached (send `SET_GPS_GLOBAL_ORIGIN` / set via GCS). Easy to miss on bench.

## Sources
- [Non-GPS Position Estimation (dev)](https://ardupilot.org/dev/docs/mavlink-nongps-position-estimation.html)
- [EKF Source Selection and Switching](https://ardupilot.org/copter/docs/common-ekf-sources.html)
- [GPS / Non-GPS Transitions](https://ardupilot.org/copter/docs/common-non-gps-to-gps.html)
