# Zoom Attendance Portal

A browser-based tool that analyzes Zoom meeting attendance. Upload your Zoom CSV export and guest list — get a live dashboard showing who attended, who left early, and who never showed up.

No backend. No server. Everything runs in your browser, nothing leaves your device.

---

## Files

| File | Purpose |
|------|---------|
| `zoom_attendance_portal.html` | Open this in a browser — it's the full portal |
| `zoom_attendance_analyzer.py` | Command-line version if you prefer terminal |
| `guests.txt` | Your team's invite list — update this each week |

---

## Quick Start

1. Open `zoom_attendance_portal.html` in any browser
2. Drop your Zoom CSV on the left panel
3. Drop your `guests.txt` on the right panel
4. Enter the host email (optional but fixes host matching)
5. Click **Analyze Meeting →**

---

## Getting the Zoom CSV

In Zoom web portal: **Reports → Usage → click the participant count on your meeting → Export with meeting data**

Make sure you click the participant count number, not the meeting title. And use "Export with meeting data" not just "Export" — the full version includes the meeting topic and duration which populate the dashboard header.

---

## Guest List Format

Same format as a calendar invite. Paste directly from your meeting invite if you want.

```
John Smith <john.smith@company.com>, Jane Doe <jane.doe@company.com>,
Alice Johnson <alice.j@company.com>, bob.wilson@company.com,
"Dr. Carol White" <carol.w@company.com>
```

Bare emails without names work too. Entries can span multiple lines — commas are the separator.

---

## How Matching Works

The tricky part is that Zoom lets people join with any display name they want. Someone invited as `alice.j@company.com` might show up in the CSV as `"Alice"`, `"alice.j"`, or their full email. The portal handles this with a 7-step chain — it tries each step in order and stops at the first match.

**Step 1 — Direct email match**  
Guest email matches the `Email` column in the CSV exactly. Most reliable — only works when the person is logged into their Zoom account.

```
Guest list:  john.smith@company.com
Zoom CSV:    Email = john.smith@company.com  ✓
```

**Step 2 — Host match**  
Zoom appends `(Host)` to the host's display name, which breaks normal matching. If you provide the host email in the settings field, it matches them by email directly and ignores the display name.

```
Guest list:  host@company.com
Zoom CSV:    Name = "Sarah Chen (Host)", Email = host@company.com  ✓
```

**Step 3 — Email used as display name**  
Some people join with their full email as their Zoom display name.

```
Guest list:  alice.j@company.com
Zoom CSV:    Name = "alice.j@company.com"  ✓
```

**Step 4 — Local-part match**  
Some people join with just the part before the `@` as their display name. Common when joining from a browser without a Zoom account.

```
Guest list:  alice.j@company.com  →  local part = "alice.j"
Zoom CSV:    Name = "alice.j"  ✓
```

**Step 5 — Exact normalized name**  
Strips all non-letter characters, lowercases both names, then compares. Handles casing differences, extra suffixes like `(ace)`, and punctuation.

```
Guest list:  "Waqid Abbas"         →  normalizes to  "waqidabbas"
Zoom CSV:    "waqid abbas ( ace )" →  normalizes to  "waqidabbasace"
                                                      ↑ still matches on prefix
```

**Step 6 — Unique-word match**  
Takes each word (>3 letters) from the guest's name and checks if that word appears in **exactly one** attendee's display name across the whole CSV. If a word appears in two or more rows it's skipped entirely — this is what prevents false matches on common names.

```
Guest list:  "Sabarna Senthilkumar"
Word "sabarna" appears in only 1 CSV row  →  match  ✓

Guest list:  "Prateek Singh"
Word "singh" appears in 3 CSV rows        →  skipped, too ambiguous
```

**Step 7 — Substring match**  
Checks if the attendee's display name (must be >5 characters) is contained inside the guest's full normalized name, and only one such attendee qualifies.

