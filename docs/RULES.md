# Fantasy Premier League — Rules (Structured Reference)

> Structured from the official rules at
> <https://fantasy.premierleague.com/en/help/rules> (2025/26 season).
> This is an internal reference for the team-planning tool. If anything here
> conflicts with the official site, the official site wins — see
> [`scripts/fetch_fpl_data.py`](../scripts/fetch_fpl_data.py), which reads the
> live rules/scoring parameters from the FPL API so the app never hard-codes a
> stale number.

---

## 1. Selecting your initial squad

| Constraint | Rule |
|---|---|
| **Squad size** | 15 players: **2 GK, 5 DEF, 5 MID, 3 FWD** |
| **Budget** | Total squad value ≤ **£100.0m** |
| **Players per team** | Max **3** players from any single Premier League club |

## 2. Managing your squad each Gameweek

### Starting XI
- Pick **11** of your 15 by the Gameweek deadline. Only these 11 score
  (subject to auto-subs).
- Any formation is legal provided you always field **1 GK, ≥3 DEF, ≥1 FWD**.

### Captain & Vice-Captain
- Choose a **captain** (score **×2**) and a **vice-captain** from the XI.
- If the captain plays **0 minutes**, the armband passes to the vice-captain.
- If both play 0 minutes, **no** score is doubled that Gameweek.

### Bench & automatic substitutions
- The bench provides cover for players who don't play (0 minutes and no card).
  "Playing" = making an appearance **or** receiving a yellow/red card.
- Bench **order matters** — it sets substitution priority. Processed at
  Gameweek end:
  - GK is only replaced by the backup **GK**.
  - An outfield non-player is replaced by the **highest-priority** benched
    outfielder who played **and** doesn't break the formation rules
    (e.g. with 3 starting DEF, a DEF can only be replaced by a DEF).

## 3. Transfers

- **Before the first deadline:** unlimited free transfers.
- **After that:** **1 free transfer** per Gameweek.
- **Extra transfers cost −4 points each** (deducted at the start of the next
  Gameweek) — a "hit".
- **Rolling:** an unused free transfer carries to the next week. You can bank
  up to a **maximum of 5** free transfers.
- Hard cap of **20 transfers** in a single Gameweek (does not apply under
  Wildcard / Free Hit).

### Player prices
- Prices move during the season based on transfer-market popularity (they don't
  move until the season starts).
- **Sell-on rule:** you keep **half** of any price rise since purchase, rounded
  **down** to the nearest £0.1m.
  *Example: bought at £7.5m, now £7.8m → sell value £7.6m.*

## 4. Chips

Only **one chip per Gameweek**.

| Chip | Effect |
|---|---|
| **Bench Boost** | Points scored by your **bench** are added to your total that GW. |
| **Free Hit** | Unlimited free transfers for **one** GW; squad reverts next deadline. |
| **Triple Captain** | Captain scores **×3** instead of ×2 that GW. |
| **Wildcard** | All transfers in the GW are **free** (no point hits). |

**Two sets of chips** across the season (2025/26):
- **Bench Boost / Triple Captain:** two of each. First set usable up to the
  **GW19 deadline**; second set after it.
- **Free Hit:** two available. First usable after GW1, must be played by GW19;
  second after the GW19 deadline. **Cannot** be played in consecutive
  Gameweeks. Confirmed on transfer confirmation — **cannot be cancelled**.
- **Wildcard:** twice per season — first up to GW19, second after (for the
  January window) through end of season. **Cannot** be cancelled once played.
- Playing a Wildcard/Free Hit **retains** any saved free transfers for the
  following Gameweek.

## 5. Deadlines

- All changes (XI, transfers, captain, bench order) must be in **by the GW
  deadline** to count.
- Deadline = **90 minutes before** the first kick-off of the Gameweek.
- A deadline won't change within **24 hours** of its scheduled time.

## 6. Scoring

### Point values

| Action | Pts |
|---|---|
| Playing up to 60 minutes | **1** |
| Playing 60+ minutes (excl. stoppage) | **2** |
| Goal — GK | **10** |
| Goal — DEF | **6** |
| Goal — MID | **5** |
| Goal — FWD | **4** |
| Assist | **3** |
| Clean sheet — GK / DEF | **4** |
| Clean sheet — MID | **1** |
| Every 3 shot saves (GK) | **1** |
| **Defensive contribution** — DEF: ≥10 CBIT (clearances, blocks, interceptions, tackles) in a match | **2** |
| **Defensive contribution** — MID/FWD: ≥12 CBIT **+ recoveries** in a match | **2** |
| Penalty save | **5** |
| Penalty miss | **−2** |
| Bonus (best players in a match) | **1–3** |
| Every 2 goals conceded — GK / DEF | **−1** |
| Yellow card | **−1** |
| Red card | **−3** |
| Own goal | **−2** |

### Defensive contributions (2025/26, "DEFCON")
Rewards defensive actions independent of goals/assists. **Capped at 2 pts per
match.**
- **DEF:** ≥ **10** combined clearances, blocks, interceptions, tackles (CBIT).
- **MID/FWD:** ≥ **12** combined CBIT **plus ball recoveries**.

This meaningfully raises the value of centre-backs and defensive midfielders
(CDMs). It should *improve* a player's case, not replace clean-sheet potential,
attacking threat, price, or minutes in the decision. The tool surfaces a
per-player DEFCON hit-rate so it can be weighed alongside the rest.

### Bonus points
The three best performers in each match receive 3 / 2 / 1 bonus points, derived
from the Bonus Points System (BPS).

## 7. Leagues, cups & scoring types (summary)

- **Classic scoring:** ranked by total points; ties broken by **fewest
  transfers made** (wildcard/free-hit transfers excluded). Runs in phases
  (Overall + monthly).
- **Head-to-head:** GW score (minus hits) vs one opponent; **3** for a win,
  **1** for a draw. Optional knock-out stage.
- **Invitational leagues:** up to 30 private + 5 public; automatic global
  leagues (overall, country, favourite club, same-start-GW, Second Chance from
  GW21, Fantasy Cup).
- **Cups:** knockout, one round per GW. Overall Cup runs GW15→GW38; finals in
  GW38. Tie-breaks: most goals scored → fewest conceded → virtual coin toss.

---

*Everything above that affects a calculation (scoring values, squad limits,
budget, transfer costs) is also pulled live by the data pipeline so the app
stays correct if the official rules change mid-season.*
