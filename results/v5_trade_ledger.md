# V5 Fade Strategy — Full Trade Ledger

**What this is:** every trade the winning V5 fade config took over ~3 years, reconstructed from real historical option prices (IVolatility). Nothing is cherry-picked — winners and losers, all 119. Each row's profit/loss is recomputed from the source prices and **asserted equal to the backtest**, so this ledger *is* the backtest, not a flattering retelling.

**Honest caveat:** these are **backtest** results, not live or paper-traded. The config was chosen as the best of 9 variants, so a walk-forward / forward-test is the real next step before trusting it with money.

## Summary

- **Config:** 0DTE debit spread · drop the treacherous `failed_c` fade · active +50%/-50% exit
- **Span:** 2023-07-12 → 2026-06-17 · **119 trades**
- **Result:** +4171% on capital-at-risk · **82% win rate**
- **In account terms:** a $10,000 account risking 1% per trade → **+42%** ($14,171), worst dip **-1.1%**

## Every trade

| # | date | dir | setup | structure | debit | exit | P&L | on risk | result |
|--:|------|-----|-------|-----------|------:|------|----:|--------:|--------|
| 1 | 2023-07-12 | long | failed_a | bull call spread 4465/4490 | $7.00 | hit +50% target @ 12:50 | +395 | +56% | WIN |
| 2 | 2023-07-14 | long | failed_a | bull call spread 4510/4535 | $7.25 | hit +50% target @ 11:32 | +375 | +52% | WIN |
| 3 | 2023-07-17 | short | failed_a | bear put spread 4520/4495 | $5.45 | hit -50% stop @ 13:51 | -280 | -51% | LOSS |
| 4 | 2023-08-03 | short | failed_a | bear put spread 4505/4480 | $6.00 | hit -50% stop @ 12:42 | -330 | -55% | LOSS |
| 5 | 2023-08-25 | short | failed_a_pivot | bear put spread 4410/4385 | $8.20 | hit +50% target @ 10:21 | +440 | +54% | WIN |
| 6 | 2023-08-28 | long | failed_a | bull call spread 4420/4445 | $6.25 | hit +50% target @ 12:53 | +360 | +58% | WIN |
| 7 | 2023-09-08 | short | failed_a | bear put spread 4470/4445 | $5.50 | hit +50% target @ 10:42 | +280 | +51% | WIN |
| 8 | 2023-09-22 | short | failed_a | bear put spread 4355/4330 | $5.45 | hit +50% target @ 11:54 | +310 | +57% | WIN |
| 9 | 2023-10-02 | short | failed_a_pivot | bear put spread 4300/4275 | $6.90 | hit +50% target @ 11:39 | +390 | +56% | WIN |
| 10 | 2023-10-12 | long | failed_a | bull call spread 4365/4390 | $8.55 | hit +50% target @ 10:28 | +495 | +58% | WIN |
| 11 | 2023-10-24 | short | failed_a | bear put spread 4255/4230 | $6.30 | hit +50% target @ 11:16 | +320 | +51% | WIN |
| 12 | 2023-10-27 | long | failed_a | bull call spread 4135/4160 | $7.80 | hit +50% target @ 10:58 | +430 | +55% | WIN |
| 13 | 2023-10-30 | long | failed_a | bull call spread 4135/4160 | $8.80 | hit +50% target @ 11:05 | +450 | +51% | WIN |
| 14 | 2023-11-10 | short | failed_a | bear put spread 4375/4350 | $5.15 | hit -50% stop @ 12:11 | -260 | -50% | LOSS |
| 15 | 2023-11-16 | short | failed_a | bear put spread 4510/4485 | $6.25 | hit +50% target @ 10:19 | +345 | +55% | WIN |
| 16 | 2023-11-16 | long | failed_a | bull call spread 4490/4515 | $6.50 | hit +50% target @ 12:14 | +345 | +53% | WIN |
| 17 | 2023-11-21 | long | failed_a | bull call spread 4525/4550 | $7.35 | hit +50% target @ 12:12 | +405 | +55% | WIN |
| 18 | 2023-12-07 | short | failed_a | bear put spread 4585/4560 | $7.00 | hit +50% target @ 11:16 | +370 | +53% | WIN |
| 19 | 2023-12-08 | short | failed_a | bear put spread 4605/4580 | $7.00 | hit +50% target @ 10:36 | +480 | +69% | WIN |
| 20 | 2023-12-19 | short | failed_a | bear put spread 4765/4740 | $5.60 | hit +50% target @ 12:01 | +325 | +58% | WIN |
| 21 | 2024-01-24 | long | failed_a | bull call spread 4880/4905 | $6.75 | hit +50% target @ 10:14 | +340 | +50% | WIN |
| 22 | 2024-01-26 | short | failed_a | bear put spread 4905/4880 | $6.25 | hit +50% target @ 11:43 | +320 | +51% | WIN |
| 23 | 2024-02-01 | long | failed_a | bull call spread 4855/4880 | $8.65 | hit +50% target @ 11:35 | +435 | +50% | WIN |
| 24 | 2024-02-06 | long | failed_a | bull call spread 4940/4965 | $7.60 | hit -50% stop @ 14:15 | -410 | -54% | LOSS |
| 25 | 2024-02-26 | long | failed_a | bull call spread 5085/5110 | $5.25 | hit -50% stop @ 13:27 | -295 | -56% | LOSS |
| 26 | 2024-03-06 | long | failed_a | bull call spread 5095/5120 | $8.90 | hit +50% target @ 10:52 | +510 | +57% | WIN |
| 27 | 2024-04-12 | long | failed_a | bull call spread 5145/5170 | $8.70 | hit -50% stop @ 12:39 | -465 | -53% | LOSS |
| 28 | 2024-04-16 | long | failed_a | bull call spread 5050/5075 | $9.20 | hit +50% target @ 11:55 | +550 | +60% | WIN |
| 29 | 2024-04-25 | long | failed_a | bull call spread 4985/5010 | $11.00 | hit +50% target @ 10:31 | +590 | +54% | WIN |
| 30 | 2024-05-03 | long | failed_a | bull call spread 5100/5125 | $11.10 | hit +50% target @ 11:55 | +580 | +52% | WIN |
| 31 | 2024-05-21 | short | failed_a | bear put spread 5315/5290 | $4.30 | hit +50% target @ 11:44 | +225 | +52% | WIN |
| 32 | 2024-05-29 | short | failed_a | bear put spread 5280/5255 | $6.00 | hit +50% target @ 11:11 | +350 | +58% | WIN |
| 33 | 2024-06-11 | long | failed_a | bull call spread 5335/5360 | $6.10 | hit +50% target @ 10:12 | +320 | +52% | WIN |
| 34 | 2024-07-03 | short | failed_a | bear put spread 5525/5500 | $3.95 | hit +50% target @ 11:32 | +235 | +60% | WIN |
| 35 | 2024-07-17 | long | failed_a | bull call spread 5600/5625 | $9.10 | hit -50% stop @ 12:39 | -465 | -51% | LOSS |
| 36 | 2024-07-22 | long | failed_a | bull call spread 5535/5560 | $7.10 | hit +50% target @ 12:48 | +360 | +51% | WIN |
| 37 | 2024-07-23 | short | failed_a | bear put spread 5585/5560 | $7.55 | hit +50% target @ 12:24 | +555 | +74% | WIN |
| 38 | 2024-08-07 | short | failed_a | bear put spread 5330/5305 | $9.60 | hit +50% target @ 10:31 | +480 | +50% | WIN |
| 39 | 2024-08-08 | long | failed_a_pivot | bull call spread 5240/5265 | $11.30 | hit +50% target @ 10:14 | +570 | +50% | WIN |
| 40 | 2024-08-09 | short | failed_a | bear put spread 5340/5315 | $9.70 | hit -50% stop @ 13:30 | -555 | -57% | LOSS |
| 41 | 2024-08-12 | long | failed_a | bull call spread 5325/5350 | $10.60 | hit +50% target @ 10:13 | +530 | +50% | WIN |
| 42 | 2024-08-14 | long | failed_a_pivot | bull call spread 5425/5450 | $8.70 | hit +50% target @ 11:01 | +470 | +54% | WIN |
| 43 | 2024-09-05 | short | failed_a_pivot | bear put spread 5535/5510 | $8.00 | hit +50% target @ 10:48 | +430 | +54% | WIN |
| 44 | 2024-09-09 | short | failed_a_pivot | bear put spread 5465/5440 | $7.30 | hit +50% target @ 10:31 | +380 | +52% | WIN |
| 45 | 2024-09-12 | long | failed_a | bull call spread 5540/5565 | $12.00 | hit +50% target @ 11:14 | +600 | +50% | WIN |
| 46 | 2024-09-19 | long | failed_a | bull call spread 5685/5710 | $11.40 | hit +50% target @ 10:29 | +600 | +53% | WIN |
| 47 | 2024-10-03 | short | failed_a | bear put spread 5710/5685 | $7.00 | hit +50% target @ 10:15 | +360 | +51% | WIN |
| 48 | 2024-10-16 | short | failed_a_pivot | bear put spread 5830/5805 | $7.30 | hit +50% target @ 10:42 | +420 | +58% | WIN |
| 49 | 2024-10-22 | short | failed_a_pivot | bear put spread 5845/5820 | $7.40 | hit -50% stop @ 13:35 | -400 | -54% | LOSS |
| 50 | 2024-11-04 | short | failed_a | bear put spread 5745/5720 | $8.10 | hit +50% target @ 11:22 | +410 | +51% | WIN |
| 51 | 2024-11-04 | long | failed_a | bull call spread 5705/5730 | $7.90 | hit +50% target @ 12:27 | +420 | +53% | WIN |
| 52 | 2024-11-13 | long | failed_a | bull call spread 5975/6000 | $8.55 | hit +50% target @ 10:35 | +465 | +54% | WIN |
| 53 | 2024-12-30 | long | failed_a | bull call spread 5875/5900 | $9.60 | hit +50% target @ 10:46 | +520 | +54% | WIN |
| 54 | 2025-01-02 | short | failed_a | bear put spread 5930/5905 | $8.70 | hit +50% target @ 10:22 | +630 | +72% | WIN |
| 55 | 2025-01-08 | long | failed_a | bull call spread 5885/5910 | $10.70 | hit +50% target @ 11:33 | +540 | +50% | WIN |
| 56 | 2025-01-16 | long | failed_a_pivot | bull call spread 5940/5965 | $10.10 | hit +50% target @ 11:05 | +520 | +52% | WIN |
| 57 | 2025-01-27 | short | failed_a | bear put spread 6015/5990 | $8.50 | hit +50% target @ 11:03 | +440 | +52% | WIN |
| 58 | 2025-01-30 | short | failed_a | bear put spread 6075/6050 | $7.30 | hit +50% target @ 10:04 | +680 | +93% | WIN |
| 59 | 2025-02-03 | long | failed_a | bull call spread 5930/5955 | $10.20 | hit +50% target @ 10:25 | +620 | +61% | WIN |
| 60 | 2025-02-05 | long | failed_a | bull call spread 6010/6035 | $9.80 | hit +50% target @ 10:38 | +510 | +52% | WIN |
| 61 | 2025-03-07 | short | failed_a | bear put spread 5770/5745 | $10.60 | hit +50% target @ 10:32 | +660 | +62% | WIN |
| 62 | 2025-04-11 | short | failed_a | bear put spread 5275/5250 | $10.10 | hit -50% stop @ 10:01 | -760 | -75% | LOSS |
| 63 | 2025-04-11 | long | failed_a | bull call spread 5215/5240 | $13.90 | hit +50% target @ 12:33 | +710 | +51% | WIN |
| 64 | 2025-04-15 | short | failed_a | bear put spread 5450/5425 | $9.40 | hit +50% target @ 10:21 | +660 | +70% | WIN |
| 65 | 2025-04-23 | short | failed_a | bear put spread 5455/5430 | $9.60 | hit +50% target @ 11:21 | +490 | +51% | WIN |
| 66 | 2025-04-30 | long | failed_a | bull call spread 5435/5460 | $10.90 | hit +50% target @ 10:24 | +550 | +50% | WIN |
| 67 | 2025-05-02 | long | failed_a | bull call spread 5645/5670 | $12.00 | hit +50% target @ 10:29 | +600 | +50% | WIN |
| 68 | 2025-05-02 | short | failed_a | bear put spread 5680/5655 | $8.00 | hit -50% stop @ 12:14 | -400 | -50% | LOSS |
| 69 | 2025-05-06 | long | failed_a | bull call spread 5585/5610 | $11.10 | hit +50% target @ 10:19 | +580 | +52% | WIN |
| 70 | 2025-05-07 | long | failed_a | bull call spread 5595/5620 | $12.20 | hit +50% target @ 13:15 | +620 | +51% | WIN |
| 71 | 2025-05-22 | short | failed_a | bear put spread 5855/5830 | $8.30 | hit +50% target @ 10:38 | +450 | +54% | WIN |
| 72 | 2025-05-23 | short | failed_a | bear put spread 5800/5775 | $8.80 | hit -50% stop @ 13:18 | -485 | -55% | LOSS |
| 73 | 2025-05-30 | short | failed_a | bear put spread 5910/5885 | $9.40 | hit +50% target @ 11:41 | +480 | +51% | WIN |
| 74 | 2025-06-04 | long | failed_a_pivot | bull call spread 5965/5990 | $10.30 | hit +50% target @ 10:28 | +620 | +60% | WIN |
| 75 | 2025-06-05 | long | failed_a | bull call spread 5950/5975 | $10.90 | hit +50% target @ 10:43 | +690 | +63% | WIN |
| 76 | 2025-06-05 | short | failed_a | bear put spread 5995/5970 | $5.95 | hit +50% target @ 12:18 | +535 | +90% | WIN |
| 77 | 2025-06-13 | short | failed_a | bear put spread 6025/6000 | $7.90 | hit +50% target @ 13:11 | +420 | +53% | WIN |
| 78 | 2025-06-25 | long | failed_a | bull call spread 6090/6115 | $8.15 | hit -50% stop @ 13:41 | -455 | -56% | LOSS |
| 79 | 2025-07-09 | long | failed_a | bull call spread 6235/6260 | $8.10 | hit +50% target @ 11:45 | +410 | +51% | WIN |
| 80 | 2025-07-11 | short | failed_a | bear put spread 6265/6240 | $6.25 | hit +50% target @ 12:06 | +345 | +55% | WIN |
| 81 | 2025-07-14 | short | failed_a | bear put spread 6270/6245 | $7.95 | hit -50% stop @ 13:33 | -410 | -52% | LOSS |
| 82 | 2025-07-24 | short | failed_a | bear put spread 6380/6355 | $6.50 | hit +50% target @ 12:13 | +335 | +52% | WIN |
| 83 | 2025-08-13 | long | failed_a | bull call spread 6455/6480 | $6.25 | hit -50% stop @ 12:50 | -335 | -54% | LOSS |
| 84 | 2025-08-21 | short | failed_a_pivot | bear put spread 6390/6365 | $7.80 | hit +50% target @ 11:14 | +480 | +62% | WIN |
| 85 | 2025-08-28 | long | failed_a | bull call spread 6470/6495 | $10.10 | hit +50% target @ 11:17 | +510 | +50% | WIN |
| 86 | 2025-09-04 | short | failed_a | bear put spread 6485/6460 | $9.65 | hit -50% stop @ 13:52 | -530 | -55% | LOSS |
| 87 | 2025-09-09 | long | failed_a | bull call spread 6485/6510 | $8.55 | hit +50% target @ 11:27 | +490 | +57% | WIN |
| 88 | 2025-09-16 | long | failed_a | bull call spread 6605/6630 | $6.20 | hit +50% target @ 14:51 | +335 | +54% | WIN |
| 89 | 2025-10-03 | short | failed_a | bear put spread 6745/6720 | $3.95 | hit +50% target @ 13:02 | +235 | +60% | WIN |
| 90 | 2025-10-16 | short | failed_a | bear put spread 6710/6685 | $7.90 | hit +50% target @ 11:26 | +420 | +53% | WIN |
| 91 | 2025-10-23 | short | failed_a | bear put spread 6730/6705 | $7.50 | hit +50% target @ 10:11 | +410 | +55% | WIN |
| 92 | 2025-11-17 | long | failed_a | bull call spread 6700/6725 | $9.90 | hit +50% target @ 11:30 | +570 | +58% | WIN |
| 93 | 2025-11-20 | short | failed_a | bear put spread 6770/6745 | $7.40 | hit +50% target @ 10:54 | +430 | +58% | WIN |
| 94 | 2025-11-25 | long | failed_a_pivot | bull call spread 6675/6700 | $11.30 | hit +50% target @ 10:00 | +580 | +51% | WIN |
| 95 | 2025-12-04 | long | failed_a_pivot | bull call spread 6840/6865 | $8.70 | hit +50% target @ 10:36 | +450 | +52% | WIN |
| 96 | 2025-12-09 | short | failed_a | bear put spread 6870/6845 | $8.10 | hit +50% target @ 12:24 | +410 | +51% | WIN |
| 97 | 2025-12-16 | long | failed_a | bull call spread 6780/6805 | $10.30 | hit +50% target @ 10:56 | +600 | +58% | WIN |
| 98 | 2025-12-23 | short | failed_a | bear put spread 6900/6875 | $4.50 | hit -50% stop @ 13:09 | -225 | -50% | LOSS |
| 99 | 2025-12-31 | long | failed_a | bull call spread 6865/6890 | $10.70 | hit +50% target @ 13:42 | +570 | +53% | WIN |
| 100 | 2026-02-19 | short | failed_a | bear put spread 6870/6845 | $7.10 | hit +50% target @ 10:30 | +380 | +54% | WIN |
| 101 | 2026-03-09 | long | failed_a | bull call spread 6635/6660 | $11.70 | hit +50% target @ 10:42 | +600 | +51% | WIN |
| 102 | 2026-03-11 | short | failed_a | bear put spread 6810/6785 | $9.20 | hit +50% target @ 10:17 | +460 | +50% | WIN |
| 103 | 2026-03-17 | long | failed_a | bull call spread 6720/6745 | $8.95 | hit -50% stop @ 14:57 | -450 | -50% | LOSS |
| 104 | 2026-03-27 | long | failed_a | bull call spread 6415/6440 | $10.00 | hit +50% target @ 11:32 | +510 | +51% | WIN |
| 105 | 2026-03-30 | long | failed_a_pivot | bull call spread 6380/6405 | $10.70 | hit +50% target @ 11:38 | +540 | +50% | WIN |
| 106 | 2026-04-06 | short | failed_a | bear put spread 6610/6585 | $8.30 | hit +50% target @ 10:50 | +460 | +55% | WIN |
| 107 | 2026-04-10 | long | failed_a_pivot | bull call spread 6815/6840 | $9.30 | hit -50% stop @ 13:30 | -475 | -51% | LOSS |
| 108 | 2026-04-15 | short | failed_a | bear put spread 7000/6975 | $6.70 | hit +50% target @ 12:42 | +370 | +55% | WIN |
| 109 | 2026-04-16 | long | failed_a_pivot | bull call spread 7015/7040 | $8.80 | hit +50% target @ 11:04 | +450 | +51% | WIN |
| 110 | 2026-04-20 | long | failed_a | bull call spread 7095/7120 | $8.90 | hit +50% target @ 14:24 | +490 | +55% | WIN |
| 111 | 2026-04-22 | short | failed_a | bear put spread 7125/7100 | $6.60 | hit +50% target @ 12:31 | +370 | +56% | WIN |
| 112 | 2026-04-28 | long | failed_a | bull call spread 7120/7145 | $8.80 | hit +50% target @ 11:02 | +450 | +51% | WIN |
| 113 | 2026-05-21 | short | failed_a_pivot | bear put spread 7420/7395 | $10.40 | hit -50% stop @ 13:17 | -610 | -59% | LOSS |
| 114 | 2026-06-09 | short | failed_a | bear put spread 7480/7455 | $8.30 | hit +50% target @ 09:58 | +540 | +65% | WIN |
| 115 | 2026-06-10 | short | failed_a | bear put spread 7390/7365 | $10.30 | hit +50% target @ 10:57 | +540 | +52% | WIN |
| 116 | 2026-06-10 | long | failed_a | bull call spread 7330/7355 | $10.80 | hit -50% stop @ 13:11 | -540 | -50% | LOSS |
| 117 | 2026-06-11 | long | failed_a | bull call spread 7250/7275 | $13.90 | hit +50% target @ 13:32 | +710 | +51% | WIN |
| 118 | 2026-06-16 | long | failed_a | bull call spread 7545/7570 | $6.80 | hit +50% target @ 10:42 | +360 | +53% | WIN |
| 119 | 2026-06-17 | long | failed_a | bull call spread 7495/7520 | $11.90 | hit -50% stop @ 14:06 | -720 | -60% | LOSS |

