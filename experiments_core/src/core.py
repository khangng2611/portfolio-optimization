"""Pure experiment accounting; no data downloads, training, or cache writes."""
import numpy as np
import pandas as pd


def simulate(prices, targets, start_index=20):
    """Targets keyed by decision close; trade next close after old holdings' P&L.

    Keep one continuous share-equivalent path across IS/OOS. No implicit daily
    rebalancing. Daily weights are the weights at the start of each return.
    """
    dates=prices.index
    weights=np.zeros(prices.shape[1]); cash=1.; nav=[1.]
    records=[]; daily=[]; trades=[]
    for i in range(start_index+1,len(prices)):
        daily.append(weights.copy())
        r=prices.iloc[i].to_numpy()/prices.iloc[i-1].to_numpy()-1
        rp=float(weights@r)
        nav.append(nav[-1]*(1+rp))
        weights=weights*(1+r)/(1+rp); cash=cash/(1+rp)
        decision=dates[i-1]
        if decision in targets:
            target=np.asarray(targets[decision],dtype=float)
            change=target-weights
            initial=bool(cash>.999999)
            trades.append({'decision_date':decision,'execution_date':dates[i],
                           'first_return_date':dates[i+1] if i+1<len(prices) else pd.NaT,
                           'turnover':float(np.abs(change).sum()/2),
                           'traded_notional':float(np.abs(change).sum()),
                           'initial_allocation':initial})
            for j,a in enumerate(prices.columns):
                records.append({'decision_date':decision,'execution_date':dates[i],
                                'asset':a,'pre_trade_weight':weights[j],
                                'target_weight':target[j],'weight_change':change[j]})
            weights=target.copy();cash=0.
        if abs(weights.sum()+cash-1)>1e-8:
            raise AssertionError('Holdings budget failure')
    return {'nav':pd.Series(nav,index=dates[start_index:]),
            'daily_weights':pd.DataFrame(daily,index=dates[start_index+1:],columns=prices.columns),
            'weights':pd.DataFrame(records),'trades':pd.DataFrame(trades)}


def prior_posterior(sigma,delta,tau,p=None,q=None,confidence=None):
    # Same eigenvalue floor as frozen code. No-view posterior is explicitly pi.
    sigma=np.asarray(sigma,dtype=float)
    values,vectors=np.linalg.eigh((sigma+sigma.T)/2)
    sigma=(vectors*np.maximum(values,1e-8))@vectors.T
    pi=delta*sigma@np.full(len(sigma),1/len(sigma))
    if p is None or len(p)==0:
        return pi
    p=np.asarray(p);q=np.asarray(q)
    omega=np.diag(np.maximum(np.diag(p@(tau*sigma)@p.T),1e-10)/np.clip(confidence,1e-6,1))
    return pi+tau*sigma@p.T@np.linalg.solve(p@(tau*sigma)@p.T+omega,q-p@pi)


def simple_selection(prices,t,k=5):
    past=prices.iloc[max(0,t-21):t]
    vol=past.pct_change(fill_method=None).iloc[1:].std()
    return sorted(vol.index,key=lambda a:(vol[a],a))[:k]


def cost_returns(gross,trades,bps):
    """Event-level multiplicative approximation, per side, including initial buy.

    Charges occur on execution date, after that day's gross return; never shift
    a terminal trade's charge outside the observed sample.
    """
    if bps==0:
        return gross.copy()
    notional=trades.groupby('execution_date').traded_notional.sum().reindex(gross.index,fill_value=0)
    haircut=1-(bps/10000)*notional
    if (haircut<=0).any():
        raise ValueError('Cost haircut must be positive')
    return (1+gross)*haircut-1


def return_stats(returns):
    r=np.asarray(returns,dtype=float)
    nav=np.r_[1.,np.cumprod(1+r)]
    volatility=np.std(r,ddof=1)*np.sqrt(252)
    rf=1.06**(1/252)-1
    return {'final_nav':float(nav[-1]),'ann_return':float(nav[-1]**(252/len(r))-1),
            'ann_volatility':float(volatility),
            'sharpe':float((np.mean(r)-rf)*252/volatility) if volatility>0 else np.nan,
            'max_drawdown':float(np.min(nav/np.maximum.accumulate(nav)-1))}


def bootstrap_effects(a,b,block=10,replicates=1000,seed=20261014):
    a=np.asarray(a);b=np.asarray(b)
    if len(a)!=len(b) or len(a)<block or not np.isfinite(np.r_[a,b]).all():
        raise ValueError('Bootstrap requires aligned finite paired returns')
    rng=np.random.default_rng(seed);n=len(a)
    samples={key:[] for key in ['ann_return','sharpe']}
    for _ in range(replicates):
        starts=rng.integers(0,n-block+1,size=int(np.ceil(n/block)))
        idx=(starts[:,None]+np.arange(block)).ravel()[:n]
        sa,sb=return_stats(a[idx]),return_stats(b[idx])
        for key in samples:
            samples[key].append(sa[key]-sb[key])
    sa,sb=return_stats(a),return_stats(b)
    return [{'metric':key,'effect':sa[key]-sb[key],
             'ci_low':float(np.quantile(values,.025)),
             'ci_high':float(np.quantile(values,.975)),
             'block_length':block,'replicates':replicates,'seed':seed}
            for key,values in samples.items()]
