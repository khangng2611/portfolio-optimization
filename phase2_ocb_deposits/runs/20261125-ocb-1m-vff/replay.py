"""One-month deposit vs. matched VFF NAV on original valuation dates."""
import calendar
import csv
import hashlib
import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from statistics import mean, median

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
NAV = ROOT / 'trusted_baseline/datasets/funds/full/VFF.csv'
D = Decimal


def read(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def write(path, rows):
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=rows[0], lineterminator='\n')
        w.writeheader()
        w.writerows(rows)


def maturity(day):
    year = day.year + (day.month == 12)
    month = day.month % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def summarize(pairs):
    def values(key):
        return [float(r[key]) for r in pairs]
    return dict(n=len(pairs), mean_ocb_pct=mean(values('ocb_pct')), mean_vff_nav_pct=mean(values('vff_nav_pct')),
                mean_vff_sale_scenario_pct=mean(values('vff_sale_scenario_pct')),
                mean_ocb_minus_nav_pp=mean(values('ocb_minus_nav_pp')),
                median_ocb_minus_nav_pp=median(values('ocb_minus_nav_pp')),
                ocb_above_nav=sum(x>0 for x in values('ocb_minus_nav_pp')),
                ocb_above_sale_scenario=sum(r['ocb_pct']>r['vff_sale_scenario_pct'] for r in pairs))


def run():
    manifest = json.loads((HERE/'manifest.json').read_text())
    for entry in manifest['inputs']:
        assert hashlib.sha256((HERE/entry['path']).read_bytes()).hexdigest() == entry['sha256'], entry['path']
    evidence = json.loads((HERE/'evidence.json').read_text())
    for src in evidence.values():
        assert hashlib.sha256((HERE/src['local']).read_bytes()).hexdigest() == src['sha256']
    nav = {}
    for row in read(NAV):
        assert row['symbol'] == 'VFF' and row['provider_fund_id']=='21'
        day = date.fromisoformat(row['date'])
        value = D(row['nav_per_unit_vnd'])
        assert day not in nav and value.is_finite() and value > 0
        nav[day] = value
    sessions = {date.fromisoformat(r['date']) for r in read(HERE/'sessions.csv')}
    docs = read(HERE/'screened_sources.csv')
    effective_days = {date.fromisoformat(r['date_in_document']) for r in docs if r['classification']=='retail_schedule'}
    # An unmatched official effective date is still counted in the exclusion ledger.
    windows = read(HERE/'verified_rates.csv')
    candidates = dict.fromkeys(effective_days)
    for row in windows:
        start, end = (date.fromisoformat(row[k]) for k in ('effective','confirmed_through'))
        assert start in effective_days and start <= end and row['bank_pdf'] in evidence
        assert not any(start < d <= end for d in effective_days)
        if end != start:
            assert row['end_observation'] in evidence
            assert evidence[row['end_observation']]['published_local'][:10] >= str(end)
        if row['prior_public_date']:
            assert evidence[row['prior_public_quote']]['published_local'][:10] == row['prior_public_date']
        for n in range((end-start).days+1):
            day = start + timedelta(days=n)
            assert candidates.get(day) is None
            candidates[day] = row

    pairs, rejected = [], []
    for start, row in sorted(candidates.items()):
        end = maturity(start)
        if start < min(sessions) or end > max(sessions):
            reason = 'outside_study'
        elif start not in sessions:
            reason = 'opening_not_project_session'
        elif end not in sessions:
            reason = 'nominal_maturity_not_session_bank_roll_unverified'
        elif start not in nav:
            reason = 'missing_exact_open_nav'
        elif end not in nav:
            reason = 'missing_exact_maturity_nav'
        else:
            assert row is not None, f'Rate transcription required for {start}'
            rate = D(row['annual_pct'])
            days = (end-start).days
            ocb = rate*days/D(365)
            ratio = nav[end]/nav[start]
            gross = (ratio-1)*100
            net = (ratio*(1-D('0.020')-D('0.001'))-1)*100
            assert D(0)<rate<D(15) and 28<=days<=31
            prior = bool(row['prior_public_date'] and row['prior_public_date']<str(start))
            pairs.append(dict(open=start,mature=end,days=days,rate_pa_pct=rate,nav_open_vnd=nav[start],
                              nav_mature_vnd=nav[end],ocb_pct=round(ocb,8),vff_nav_pct=round(gross,8),
                              vff_sale_scenario_pct=round(net,8),ocb_minus_nav_pp=round(ocb-gross,8),
                              bank_pdf=row['bank_pdf'],end_observation=row['end_observation'],
                              public_before_open=prior,public_quote=row['prior_public_quote'] if prior else '',
                              nonoverlap=False))
            continue
        rejected.append(dict(open=start,nominal_maturity=end,reason=reason))
    last_end = date.min
    for row in pairs:
        if row['open'] >= last_end:
            row['nonoverlap'] = True
            last_end = row['mature']
    assert len(candidates)==len(pairs)+len(rejected)
    assert maturity(date(2024,1,31))==date(2024,2,29)
    write(HERE/'pairs.csv',pairs)
    write(HERE/'excluded.csv',rejected)
    prepublished = [r for r in pairs if r['public_before_open']]
    distinct_prepublished = []
    for r in prepublished:
        if not distinct_prepublished or r['open'] >= distinct_prepublished[-1]['mature']:
            distinct_prepublished.append(r)
    result={'calendar_start':str(min(sessions)),'calendar_end':str(max(sessions)), 'schedule_files':sum(r['classification']=='retail_schedule' for r in docs),
            'distinct_effective_dates':len(effective_days),'candidate_days':len(candidates),'excluded':len(rejected),
            'all':summarize(pairs),'nonoverlapping':summarize([r for r in pairs if r['nonoverlap']]),
            'public_before_open':summarize(prepublished),
            'public_before_open_nonoverlapping':summarize(distinct_prepublished),
            'effective_day_only':summarize([r for r in pairs if r['open'] in effective_days])}
    (HERE/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    run()
