#!/usr/bin/env python3
"""
Zoom Meeting Attendance Analyzer
=================================
Usage:
    python zoom_attendance_analyzer.py --csv <zoom_report.csv> --guests <guests.txt> [--threshold 15] [--output report.html] [--host host@email.com]
"""

import csv, re, argparse
from pathlib import Path
from datetime import datetime

# ──────────────────────────────────────────────
# PARSING
# ──────────────────────────────────────────────

def parse_guest_list(text):
    guests = {}
    for m in re.finditer(r'"?([^"<,\n]+?)"?\s*<([^>]+)>', text):
        guests[m.group(2).strip().lower()] = m.group(1).strip()
    remaining = re.sub(r'"?[^"<,\n]+?"?\s*<[^>]+>', '', text)
    for m in re.finditer(r'\b([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)\b', remaining):
        e = m.group(1).lower()
        if e not in guests: guests[e] = e
    return guests

def read_zoom_csv(filepath):
    with open(filepath, encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))

def aggregate_attendance(rows):
    NOISE = ['read.ai', 'dbg/']
    person_data = {}
    for row in rows:
        email = row.get('Email','').strip().lower()
        name  = row.get('Name (original name)','').strip()
        if any(n in name.lower() for n in NOISE): continue
        try: dur = int(row.get('Duration (minutes)', 0))
        except: dur = 0
        key = email if email else name.lower()
        if key not in person_data:
            person_data[key] = {'name': name, 'email': email, 'total_duration': 0, 'sessions': 0}
        person_data[key]['total_duration'] += dur
        person_data[key]['sessions'] += 1
    return person_data

def norm(n):    return re.sub(r'[^a-z]', '', n.lower())
def clean(n):   return re.sub(r'\s*\(.*?\)', '', n).strip()


# ──────────────────────────────────────────────
# MATCHING
# ──────────────────────────────────────────────

def match_guests_to_attendance(guests, person_data, threshold=15, host_email=None):
    """
    Match guests to attendance with a strict priority chain.
    Each attendance record is claimed only once (first-match wins).
    Ambiguous partial-word matches are resolved only when the match is unique.

    Priority order:
      1. Direct email match
      2. Host email match (strips '(Host)' suffix from display name)
      3. Guest email used as attendee display name  (e.g. 'berenice.a@turing.com')
      4. Local-part of guest email = attendee display name (e.g. 'leykun.t', 'justice.p')
      5. Exact normalized full name
      6. Unique-word match: a word from guest name appears in exactly ONE attendee's name
      7. Substring: attendee display name (>5 chars) contained in guest full name,
                    and only one such attendee exists
    """

    # Build lookups
    email_lkp      = {v['email']: k for k, v in person_data.items() if v['email']}
    name_lkp       = {}
    for k, v in person_data.items():
        name_lkp[norm(v['name'])]       = k
        name_lkp[norm(clean(v['name']))] = k
    local_lkp      = {}
    for k, v in person_data.items():
        if v['email']: local_lkp[v['email'].split('@')[0].lower()] = k
        dn = v['name'].strip().lower()
        if re.match(r'^[a-z0-9_.+-]+$', dn) and '.' in dn: local_lkp[dn] = k
    email_as_name  = {v['name'].strip().lower(): k for k, v in person_data.items() if '@' in v['name']}

    # Word -> set of attendee keys (for uniqueness check)
    word_to_keys = {}
    for k, v in person_data.items():
        for w in clean(v['name']).lower().split():
            if len(w) > 3:
                word_to_keys.setdefault(w, set()).add(k)
    unique_word_lkp = {w: list(ks)[0] for w, ks in word_to_keys.items() if len(ks) == 1}

    claimed = set()

    def try_claim(key):
        if key and key not in claimed:
            claimed.add(key)
            return key
        return None

    results = []
    for email, full_name in guests.items():
        local = email.split('@')[0].lower()
        mk = None

        # 1. Direct email
        if not mk: mk = try_claim(email_lkp.get(email))
        # 2. Host
        if not mk and host_email and email == host_email:
            mk = try_claim(email_lkp.get(host_email))
        # 3. Email as display name
        if not mk: mk = try_claim(email_as_name.get(email))
        # 4. Local-part matches display name
        if not mk: mk = try_claim(local_lkp.get(local))
        # 5. Exact normalized name
        if not mk: mk = try_claim(name_lkp.get(norm(full_name)))
        # 6. Unique-word match
        if not mk:
            for w in full_name.lower().split():
                if len(w) > 3 and w in unique_word_lkp:
                    mk = try_claim(unique_word_lkp[w])
                    if mk: break
        # 7. Substring (attendee name inside guest full name, unique result)
        if not mk:
            fn = norm(full_name)
            candidates = [k for k, v in person_data.items()
                          if len(norm(clean(v['name']))) > 5
                          and norm(clean(v['name'])) in fn
                          and k not in claimed]
            if len(candidates) == 1:
                mk = try_claim(candidates[0])

        if mk:
            dur = person_data[mk]['total_duration']
            results.append({'name': full_name, 'email': email, 'status': 'attended',
                             'duration': dur, 'flag': dur <= threshold,
                             'sessions': person_data[mk]['sessions']})
        else:
            results.append({'name': full_name, 'email': email, 'status': 'absent',
                             'duration': 0, 'flag': False, 'sessions': 0})

    return results, claimed