```
Guest list:  "Oluwaferanmi Ibitunde"
Zoom CSV:    "Feranmi"
"feranmi" is found inside "oluwaferanmiibitunde"  →  match  ✓
```

If all 7 steps fail, the guest is marked **Absent**. The system never guesses when it isn't confident.

### Deduplication

Once a CSV row is claimed by a guest it can't be claimed again. So if you have two guests named `mehedi.h1@company.com` and `mehedi.h2@company.com` but only one "Mehedi Hasan" row in the CSV — the first guest claims it, the second is correctly marked Absent.

### Why not fuzzy matching?

In a 200-person meeting, words like `sharma`, `singh`, `kumar`, `muhammad` appear in multiple attendee names. Fuzzy matching would silently mark people as attended when they weren't. The 7-step chain only matches when the evidence is strong enough to be confident.

---

## Status Meanings

| Status | Meaning |
|--------|---------|
| ✓ Attended | Matched to a CSV row, total time > threshold |
| ⏱ Left Early | Matched to a CSV row, total time ≤ threshold |
| ✗ Absent | No CSV row could be confidently matched |
| ⚠️ Unaccounted | In Zoom CSV but not matched to any guest |

Duration is summed across all sessions — if someone dropped and rejoined, the reconnect time is added together.

The threshold defaults to 15 minutes. Change it before analyzing — for a 30-minute standup you might use 10, for an hour-long session maybe 20.

---

## Unaccounted Attendees

These appear in a yellow warning banner on the dashboard. They attended the meeting (they're in the Zoom CSV) but couldn't be matched to anyone on your guest list. Common reasons:

- Joined with a nickname that doesn't resemble their full name
- Not on the guest list at all (last-minute invite, uninvited guest)
- Host and you didn't enter the host email in settings
- The `read.ai` bot or similar tools (filtered out automatically)

---

## Python CLI

Same logic as the portal, outputs an HTML report file.

```bash
python zoom_attendance_analyzer.py \
  --csv      meeting_report.csv \
  --guests   guests.txt \
  --host     host@company.com \
  --threshold 15 \
  --output   report.html
```

| Flag | Description |
|------|-------------|
| `--csv` | Zoom CSV export (required) |
| `--guests` | Path to guest list file |
| `--gueststr` | Guest list as a raw string instead of a file |
| `--host` | Host email so host row is matched correctly |
| `--threshold` | Minutes to flag as left early (default: 15) |
| `--output` | Output HTML filename (default: attendance_report.html) |

---

## Deployment

The portal is a single HTML file with no backend so deployment is just file hosting.

**Netlify Drop (fastest)** — go to [app.netlify.com/drop](https://app.netlify.com/drop), rename the file to `index.html`, drag it onto the page. Live in under a minute.

**GitHub Pages** — create a repo, upload as `index.html`, enable Pages in settings. Live at `username.github.io/repo-name`. Easy to update by just pushing a new file.

**Vercel** — best if you want a custom domain like `attendance.yourcompany.com`. Connect a GitHub repo, auto-deploys on push.

**Share directly** — email the file or share via Drive/OneDrive. Anyone who downloads it can open it locally — works fully offline.

---

## Troubleshooting

**Someone attended but shows as Absent**  
Check the yellow warning banner. If their name is there, they did attend but joined with an unrecognized display name. Ask them to update their Zoom display name to match what's in the guest list.

**Duration looks too high**  
Duration is summed across all sessions. Someone who reconnected three times will have all three session lengths added together.

**Host always shows as Absent**  
Zoom adds `(Host)` to the display name which breaks name matching. Enter the host email in the settings field before analyzing.

**Two people with the same name**  
If only one row exists in the CSV, the first guest in the list order claims it. The second is marked Absent. The system won't fabricate a second match.

---

## Requirements

**Portal** — any modern browser, no installation  
**Python script** — Python 3.7+, no third-party libraries needed