## Trade-by-trade (one line each)


### 2023

1. 2023-07-12 11:42 — faded LONG (failed_a): bull call spread 4465/4490 for $7.00 -> hit +50% target at 12:50 -> +395 (+56%) [WIN]
2. 2023-07-14 10:49 — faded LONG (failed_a): bull call spread 4510/4535 for $7.25 -> hit +50% target at 11:32 -> +375 (+52%) [WIN]
3. 2023-07-17 11:42 — faded SHORT (failed_a): bear put spread 4520/4495 for $5.45 -> hit -50% stop at 13:51 -> -280 (-51%) [LOSS]
4. 2023-08-03 11:32 — faded SHORT (failed_a): bear put spread 4505/4480 for $6.00 -> hit -50% stop at 12:42 -> -330 (-55%) [LOSS]
5. 2023-08-25 10:16 — faded SHORT (failed_a_pivot): bear put spread 4410/4385 for $8.20 -> hit +50% target at 10:21 -> +440 (+54%) [WIN]
6. 2023-08-28 11:46 — faded LONG (failed_a): bull call spread 4420/4445 for $6.25 -> hit +50% target at 12:53 -> +360 (+58%) [WIN]
7. 2023-09-08 10:31 — faded SHORT (failed_a): bear put spread 4470/4445 for $5.50 -> hit +50% target at 10:42 -> +280 (+51%) [WIN]
8. 2023-09-22 11:40 — faded SHORT (failed_a): bear put spread 4355/4330 for $5.45 -> hit +50% target at 11:54 -> +310 (+57%) [WIN]
9. 2023-10-02 11:31 — faded SHORT (failed_a_pivot): bear put spread 4300/4275 for $6.90 -> hit +50% target at 11:39 -> +390 (+56%) [WIN]
10. 2023-10-12 10:02 — faded LONG (failed_a): bull call spread 4365/4390 for $8.55 -> hit +50% target at 10:28 -> +495 (+58%) [WIN]
11. 2023-10-24 10:50 — faded SHORT (failed_a): bear put spread 4255/4230 for $6.30 -> hit +50% target at 11:16 -> +320 (+51%) [WIN]
12. 2023-10-27 10:43 — faded LONG (failed_a): bull call spread 4135/4160 for $7.80 -> hit +50% target at 10:58 -> +430 (+55%) [WIN]
13. 2023-10-30 10:45 — faded LONG (failed_a): bull call spread 4135/4160 for $8.80 -> hit +50% target at 11:05 -> +450 (+51%) [WIN]
14. 2023-11-10 11:17 — faded SHORT (failed_a): bear put spread 4375/4350 for $5.15 -> hit -50% stop at 12:11 -> -260 (-50%) [LOSS]
15. 2023-11-16 10:02 — faded SHORT (failed_a): bear put spread 4510/4485 for $6.25 -> hit +50% target at 10:19 -> +345 (+55%) [WIN]
16. 2023-11-16 11:31 — faded LONG (failed_a): bull call spread 4490/4515 for $6.50 -> hit +50% target at 12:14 -> +345 (+53%) [WIN]
17. 2023-11-21 10:29 — faded LONG (failed_a): bull call spread 4525/4550 for $7.35 -> hit +50% target at 12:12 -> +405 (+55%) [WIN]
18. 2023-12-07 10:31 — faded SHORT (failed_a): bear put spread 4585/4560 for $7.00 -> hit +50% target at 11:16 -> +370 (+53%) [WIN]
19. 2023-12-08 10:18 — faded SHORT (failed_a): bear put spread 4605/4580 for $7.00 -> hit +50% target at 10:36 -> +480 (+69%) [WIN]
20. 2023-12-19 11:13 — faded SHORT (failed_a): bear put spread 4765/4740 for $5.60 -> hit +50% target at 12:01 -> +325 (+58%) [WIN]