# ──────────────────────────────────────────────
# HTML REPORT
# ──────────────────────────────────────────────

HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Zoom Attendance Report</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Fraunces:ital,opsz,wght@0,9..144,300;0,9..144,700;1,9..144,300&display=swap" rel="stylesheet">
<style>
:root{--bg:#0e0f11;--surface:#16181c;--border:#2a2d34;--green:#4ade80;--red:#f87171;--amber:#fbbf24;--text:#e2e8f0;--muted:#64748b;--card:#1c1f26}
*{box-sizing:border-box;margin:0;padding:0}body{background:var(--bg);color:var(--text);font-family:'DM Mono',monospace}
.hero{padding:60px 40px 40px;border-bottom:1px solid var(--border);background:linear-gradient(135deg,#0e0f11,#13151a)}
.hero h1{font-family:'Fraunces',serif;font-size:2.8rem;font-weight:700;color:#fff;margin-bottom:6px}
.hero .sub{color:var(--muted);font-size:.8rem;letter-spacing:.05em}
.hero .meta{margin-top:20px;display:flex;gap:30px;flex-wrap:wrap}
.hero .meta span{color:var(--muted);font-size:.75rem}.hero .meta strong{color:var(--text)}
.stats{display:flex;gap:1px;background:var(--border);border-bottom:1px solid var(--border)}
.stat{flex:1;background:var(--surface);padding:28px 32px;text-align:center}
.stat .n{font-family:'Fraunces',serif;font-size:3rem;font-weight:700;line-height:1;margin-bottom:6px}
.stat .l{font-size:.7rem;letter-spacing:.1em;color:var(--muted);text-transform:uppercase}
.stat.green .n{color:var(--green)}.stat.red .n{color:var(--red)}.stat.amber .n{color:var(--amber)}.stat.blue .n{color:#60a5fa}
.wrap{max-width:1100px;margin:0 auto;padding:40px}
.sh{display:flex;align-items:center;gap:12px;margin-bottom:20px;margin-top:48px}
.dot{width:10px;height:10px;border-radius:50%;flex-shrink:0}
.dot.red{background:var(--red);box-shadow:0 0 8px var(--red)}.dot.amber{background:var(--amber);box-shadow:0 0 8px var(--amber)}.dot.green{background:var(--green);box-shadow:0 0 8px var(--green)}
.sh h2{font-family:'Fraunces',serif;font-size:1.4rem;font-weight:300;font-style:italic;color:var(--text)}
.sh .cnt{margin-left:auto;background:var(--card);border:1px solid var(--border);border-radius:20px;padding:3px 12px;font-size:.72rem;color:var(--muted)}
table{width:100%;border-collapse:collapse}thead tr{border-bottom:1px solid var(--border)}
thead th{text-align:left;padding:10px 16px;font-size:.65rem;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);font-weight:400}
tbody tr{border-bottom:1px solid rgba(255,255,255,.04);transition:background .15s}tbody tr:hover{background:rgba(255,255,255,.03)}
tbody td{padding:11px 16px;font-size:.8rem;color:var(--text)}
.badge{display:inline-block;padding:2px 10px;border-radius:12px;font-size:.68rem;font-weight:500}
.b-absent{background:rgba(248,113,113,.12);color:var(--red);border:1px solid rgba(248,113,113,.25)}
.b-early{background:rgba(251,191,36,.12);color:var(--amber);border:1px solid rgba(251,191,36,.25)}
.b-full{background:rgba(74,222,128,.1);color:var(--green);border:1px solid rgba(74,222,128,.2)}
.bar-w{display:flex;align-items:center;gap:10px}.bar{height:4px;border-radius:2px;flex-shrink:0}
.bar.full{background:var(--green)}.bar.early{background:var(--amber)}.dur{color:var(--muted)}
.ec{color:var(--muted);font-size:.72rem}
.note{background:rgba(251,191,36,.08);border:1px solid rgba(251,191,36,.2);border-radius:8px;padding:16px 20px;margin-bottom:32px;font-size:.78rem;color:var(--amber);line-height:1.6}
.footer{margin-top:60px;padding:24px 40px;border-top:1px solid var(--border);font-size:.7rem;color:var(--muted);text-align:center}
@media(max-width:700px){.stats{flex-direction:column}.wrap{padding:20px}.hero{padding:30px 20px}.hero h1{font-size:1.8rem}}
</style></head><body>
<div class="hero">
  <h1>Attendance Report</h1><div class="sub">ZOOM MEETING ANALYSIS</div>
  <div class="meta">
    <span>Meeting: <strong>__TOPIC__</strong></span>
    <span>Date: <strong>__DATE__</strong></span>
    <span>Duration: <strong>__DUR__ min</strong></span>
    <span>Generated: <strong>__GEN__</strong></span>
    <span>Flag threshold: <strong>≤ __THRESH__ min</strong></span>
  </div>
</div>
<div class="stats">
  <div class="stat blue"><div class="n">__TOTAL__</div><div class="l">Total Invited</div></div>
  <div class="stat green"><div class="n">__FULL__</div><div class="l">Attended Fully</div></div>
  <div class="stat amber"><div class="n">__EARLY__</div><div class="l">Left Early</div></div>
  <div class="stat red"><div class="n">__ABSENT__</div><div class="l">Did Not Join</div></div>
</div>
<div class="wrap">
__NOTE__
  <div class="sh"><div class="dot red"></div><h2>Did Not Join</h2><span class="cnt">__ABSENT__ people</span></div>
  <table><thead><tr><th>#</th><th>Name</th><th>Email</th><th>Status</th></tr></thead><tbody>__ABSENT_R__</tbody></table>
  <div class="sh"><div class="dot amber"></div><h2>Left Early &nbsp;<small style="font-size:.9rem;font-style:normal">(≤ __THRESH__ min)</small></h2><span class="cnt">__EARLY__ people</span></div>
  <table><thead><tr><th>#</th><th>Name</th><th>Email</th><th>Duration</th><th>Status</th></tr></thead><tbody>__EARLY_R__</tbody></table>
  <div class="sh"><div class="dot green"></div><h2>Fully Attended</h2><span class="cnt">__FULL__ people</span></div>
  <table><thead><tr><th>#</th><th>Name</th><th>Email</th><th>Duration</th><th>Status</th></tr></thead><tbody>__FULL_R__</tbody></table>
</div>
<div class="footer">zoom_attendance_analyzer.py &nbsp;·&nbsp; __GEN__</div>
</body></html>"""


def bar(dur, mtotal, cls):
    w = max(4, min(100, round(dur / max(mtotal,1) * 100)))
    return f'<div class="bar-w"><div class="bar {cls}" style="width:{w}px"></div><span class="dur">{dur} min</span></div>'

def build_html_report(results, unaccounted, topic, date, mtotal, threshold, outpath):
    absent = sorted([r for r in results if r['status']=='absent'], key=lambda x: x['name'])
    early  = sorted([r for r in results if r['status']=='attended' and r['flag']], key=lambda x: x['duration'])
    full   = sorted([r for r in results if r['status']=='attended' and not r['flag']], key=lambda x: -x['duration'])
    gen = datetime.now().strftime("%Y-%m-%d %H:%M")

    def ar(i,r): return f'<tr><td style="color:var(--muted)">{i}</td><td>{r["name"]}</td><td class="ec">{r["email"]}</td><td><span class="badge b-absent">Absent</span></td></tr>'
    def er(i,r,cls,bcls): return f'<tr><td style="color:var(--muted)">{i}</td><td>{r["name"]}</td><td class="ec">{r["email"]}</td><td>{bar(r["duration"],mtotal,cls)}</td><td><span class="badge {bcls}">{r["duration"]} min</span></td></tr>'

    note = ""
    if unaccounted:
        names = ", ".join(f'<strong>{v["name"]}</strong>' for v in sorted(unaccounted, key=lambda x: x['name']))
        note = f'<div class="note">⚠️ <strong>{len(unaccounted)} attendee(s) in the Zoom CSV could not be matched to anyone on the guest list</strong> — they likely joined with a nickname or unrecognized display name:<br>{names}</div>'

    html = HTML
    for k, v in {
        '__TOPIC__': topic, '__DATE__': date, '__DUR__': str(mtotal), '__GEN__': gen,
        '__THRESH__': str(threshold), '__TOTAL__': str(len(results)),
        '__FULL__': str(len(full)), '__EARLY__': str(len(early)), '__ABSENT__': str(len(absent)),
        '__ABSENT_R__': "\n".join(ar(i+1, r) for i, r in enumerate(absent)),
        '__EARLY_R__':  "\n".join(er(i+1, r, 'early', 'b-early') for i, r in enumerate(early)),
        '__FULL_R__':   "\n".join(er(i+1, r, 'full',  'b-full')  for i, r in enumerate(full)),
        '__NOTE__': note,
    }.items():
        html = html.replace(k, v)

    with open(outpath, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"✅ Saved: {outpath}")


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--csv',       required=True)
    parser.add_argument('--guests',    default=None)
    parser.add_argument('--gueststr',  default=None)
    parser.add_argument('--threshold', type=int, default=15)
    parser.add_argument('--output',    default='attendance_report.html')
    parser.add_argument('--host',      default=None, help='Host email address')
    args = parser.parse_args()

    guest_text = Path(args.guests).read_text('utf-8') if args.guests else (args.gueststr or "")
    if not guest_text:
        print("❌ Provide --guests <file> or --gueststr '<string>'"); return

    guests      = parse_guest_list(guest_text)
    rows        = read_zoom_csv(args.csv)
    person_data = aggregate_attendance(rows)
    results, claimed = match_guests_to_attendance(guests, person_data, args.threshold, args.host)

    # Unaccounted: CSV attendees nobody in the guest list was matched to
    unaccounted = [v for k, v in person_data.items() if k not in claimed]

    absent = [r for r in results if r['status']=='absent']
    early  = [r for r in results if r['status']=='attended' and r['flag']]
    full   = [r for r in results if r['status']=='attended' and not r['flag']]

    print(f"\n{'='*55}")
    print(f"  Total invited      : {len(results)}")
    print(f"  Fully attended (>threshold): {len(full)}")
    print(f"  Left early (≤{args.threshold} min)    : {len(early)}")
    print(f"  Absent             : {len(absent)}")
    print(f"  Unaccounted in CSV : {len(unaccounted)}")
    print(f"{'='*55}")
    if early:
        print(f"\n🟡 Left Early:")
        for r in sorted(early, key=lambda x: x['duration']): print(f"   {r['name']:<40} {r['duration']} min")
    if absent:
        print(f"\n🔴 Absent ({len(absent)}):")
        for r in sorted(absent, key=lambda x: x['name']): print(f"   {r['name']}")
    if unaccounted:
        print(f"\n⚠️  Unaccounted CSV attendees (not on guest list or unrecognized alias):")
        for v in sorted(unaccounted, key=lambda x: x['name']): print(f"   '{v['name']}' ({v['email']}) — {v['total_duration']} min")

    try: mtotal = int(rows[0].get('Duration (minutes)', 60))
    except: mtotal = 60
    build_html_report(results, unaccounted,
                      rows[0].get('Topic','Meeting') if rows else 'Meeting',
                      rows[0].get('Start time','')[:10] if rows else '',
                      mtotal, args.threshold, args.output)

if __name__ == '__main__':
    main()
