"""Check age bands, independently reconcile lot cashflows, and follow outstanding orders."""
from collections import defaultdict
from datetime import date, timedelta
from math import floor, isclose
from replay import read, sale_parts, write

day = date(2025, 1, 1)
ages = [730, 729, 365, 364]
lots = {day - timedelta(days=age): 2000 for age in ages}
parts = list(sale_parts(lots, 6500, day, 10000))
assert [p['fee_pct'] for p in parts] == [0, 0.5, 0.5, 2]
assert sum(p['fee'] for p in parts) == 3000 and list(lots.values()) == [1500]

market = {r['date']:r for r in read('markets.csv')}
dates = list(market)
coverage = {r['effective']:r for r in read('coverage.csv')}
events = defaultdict(list)
for r in read('transactions.csv'):
    events[r['sample'], r['arm'], r['window']].append(r)
tail = []
for summary in read('summary.csv'):
    key = tuple(summary[k] for k in ('sample','arm','window'))
    trades = events[key]
    rate = float(coverage[key[2]]['annual_pct']) / 100
    early = float(coverage[key[2]]['early_pa_pct']) / 100
    fund_lots = {}
    tickets = {}
    for r in trades:
        kind = r['kind']
        if kind in ('open','early','maturity'):
            p = float(r['principal'])
            if kind == 'open':
                tickets[r['opened']] = p
                continue
            age = (date.fromisoformat(r['day'])-date.fromisoformat(r['opened'])).days
            assert isclose(float(r['interest']), p * age / 365 * (rate if kind=='maturity' else early))
            tickets[r['opened']] -= p
            if kind == 'early':
                assert isclose(float(r['lost_interest']), p * age / 365 * (rate-early))
                assert abs(tickets[r['opened']] - float(r['remaining_in_ticket'])) < .01
            else:
                assert abs(tickets[r['opened']]) < .01
        elif kind == 'buy_fill':
            fund_lots[date.fromisoformat(r['day'])] = round(float(r['units'])*100)
        elif kind == 'sell_fill':
            opening = date.fromisoformat(r['opened'])
            assert opening == min(d for d in fund_lots if fund_lots[d])
            fund_lots[opening] -= round(float(r['units'])*100)
            assert fund_lots[opening] >= 0
            assert isclose(float(r['net']), float(r['gross'])-float(r['fee'])-float(r['tax']))
            if not fund_lots[opening]:
                del fund_lots[opening]
    assert abs(sum(tickets.values()) - float(summary['locked_end'])) < .01
    for r in trades:
        if not r['fill_day'] or r['fill_day'] <= summary['end']:
            continue
        fill = r['fill_day']
        nav = float(market[fill]['exact_vff_vnd'])
        item = dict(sample=key[0], arm=key[1], window=key[2], cutoff=summary['end'],
                    order_date=r['day'], fill_date=fill, order=r['kind'], nav=nav)
        if r['kind']=='buy_order':
            qty = floor(float(r['amount']) / nav * 100) / 100
            tail.append(dict(**item, units=qty, gross=qty*nav, fee=0., tax=0.))
        else:
            lag = 5 if key[1]=='VFF_T5' else 1
            for part in sale_parts(fund_lots, round(float(r['units'])*100), date.fromisoformat(fill), nav):
                tail.append(dict(**item, **part, settlement=dates[dates.index(fill)+lag]))
write('pending_fills.csv', tail)
print('Reconciled principal, interest, FIFO, fees and outstanding order fills.')