### 2024

21. 2024-01-24 10:04 — faded LONG (failed_a): bull call spread 4880/4905 for $6.75 -> hit +50% target at 10:14 -> +340 (+50%) [WIN]
22. 2024-01-26 11:01 — faded SHORT (failed_a): bear put spread 4905/4880 for $6.25 -> hit +50% target at 11:43 -> +320 (+51%) [WIN]
23. 2024-02-01 11:01 — faded LONG (failed_a): bull call spread 4855/4880 for $8.65 -> hit +50% target at 11:35 -> +435 (+50%) [WIN]
24. 2024-02-06 10:06 — faded LONG (failed_a): bull call spread 4940/4965 for $7.60 -> hit -50% stop at 14:15 -> -410 (-54%) [LOSS]
25. 2024-02-26 11:08 — faded LONG (failed_a): bull call spread 5085/5110 for $5.25 -> hit -50% stop at 13:27 -> -295 (-56%) [LOSS]
26. 2024-03-06 10:07 — faded LONG (failed_a): bull call spread 5095/5120 for $8.90 -> hit +50% target at 10:52 -> +510 (+57%) [WIN]
27. 2024-04-12 10:53 — faded LONG (failed_a): bull call spread 5145/5170 for $8.70 -> hit -50% stop at 12:39 -> -465 (-53%) [LOSS]
28. 2024-04-16 10:38 — faded LONG (failed_a): bull call spread 5050/5075 for $9.20 -> hit +50% target at 11:55 -> +550 (+60%) [WIN]
29. 2024-04-25 10:04 — faded LONG (failed_a): bull call spread 4985/5010 for $11.00 -> hit +50% target at 10:31 -> +590 (+54%) [WIN]
30. 2024-05-03 10:27 — faded LONG (failed_a): bull call spread 5100/5125 for $11.10 -> hit +50% target at 11:55 -> +580 (+52%) [WIN]
31. 2024-05-21 11:23 — faded SHORT (failed_a): bear put spread 5315/5290 for $4.30 -> hit +50% target at 11:44 -> +225 (+52%) [WIN]
32. 2024-05-29 10:39 — faded SHORT (failed_a): bear put spread 5280/5255 for $6.00 -> hit +50% target at 11:11 -> +350 (+58%) [WIN]
33. 2024-06-11 09:49 — faded LONG (failed_a): bull call spread 5335/5360 for $6.10 -> hit +50% target at 10:12 -> +320 (+52%) [WIN]
34. 2024-07-03 11:23 — faded SHORT (failed_a): bear put spread 5525/5500 for $3.95 -> hit +50% target at 11:32 -> +235 (+60%) [WIN]
35. 2024-07-17 10:10 — faded LONG (failed_a): bull call spread 5600/5625 for $9.10 -> hit -50% stop at 12:39 -> -465 (-51%) [LOSS]
36. 2024-07-22 11:42 — faded LONG (failed_a): bull call spread 5535/5560 for $7.10 -> hit +50% target at 12:48 -> +360 (+51%) [WIN]
37. 2024-07-23 11:16 — faded SHORT (failed_a): bear put spread 5585/5560 for $7.55 -> hit +50% target at 12:24 -> +555 (+74%) [WIN]
38. 2024-08-07 10:01 — faded SHORT (failed_a): bear put spread 5330/5305 for $9.60 -> hit +50% target at 10:31 -> +480 (+50%) [WIN]
39. 2024-08-08 09:51 — faded LONG (failed_a_pivot): bull call spread 5240/5265 for $11.30 -> hit +50% target at 10:14 -> +570 (+50%) [WIN]
40. 2024-08-09 10:57 — faded SHORT (failed_a): bear put spread 5340/5315 for $9.70 -> hit -50% stop at 13:30 -> -555 (-57%) [LOSS]
41. 2024-08-12 09:59 — faded LONG (failed_a): bull call spread 5325/5350 for $10.60 -> hit +50% target at 10:13 -> +530 (+50%) [WIN]
42. 2024-08-14 10:35 — faded LONG (failed_a_pivot): bull call spread 5425/5450 for $8.70 -> hit +50% target at 11:01 -> +470 (+54%) [WIN]
43. 2024-09-05 10:02 — faded SHORT (failed_a_pivot): bear put spread 5535/5510 for $8.00 -> hit +50% target at 10:48 -> +430 (+54%) [WIN]
44. 2024-09-09 10:12 — faded SHORT (failed_a_pivot): bear put spread 5465/5440 for $7.30 -> hit +50% target at 10:31 -> +380 (+52%) [WIN]
45. 2024-09-12 09:49 — faded LONG (failed_a): bull call spread 5540/5565 for $12.00 -> hit +50% target at 11:14 -> +600 (+50%) [WIN]
46. 2024-09-19 09:52 — faded LONG (failed_a): bull call spread 5685/5710 for $11.40 -> hit +50% target at 10:29 -> +600 (+53%) [WIN]
47. 2024-10-03 10:06 — faded SHORT (failed_a): bear put spread 5710/5685 for $7.00 -> hit +50% target at 10:15 -> +360 (+51%) [WIN]
48. 2024-10-16 10:26 — faded SHORT (failed_a_pivot): bear put spread 5830/5805 for $7.30 -> hit +50% target at 10:42 -> +420 (+58%) [WIN]
49. 2024-10-22 11:18 — faded SHORT (failed_a_pivot): bear put spread 5845/5820 for $7.40 -> hit -50% stop at 13:35 -> -400 (-54%) [LOSS]
50. 2024-11-04 10:26 — faded SHORT (failed_a): bear put spread 5745/5720 for $8.10 -> hit +50% target at 11:22 -> +410 (+51%) [WIN]
51. 2024-11-04 11:58 — faded LONG (failed_a): bull call spread 5705/5730 for $7.90 -> hit +50% target at 12:27 -> +420 (+53%) [WIN]
52. 2024-11-13 10:07 — faded LONG (failed_a): bull call spread 5975/6000 for $8.55 -> hit +50% target at 10:35 -> +465 (+54%) [WIN]
53. 2024-12-30 10:01 — faded LONG (failed_a): bull call spread 5875/5900 for $9.60 -> hit +50% target at 10:46 -> +520 (+54%) [WIN]

