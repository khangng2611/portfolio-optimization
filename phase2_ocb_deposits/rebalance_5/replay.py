"""Replay saved HYBRID targets using separately funded OCB and VFF accounts."""
import calendar
import csv
import hashlib
import json
import math
import sys
from bisect import bisect_left
from collections import defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
CAPITAL = 10_000_000
MIN_BUY = 100_000


def read(name):
    with (HERE / name).open(newline='') as f:
        return list(csv.DictReader(f))


def write(name, rows):
    with (HERE / name).open('w', newline='') as f:
        columns = list(dict.fromkeys(k for row in rows for k in row))
        writer = csv.DictWriter(f, columns, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def next_month(day):
    month = day.month % 12 + 1
    year = day.year + (month == 1)
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def sale_parts(lots, hundredths, day, price):
    """Consume FIFO in integer hundredths of one fund unit."""
    assert 0 < hundredths <= sum(lots.values())
    for opened in list(lots):
        qty = min(hundredths, lots[opened])
        age = (day - opened).days
        rate = 0.02 if age < 365 else 0.005 if age < 730 else 0
        gross = qty / 100 * price
        lots[opened] -= qty
        if not lots[opened]:
            del lots[opened]
        yield dict(opened=opened, age_days=age, units=qty / 100, gross=gross,
                   fee_pct=rate * 100, fee=gross * rate, tax=gross * 0.001)
        hundredths -= qty
        if not hundredths:
            break


def run(market, dates, targets, assets, window, first, last, arm, sample, lag, events, daily):
    tag = dict(sample=sample, window=window['effective'], arm=arm)
    start_event, start_day = len(events), len(daily)
    cash = CAPITAL
    shares = dict.fromkeys(assets, 0.)
    deposits, lots, due_cash = {}, {}, defaultdict(float)
    order = None
    rate = float(window['annual_pct']) / 100
    early_rate = float(window['early_pa_pct']) / 100

    def event(kind, **values):
        events.append(dict(**tag, day=day, kind=kind, **values))

    for i in range(first, last + 1):
        day, row = dates[i], market[i]
        prices = {a: float(row[a]) for a in assets}
        eligible = float(row['eligible_vff_vnd'])
        mark = 1000 * float(row['VFF'])
        weight = None
        penalty = 0.
        def books(nav):
            principal = sum(p for p, _ in deposits.values())
            accrual = sum(p * rate * (day - d).days / 365 for d, (p, _) in deposits.items())
            fund = sum(lots.values()) / 100 * nav
            reserved = order[2] if order and order[1] == 'buy' else 0.
            risk = sum(shares[a] * prices[a] for a in assets)
            total = cash + sum(due_cash.values()) + reserved + principal + accrual + fund + risk
            return dict(total=total, cash=cash, risk=risk, locked=principal, accrued=accrual,
                        vff_value=fund, units=sum(lots.values()) / 100, reserved=reserved,
                        receivable=sum(due_cash.values()))
        before = books(mark)['total']
        for opened, (p, maturity) in list(deposits.items()):
            if day == maturity:
                interest = p * rate * (day - opened).days / 365
                cash += p + interest
                del deposits[opened]
                event('maturity', opened=opened, principal=p, interest=interest)
        if i in due_cash:
            payment = due_cash.pop(i)
            cash += payment
            event('settle', payment=payment)
        if order and order[0] == i:
            assert row['exact_vff_vnd'] and day.weekday() in (1, 3)
            price = float(row['exact_vff_vnd'])
            assert math.isclose(mark, price, abs_tol=0.001)
            _, side, size = order
            order = None
            if side == 'buy':
                qty = math.floor(size / price * 100)
                lots[day] = qty
                cash += size - qty / 100 * price
                event('buy_fill', units=qty / 100, nav=price, gross=qty / 100 * price)
            else:
                for part in sale_parts(lots, size, day, price):
                    net = part['gross'] - part['fee'] - part['tax']
                    penalty += part['fee'] + part['tax']
                    due_cash[i + lag] += net
                    event('sell_fill', **part, nav=price, net=net, settlement=dates[i + lag])
        if day in targets:
            t = targets[day]
            weight = float(t['VFF'])
            decision = date.fromisoformat(t['decision'])
            assert decision == dates[i - 1]
            # Submitted quantities use the eligible fund mark at execution, never the fill NAV.
            book = books(eligible)
            desired = {a: book['total'] * float(t[a]) for a in assets}
            for a in assets:
                sold = max(0., shares[a] - desired[a] / prices[a])
                shares[a] -= sold
                cash += sold * prices[a]
            gap = book['total'] * weight - book['locked'] - book['accrued'] - book['vff_value']
            if arm == 'OCB':
                if gap < 0:
                    for opened in reversed(list(deposits)):
                        p, maturity = deposits[opened]
                        age = (day - opened).days
                        factor = age / 365
                        withdraw = min(p, -gap / (1 + rate * factor))
                        interest = withdraw * early_rate * factor
                        lost = withdraw * (rate - early_rate) * factor
                        penalty += lost
                        cash += withdraw + interest
                        if withdraw >= p:
                            del deposits[opened]
                        else:
                            deposits[opened] = (p - withdraw, maturity)
                        event('early', opened=opened, maturity=maturity, age_days=age, principal=withdraw,
                              remaining_in_ticket=p-withdraw, interest=interest, lost_interest=lost,
                              early_pa_pct=early_rate*100)
                        gap += withdraw * (1 + rate * factor)
                        if gap >= -1e-6:
                            break
                elif min(gap, cash) >= MIN_BUY:
                    p = min(gap, cash)
                    maturity = dates[bisect_left(dates, next_month(day))]
                    deposits[day] = (p, maturity)
                    cash -= p
                    event('open', opened=day, maturity=maturity, principal=p, annual_pct=rate*100)
            elif order is None:
                fill = next(j for j in range(i + 2, len(dates)) if dates[j].weekday() in (1, 3))
                if min(gap, cash) >= MIN_BUY:
                    amount = min(gap, cash)
                    cash -= amount
                    order = (fill, 'buy', amount)
                    event('buy_order', fill_day=dates[fill], amount=amount)
                elif gap < 0:
                    held = sum(lots.values())
                    qty = min(held, math.floor(-gap / eligible * 100))
                    if qty >= 1000:
                        if held - qty < 1000:
                            qty = held
                        order = (fill, 'sell', qty)
                        event('sell_order', fill_day=dates[fill], units=qty / 100, sizing_nav=eligible)
            deficits = {a: max(0., desired[a] - shares[a] * prices[a]) for a in assets}
            spend = min(max(0., cash), sum(deficits.values()))
            if spend:
                scale = spend / sum(deficits.values())
                for a in assets:
                    shares[a] += deficits[a] * scale / prices[a]
                cash -= spend
        book = books(mark)
        assert min(cash, *shares.values()) > -0.00001 and math.isfinite(book['total'])
        assert abs(before - penalty - book['total']) < 0.02, (day, before, penalty, book)
        early_today = book['accrued'] * early_rate / rate
        daily.append(dict(**tag, day=day, target=weight, **book, locked_pct=100*book['locked']/book['total'],
                          interest_if_withdraw_all_today=early_today,
                          outstanding_order=order[1] if order else '', order_fill=dates[order[0]] if order else ''))
    observations = daily[start_day:]
    et = events[start_event:]
    def total(kind, col):
        return sum(e[col] for e in et if e['kind'] == kind)
    rebalances = [r for r in observations if r['target'] is not None]
    if arm == 'OCB':
        assert abs(total('open','principal')-total('early','principal')-total('maturity','principal')-book['locked']) < .01
    else:
        assert abs(total('buy_fill','units')-total('sell_fill','units')-book['units']) < 1e-7
        assert abs(total('sell_fill','net')-total('settle','payment')-book['receivable']) < .01
    return dict(**tag, first=dates[first], end=day, rebalances=len(rebalances), sessions=len(observations),
                final=book['total'], return_pct=100*(book['total']/CAPITAL-1), locked_end=book['locked'],
                locked_max=max(r['locked'] for r in observations), accrued_end=book['accrued'],
                early_principal=total('early','principal'), early_paid=total('early','interest'),
                early_lost=total('early','lost_interest'), maturity_paid=total('maturity','interest'),
                sold_gross=total('sell_fill','gross'), sale_fee=total('sell_fill','fee'), sale_tax=total('sell_fill','tax'),
                sale_orders_filled=len({e['day'] for e in et if e['kind']=='sell_fill'}),
                reserved_end=book['reserved'], receivable_end=book['receivable'])


def main():
    for name, digest in json.loads((HERE / 'manifest.json').read_text())['frozen_inputs'].items():
        assert hashlib.sha256((HERE / name).read_bytes()).hexdigest() == digest, name
    market = read('markets.csv')
    dates = [date.fromisoformat(r['date']) for r in market]
    assert dates == sorted(set(dates))
    targets = {date.fromisoformat(r['execution']):r for r in read('targets.csv')}
    assets = [k for k in next(iter(targets.values())) if k not in ('decision','execution','VFF')]
    for row in targets.values():
        w = [float(row[a]) for a in [*assets, 'VFF']]
        assert min(w) >= 0 and abs(sum(w)-1) < 1e-7
    results, daily, events = [], [], []
    for window in read('coverage.csv'):
        for sample in ('verified', 'prior_public'):
            if sample == 'prior_public' and not window['prior_public_date']:
                continue
            scheduled = [d for d in targets if window['effective'] <= str(d) <= window['confirmed_through']
                         and (sample == 'verified' or str(d) > window['prior_public_date'])]
            if not scheduled:
                continue
            indices = sorted(dates.index(d) for d in scheduled)
            assert all(b-a==5 for a,b in zip(indices,indices[1:]))
            last = max(i for i,d in enumerate(dates) if str(d)<=window['confirmed_through'])
            for arm, lag in [('OCB',0), ('VFF_T5',5), ('VFF_T1',1)]:
                results.append(run(market, dates, targets, assets, window, indices[0], last, arm,
                                   sample, lag, events, daily))
    write('summary.csv', results)
    write('daily.csv', daily)
    write('transactions.csv', events)
    print(f'{len(results)} episode/arm results, {len(daily)} daily balances, {len(events)} ledger rows')


if __name__ == '__main__':
    main()