### 2025

54. 2025-01-02 10:06 — faded SHORT (failed_a): bear put spread 5930/5905 for $8.70 -> hit +50% target at 10:22 -> +630 (+72%) [WIN]
55. 2025-01-08 10:17 — faded LONG (failed_a): bull call spread 5885/5910 for $10.70 -> hit +50% target at 11:33 -> +540 (+50%) [WIN]
56. 2025-01-16 10:01 — faded LONG (failed_a_pivot): bull call spread 5940/5965 for $10.10 -> hit +50% target at 11:05 -> +520 (+52%) [WIN]
57. 2025-01-27 10:40 — faded SHORT (failed_a): bear put spread 6015/5990 for $8.50 -> hit +50% target at 11:03 -> +440 (+52%) [WIN]
58. 2025-01-30 09:50 — faded SHORT (failed_a): bear put spread 6075/6050 for $7.30 -> hit +50% target at 10:04 -> +680 (+93%) [WIN]
59. 2025-02-03 10:16 — faded LONG (failed_a): bull call spread 5930/5955 for $10.20 -> hit +50% target at 10:25 -> +620 (+61%) [WIN]
60. 2025-02-05 10:05 — faded LONG (failed_a): bull call spread 6010/6035 for $9.80 -> hit +50% target at 10:38 -> +510 (+52%) [WIN]
61. 2025-03-07 09:54 — faded SHORT (failed_a): bear put spread 5770/5745 for $10.60 -> hit +50% target at 10:32 -> +660 (+62%) [WIN]
62. 2025-04-11 09:47 — faded SHORT (failed_a): bear put spread 5275/5250 for $10.10 -> hit -50% stop at 10:01 -> -760 (-75%) [LOSS]
63. 2025-04-11 10:24 — faded LONG (failed_a): bull call spread 5215/5240 for $13.90 -> hit +50% target at 12:33 -> +710 (+51%) [WIN]
64. 2025-04-15 10:13 — faded SHORT (failed_a): bear put spread 5450/5425 for $9.40 -> hit +50% target at 10:21 -> +660 (+70%) [WIN]
65. 2025-04-23 09:53 — faded SHORT (failed_a): bear put spread 5455/5430 for $9.60 -> hit +50% target at 11:21 -> +490 (+51%) [WIN]
66. 2025-04-30 09:59 — faded LONG (failed_a): bull call spread 5435/5460 for $10.90 -> hit +50% target at 10:24 -> +550 (+50%) [WIN]
67. 2025-05-02 09:52 — faded LONG (failed_a): bull call spread 5645/5670 for $12.00 -> hit +50% target at 10:29 -> +600 (+50%) [WIN]
68. 2025-05-02 10:30 — faded SHORT (failed_a): bear put spread 5680/5655 for $8.00 -> hit -50% stop at 12:14 -> -400 (-50%) [LOSS]
69. 2025-05-06 09:52 — faded LONG (failed_a): bull call spread 5585/5610 for $11.10 -> hit +50% target at 10:19 -> +580 (+52%) [WIN]
70. 2025-05-07 11:14 — faded LONG (failed_a): bull call spread 5595/5620 for $12.20 -> hit +50% target at 13:15 -> +620 (+51%) [WIN]
71. 2025-05-22 10:02 — faded SHORT (failed_a): bear put spread 5855/5830 for $8.30 -> hit +50% target at 10:38 -> +450 (+54%) [WIN]
72. 2025-05-23 11:35 — faded SHORT (failed_a): bear put spread 5800/5775 for $8.80 -> hit -50% stop at 13:18 -> -485 (-55%) [LOSS]
73. 2025-05-30 10:32 — faded SHORT (failed_a): bear put spread 5910/5885 for $9.40 -> hit +50% target at 11:41 -> +480 (+51%) [WIN]
74. 2025-06-04 10:09 — faded LONG (failed_a_pivot): bull call spread 5965/5990 for $10.30 -> hit +50% target at 10:28 -> +620 (+60%) [WIN]
75. 2025-06-05 09:58 — faded LONG (failed_a): bull call spread 5950/5975 for $10.90 -> hit +50% target at 10:43 -> +690 (+63%) [WIN]
76. 2025-06-05 11:58 — faded SHORT (failed_a): bear put spread 5995/5970 for $5.95 -> hit +50% target at 12:18 -> +535 (+90%) [WIN]
77. 2025-06-13 11:53 — faded SHORT (failed_a): bear put spread 6025/6000 for $7.90 -> hit +50% target at 13:11 -> +420 (+53%) [WIN]
78. 2025-06-25 11:34 — faded LONG (failed_a): bull call spread 6090/6115 for $8.15 -> hit -50% stop at 13:41 -> -455 (-56%) [LOSS]
79. 2025-07-09 11:15 — faded LONG (failed_a): bull call spread 6235/6260 for $8.10 -> hit +50% target at 11:45 -> +410 (+51%) [WIN]
80. 2025-07-11 11:43 — faded SHORT (failed_a): bear put spread 6265/6240 for $6.25 -> hit +50% target at 12:06 -> +345 (+55%) [WIN]
81. 2025-07-14 11:42 — faded SHORT (failed_a): bear put spread 6270/6245 for $7.95 -> hit -50% stop at 13:33 -> -410 (-52%) [LOSS]
82. 2025-07-24 11:03 — faded SHORT (failed_a): bear put spread 6380/6355 for $6.50 -> hit +50% target at 12:13 -> +335 (+52%) [WIN]
83. 2025-08-13 11:10 — faded LONG (failed_a): bull call spread 6455/6480 for $6.25 -> hit -50% stop at 12:50 -> -335 (-54%) [LOSS]
84. 2025-08-21 10:18 — faded SHORT (failed_a_pivot): bear put spread 6390/6365 for $7.80 -> hit +50% target at 11:14 -> +480 (+62%) [WIN]
85. 2025-08-28 09:52 — faded LONG (failed_a): bull call spread 6470/6495 for $10.10 -> hit +50% target at 11:17 -> +510 (+50%) [WIN]
86. 2025-09-04 11:54 — faded SHORT (failed_a): bear put spread 6485/6460 for $9.65 -> hit -50% stop at 13:52 -> -530 (-55%) [LOSS]
87. 2025-09-09 10:39 — faded LONG (failed_a): bull call spread 6485/6510 for $8.55 -> hit +50% target at 11:27 -> +490 (+57%) [WIN]
88. 2025-09-16 11:02 — faded LONG (failed_a): bull call spread 6605/6630 for $6.20 -> hit +50% target at 14:51 -> +335 (+54%) [WIN]
89. 2025-10-03 11:57 — faded SHORT (failed_a): bear put spread 6745/6720 for $3.95 -> hit +50% target at 13:02 -> +235 (+60%) [WIN]
90. 2025-10-16 10:44 — faded SHORT (failed_a): bear put spread 6710/6685 for $7.90 -> hit +50% target at 11:26 -> +420 (+53%) [WIN]
91. 2025-10-23 09:52 — faded SHORT (failed_a): bear put spread 6730/6705 for $7.50 -> hit +50% target at 10:11 -> +410 (+55%) [WIN]
92. 2025-11-17 11:18 — faded LONG (failed_a): bull call spread 6700/6725 for $9.90 -> hit +50% target at 11:30 -> +570 (+58%) [WIN]
93. 2025-11-20 10:38 — faded SHORT (failed_a): bear put spread 6770/6745 for $7.40 -> hit +50% target at 10:54 -> +430 (+58%) [WIN]
94. 2025-11-25 09:49 — faded LONG (failed_a_pivot): bull call spread 6675/6700 for $11.30 -> hit +50% target at 10:00 -> +580 (+51%) [WIN]
95. 2025-12-04 10:26 — faded LONG (failed_a_pivot): bull call spread 6840/6865 for $8.70 -> hit +50% target at 10:36 -> +450 (+52%) [WIN]
96. 2025-12-09 11:20 — faded SHORT (failed_a): bear put spread 6870/6845 for $8.10 -> hit +50% target at 12:24 -> +410 (+51%) [WIN]
97. 2025-12-16 10:26 — faded LONG (failed_a): bull call spread 6780/6805 for $10.30 -> hit +50% target at 10:56 -> +600 (+58%) [WIN]
98. 2025-12-23 11:52 — faded SHORT (failed_a): bear put spread 6900/6875 for $4.50 -> hit -50% stop at 13:09 -> -225 (-50%) [LOSS]
99. 2025-12-31 10:56 — faded LONG (failed_a): bull call spread 6865/6890 for $10.70 -> hit +50% target at 13:42 -> +570 (+53%) [WIN]

### 2026

100. 2026-02-19 10:04 — faded SHORT (failed_a): bear put spread 6870/6845 for $7.10 -> hit +50% target at 10:30 -> +380 (+54%) [WIN]
101. 2026-03-09 10:12 — faded LONG (failed_a): bull call spread 6635/6660 for $11.70 -> hit +50% target at 10:42 -> +600 (+51%) [WIN]
102. 2026-03-11 10:02 — faded SHORT (failed_a): bear put spread 6810/6785 for $9.20 -> hit +50% target at 10:17 -> +460 (+50%) [WIN]
103. 2026-03-17 11:38 — faded LONG (failed_a): bull call spread 6720/6745 for $8.95 -> hit -50% stop at 14:57 -> -450 (-50%) [LOSS]
104. 2026-03-27 09:59 — faded LONG (failed_a): bull call spread 6415/6440 for $10.00 -> hit +50% target at 11:32 -> +510 (+51%) [WIN]
105. 2026-03-30 09:56 — faded LONG (failed_a_pivot): bull call spread 6380/6405 for $10.70 -> hit +50% target at 11:38 -> +540 (+50%) [WIN]
106. 2026-04-06 10:22 — faded SHORT (failed_a): bear put spread 6610/6585 for $8.30 -> hit +50% target at 10:50 -> +460 (+55%) [WIN]
107. 2026-04-10 11:58 — faded LONG (failed_a_pivot): bull call spread 6815/6840 for $9.30 -> hit -50% stop at 13:30 -> -475 (-51%) [LOSS]
108. 2026-04-15 11:29 — faded SHORT (failed_a): bear put spread 7000/6975 for $6.70 -> hit +50% target at 12:42 -> +370 (+55%) [WIN]
109. 2026-04-16 09:56 — faded LONG (failed_a_pivot): bull call spread 7015/7040 for $8.80 -> hit +50% target at 11:04 -> +450 (+51%) [WIN]
110. 2026-04-20 11:04 — faded LONG (failed_a): bull call spread 7095/7120 for $8.90 -> hit +50% target at 14:24 -> +490 (+55%) [WIN]
111. 2026-04-22 10:21 — faded SHORT (failed_a): bear put spread 7125/7100 for $6.60 -> hit +50% target at 12:31 -> +370 (+56%) [WIN]
112. 2026-04-28 10:52 — faded LONG (failed_a): bull call spread 7120/7145 for $8.80 -> hit +50% target at 11:02 -> +450 (+51%) [WIN]
113. 2026-05-21 09:56 — faded SHORT (failed_a_pivot): bear put spread 7420/7395 for $10.40 -> hit -50% stop at 13:17 -> -610 (-59%) [LOSS]
114. 2026-06-09 09:50 — faded SHORT (failed_a): bear put spread 7480/7455 for $8.30 -> hit +50% target at 09:58 -> +540 (+65%) [WIN]
115. 2026-06-10 10:10 — faded SHORT (failed_a): bear put spread 7390/7365 for $10.30 -> hit +50% target at 10:57 -> +540 (+52%) [WIN]
116. 2026-06-10 11:13 — faded LONG (failed_a): bull call spread 7330/7355 for $10.80 -> hit -50% stop at 13:11 -> -540 (-50%) [LOSS]
117. 2026-06-11 11:01 — faded LONG (failed_a): bull call spread 7250/7275 for $13.90 -> hit +50% target at 13:32 -> +710 (+51%) [WIN]
118. 2026-06-16 10:33 — faded LONG (failed_a): bull call spread 7545/7570 for $6.80 -> hit +50% target at 10:42 -> +360 (+53%) [WIN]
119. 2026-06-17 10:48 — faded LONG (failed_a): bull call spread 7495/7520 for $11.90 -> hit -50% stop at 14:06 -> -720 (-60%) [LOSS]
